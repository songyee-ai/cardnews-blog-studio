import copy
import json
import tempfile
import unittest
from pathlib import Path
from app import Store, Problem
from engine import EngineError
from jobs import checked_storyboard

URL = "https://example.org/official-source"


class StoryboardSafetyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.tmp.name) / "projects.sqlite3")
        self.p = self.store.create({"topic": "시험 자료", "mode": "claude"})
        self.p.update(status="brief_ready", card_size="1080x1350", read_urls=[URL], editorial_goal="변화 이해하기",
                      editorial_brief={"facts": [{"text": "시험 사실", "kind": "fact", "source_url": URL}]})
        self.data = {"status": "storyboard_ready", "format": "이야기형", "design_direction": "공통 색감과 여백", "review_notes": "날짜와 조건 대조",
                     "cards": [{"role": "설명", "title": f"제목 {i}", "message": f"서로 다른 메시지 {i}", "body": "짧은 본문", "image_brief": "설명용 이미지, 글자 없음", "source_urls": [URL], "fact_refs": [0]} for i in range(5)]}

    def tearDown(self):
        self.tmp.cleanup()

    def save(self):
        with self.store.connect() as db:
            db.execute("UPDATE projects SET body=? WHERE id=?", (json.dumps(self.p), self.p["id"]))

    def test_unread_or_unknown_source_and_short_board_are_rejected(self):
        self.assertEqual(len(checked_storyboard(self.data, self.p)["cards"]), 5)
        with self.assertRaises(EngineError):
            checked_storyboard(self.data, dict(self.p, read_urls=[]))
        bad = copy.deepcopy(self.data)
        bad["cards"][0]["fact_refs"] = [9]
        with self.assertRaises(EngineError):
            checked_storyboard(bad, self.p)
        bad = copy.deepcopy(self.data)
        bad["cards"][0]["source_urls"] = ["https://example.org/unread"]
        with self.assertRaises(EngineError):
            checked_storyboard(bad, self.p)
        with self.assertRaises(EngineError):
            checked_storyboard(dict(self.data, cards=self.data["cards"][:4]), self.p)

    def test_partial_edit_keeps_other_cards_and_invalidates_approval(self):
        board = checked_storyboard(self.data, self.p)
        board["approved_version"] = 1
        self.p.update(storyboard=board, status="storyboard_approved")
        self.save()
        untouched = copy.deepcopy(board["cards"][1:])
        p = self.store.mutate(self.p["id"], "edit-card", dict(version=self.p["version"], request_id="edit", storyboard_version=1,
            card_id=board["cards"][0]["id"], title="고친 제목", message="고친 메시지", body="고친 본문"))
        self.assertEqual(p["storyboard"]["cards"][1:], untouched)
        self.assertEqual(p["status"], "storyboard_ready")
        self.assertIsNone(p["storyboard"]["approved_version"])
        self.assertEqual(p["storyboard_history"][0]["cards"][0]["title"], "제목 0")
        self.assertTrue(p["storyboard"]["cards"][0]["edited_by_user"])

    def test_old_approval_is_rejected_and_current_approval_starts_no_image_job(self):
        self.p.update(storyboard=checked_storyboard(self.data,self.p), status="storyboard_ready")
        self.save()
        with self.assertRaises(Problem):
            self.store.mutate(self.p["id"], "approve", dict(version=self.p["version"],request_id="old",stage="storyboard",storyboard_version=0))
        p = self.store.mutate(self.p["id"], "approve", dict(version=self.p["version"],request_id="ok",stage="storyboard",storyboard_version=1))
        self.assertEqual(p["status"], "storyboard_approved")
        self.assertIsNone(p["run_id"])

    def test_storyboard_rebuild_retains_previous_plan_while_running(self):
        board = checked_storyboard(self.data,self.p)
        self.p.update(storyboard=board, status="storyboard_ready")
        self.save()
        p = self.store.mutate(self.p["id"], "storyboard", dict(version=self.p["version"],request_id="rebuild",card_size="1080x1350",feedback="쉽게 설명"))
        self.assertEqual(p["status"], "planning")
        self.assertEqual(p["storyboard"], board)
        self.assertEqual(p["storyboard_feedback"], "쉽게 설명")


if __name__ == "__main__":
    unittest.main()
