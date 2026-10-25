"""State-safety checks for the first mock milestone; no real AI calls."""
import tempfile
import unittest
from pathlib import Path
from app import Problem, Store


class StateSafetyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "projects.sqlite3"
        self.store = Store(self.path)

    def tearDown(self):
        self.tmp.cleanup()

    def waiting(self):
        p = self.store.create({"topic": "AI 최신소식"})
        p = self.store.mutate(p["id"], "selection", {"candidate_ids": ["mock-1"], "version": p["version"], "request_id": "select"})
        return self.store.mutate(p["id"], "next", {"version": p["version"], "request_id": "next"})

    def test_restart_restores_waiting_question_and_selection(self):
        p = self.waiting()
        restored = Store(self.path).get(p["id"])
        self.assertEqual(p, restored)
        self.assertEqual(restored["status"], "waiting_for_user")
        self.assertIsNone(restored["answer"])
        self.assertEqual(restored["continuation_count"], 0)

    def test_duplicate_answer_does_not_continue_twice(self):
        p = self.waiting()
        data = {"version": p["version"], "question_id": p["question"]["id"], "question_version": 1, "answer": "변화 이해하기", "request_id": "answer"}
        first = self.store.mutate(p["id"], "answers", data)
        self.assertEqual(first, self.store.mutate(p["id"], "answers", data))
        data["request_id"] = "answer-second-click"
        self.assertEqual(first, self.store.mutate(p["id"], "answers", data))
        self.assertEqual(self.store.get(p["id"])["continuation_count"], 1)

    def test_stale_or_foreign_answer_cannot_overwrite(self):
        a, b = self.waiting(), self.waiting()
        data = {"version": b["version"], "question_id": a["question"]["id"], "question_version": 1, "answer": "직접 써보기", "request_id": "foreign"}
        with self.assertRaises(Problem) as err:
            self.store.mutate(b["id"], "answers", data)
        self.assertEqual(err.exception.status, 409)
        self.assertIsNone(self.store.get(b["id"])["answer"])
        data.update(question_id=b["question"]["id"], version=b["version"]-1)
        with self.assertRaises(Problem):
            self.store.mutate(b["id"], "answers", data)

    def test_request_collision_and_selection_limit(self):
        p = self.store.create({"topic": "AI 최신소식"})
        data = {"version": p["version"], "candidate_ids": ["mock-1"], "request_id": "same"}
        self.store.mutate(p["id"], "selection", data)
        with self.assertRaises(Problem):
            self.store.mutate(p["id"], "selection", dict(data, candidate_ids=["mock-2"]))
        with self.assertRaises(Problem):
            self.store.mutate(p["id"], "selection", dict(data, version=2, request_id="too-many", candidate_ids=["mock-1","mock-2","mock-3","mock-4"]))
        self.assertEqual(self.store.get(p["id"])["selected_ids"], ["mock-1"])

    def test_cannot_skip_selection_or_revise_after_commit(self):
        p = self.store.create({"topic": "AI 최신소식"})
        with self.assertRaises(Problem):
            self.store.mutate(p["id"], "next", {"version": p["version"], "request_id": "skip"})
        p = self.waiting()
        with self.assertRaises(Problem):
            self.store.mutate(p["id"], "selection", {"version": p["version"], "request_id": "late", "candidate_ids": ["mock-2"]})


if __name__ == "__main__":
    unittest.main()
