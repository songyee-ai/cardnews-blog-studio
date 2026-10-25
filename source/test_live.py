"""Live-path contracts tested with an isolated fake CLI adapter; no API spend."""
import tempfile
import threading
import unittest
from pathlib import Path
from app import Store, Problem
from jobs import JobManager, checked_research, checked_editorial
from engine import EngineError, extract_result

URL = "https://example.org/official-announcement"


class LiveSafetyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.tmp.name) / "projects.sqlite3")

    def tearDown(self):
        self.tmp.cleanup()

    def request(self, p, action, **extra):
        return self.store.mutate(p["id"], action, dict(version=p["version"], request_id=f"{action}-{p['version']}", **extra))

    def test_live_never_falls_back_to_mock_and_job_request_is_idempotent(self):
        p = self.store.create({"topic": "AI 최신소식", "mode": "claude"})
        self.assertEqual(p["candidates"], [])
        data = {"version": 1, "request_id": "research"}
        a = self.store.mutate(p["id"], "research", data)
        b = self.store.mutate(p["id"], "research", data)
        self.assertEqual(a["run_id"], b["run_id"])
        self.assertEqual(a["status"], "researching")
        with self.assertRaises(Problem):
            self.request(a, "research")

    def test_recovery_and_cancel_preserve_context(self):
        p = self.store.create({"topic": "AI 최신소식", "mode": "claude"})
        p = self.request(p, "research")
        JobManager(self.store).recover()
        p = self.store.get(p["id"])
        self.assertEqual(p["status"], "interrupted")
        self.assertIn("서버", p["error"])
        p = self.request(p, "retry")
        old_run = p["run_id"]
        p = self.request(p, "cancel")
        JobManager(self.store).update(p["id"], old_run, lambda x: x.update(status="brief_ready"))
        self.assertEqual(self.store.get(p["id"])["status"], "cancelled")

    def test_old_event_and_invented_read_are_not_verified(self):
        period = {"start": "2026-10-17", "end": "2026-10-23"}
        base = dict(title="가상 검사 자료", summary="설명", category="연구", value="이유", uncertainty="", source_url=URL, evidence="근거", event_key="same-event", published_at="2026-10-20", event_at="2026-01-01", source_read=True)
        result = {"status": "research_ready", "candidates": [base], "notes": ""}
        self.assertEqual(checked_research(result, {"searched": True, "read_urls": [URL]}, period)[0], [])
        base["event_at"] = "2026-10-20"
        items, _ = checked_research(result, {"searched": True, "read_urls": []}, period)
        self.assertFalse(items[0]["source_read"])
        with self.assertRaises(EngineError):
            checked_research(result, {"searched": False}, period)

    def test_unread_fact_and_malformed_output_are_rejected(self):
        brief = dict(recommended_format="이야기형", format_comparison="비교", reason="이유", limitations="한계", hooks=["문구1", "문구2"], facts=[dict(text="사실",kind="fact",source_url=URL)])
        data = {"status": "brief_ready", "brief": brief, "question": None}
        with self.assertRaises(EngineError):
            checked_editorial(data, [], True)
        self.assertEqual(checked_editorial(data, [URL], True)[0], "brief_ready")
        with self.assertRaises(EngineError):
            extract_result({"type": "result", "subtype": "success", "result": "not JSON"})

    def test_answer_is_passed_to_same_session_once(self):
        calls = []
        class FakeEngine:
            def run(self, project_id, prompt, schema, session_id, on_event, on_session, cancelled):
                calls.append((session_id, prompt))
                on_session(session_id or "session-for-test")
                if len(calls) == 1:
                    data = {"status": "need_input", "question": {"text": "목적은?", "options": [{"value": "이해", "detail": "설명", "recommended": True}, {"value": "활용", "detail": "실습", "recommended": False}], "recommendation": "이유"}, "brief": None}
                else:
                    data = {"status": "brief_ready", "question": None, "brief": dict(recommended_format="이야기형", format_comparison="비교", reason="답변 이해 반영", limitations="한계", hooks=["문구1", "문구2"], facts=[dict(text="사실", kind="fact", source_url=URL)])}
                return data, {"session_id": "session-for-test", "read_urls": [URL]}
        manager = JobManager(self.store, FakeEngine())
        p = self.store.create({"topic": "AI 최신소식", "mode": "claude"})
        with self.store.connect() as db:
            p.update(status="selecting", candidates=[dict(id="candidate",title="가상 시험",source_url=URL)], selected_ids=["candidate"], engine_session_id="session-for-test", read_urls=[URL])
            import json
            db.execute("UPDATE projects SET body=? WHERE id=?", (json.dumps(p),p["id"]))
        p = self.request(p, "next")
        manager.work(p, threading.Event())
        p = self.store.get(p["id"])
        self.assertEqual(p["status"], "waiting_for_user")
        data = dict(version=p["version"],request_id="answer",question_id=p["question"]["id"],question_version=1,answer="이해")
        p = self.store.mutate(p["id"], "answers", data)
        manager.work(p, threading.Event())
        final = self.store.get(p["id"])
        self.assertEqual(final["status"], "brief_ready")
        self.assertEqual(final["continuation_count"], 1)
        self.assertEqual([x[0] for x in calls], ["session-for-test", "session-for-test"])
        self.assertIn('"text": "이해"', calls[1][1])
        self.store.mutate(p["id"], "answers", data)
        self.assertEqual(len(calls), 2)


if __name__ == "__main__":
    unittest.main()
