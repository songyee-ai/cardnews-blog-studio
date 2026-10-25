import base64
import io
import json
import tempfile
import threading
import unittest
import zipfile
from pathlib import Path
from PIL import Image
from app import Store, Problem
from jobs import JobManager, checked_storyboard

URL = "https://example.org/official-source"


class FakeEngine:
    def __init__(self, data):
        self.data = data

    def run(self, project_id, prompt, schema, session_id, log, session, cancelled):
        session("sid")
        return self.data, {"session_id": "sid", "read_urls": [URL], "searched": False}


class FinalCardTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.store = Store(self.root / "projects.sqlite3")
        p = self.store.create({"topic": "카드 완성 시험", "mode": "claude"})
        p.update(status="brief_ready", card_size="1080x1350", read_urls=[URL], editorial_goal="변화 이해하기", engine_session_id="sid",
                 editorial_brief={"facts": [{"text": "시험 사실", "kind": "fact", "source_url": URL}]})
        data = {"status": "storyboard_ready", "format": "이야기형", "design_direction": "공통 색감", "review_notes": "날짜 대조",
                "cards": [{"role": "설명", "title": f"제목 {i}", "message": f"서로 다른 핵심 문장 {i}", "body": "2026년 10월 21일 발표한 내용을 짧게 설명합니다.",
                           "image_brief": "설명용 이미지, 하단 1/3 본문 여백" if i % 2 else "설명용 이미지, 상단 여백", "source_urls": [URL], "fact_refs": [0]} for i in range(5)]}
        board = checked_storyboard(data, p)
        board["approved_version"] = board["version"]
        p.update(storyboard=board, status="storyboard_approved")
        with self.store.connect() as db:
            db.execute("UPDATE projects SET body=? WHERE id=?", (json.dumps(p), p["id"]))
        self.p, self.cards, self.n = p, board["cards"], 0

    def tearDown(self):
        self.tmp.cleanup()

    def act(self, action, **data):
        self.n += 1
        self.p = self.store.mutate(self.p["id"], action, dict(data, version=self.p["version"], request_id=f"r{self.n}"))
        return self.p

    def image(self, color="ivory"):
        stream = io.BytesIO()
        Image.new("RGB", (400, 500), color).save(stream, format="PNG")
        return base64.b64encode(stream.getvalue()).decode()

    def import_all(self):
        for card in self.cards:
            self.act("import-image", card_id=card["id"], image_base64=self.image(), generator="unit-test fixture", prompt="검사용 단색 배경")

    def approve_final(self):
        return self.act("approve", stage="final", render_signature=self.p["render_signature"])

    def test_text_rendered_separately_and_only_changed_card_rerenders(self):
        self.act("import-image", card_id=self.cards[0]["id"], image_base64=self.image(), generator="fixture", prompt="")
        self.assertEqual(list(self.p["renders"]), [self.cards[0]["id"]])
        self.import_all()
        renders = {k: dict(v) for k, v in self.p["renders"].items()}
        first = self.root / renders[self.cards[0]["id"]]["relative_path"]
        with Image.open(first) as image:
            self.assertEqual(image.size, (1080, 1350))
        self.assertTrue(all(x["level"] != "error" for r in renders.values() for x in r["checks"]))
        background = dict(self.p["image_results"][self.cards[1]["id"]])
        self.act("edit-card", storyboard_version=1, card_id=self.cards[1]["id"], title="고친 제목", message="고친 핵심 문장", body="고친 본문")
        self.assertEqual(self.p["image_results"][self.cards[1]["id"]], background)
        self.assertNotEqual(self.p["renders"][self.cards[1]["id"]]["sha256"], renders[self.cards[1]["id"]]["sha256"])
        for card in self.cards[:1] + self.cards[2:]:
            self.assertEqual(self.p["renders"][card["id"]]["sha256"], renders[card["id"]]["sha256"])
            self.assertEqual(self.p["renders"][card["id"]]["relative_path"], renders[card["id"]]["relative_path"])

    def test_final_approval_gate_export_and_verification(self):
        self.act("import-image", card_id=self.cards[0]["id"], image_base64=self.image(), generator="fixture", prompt="")
        with self.assertRaises(Problem):
            self.approve_final()
        self.import_all()
        with self.assertRaises(Problem):
            self.act("approve", stage="final", render_signature="old-screen")
        self.approve_final()
        self.assertEqual(self.p["status"], "final_approved")
        with zipfile.ZipFile(self.root / self.p["final_approval"]["export_path"]) as archive:
            names = archive.namelist()
            self.assertEqual([n for n in names if n.startswith("cards/")], [f"cards/card-0{i}.png" for i in range(1, 6)])
            self.assertIn(URL, archive.read("sources.md").decode())
            self.assertIn("unit-test fixture", archive.read("image-log.md").decode())
        check = self.act("verify-export")["export_check"]
        results = {i["name"]: i["result"] for i in check["items"]}
        self.assertNotIn("fail", results.values())
        self.assertEqual(results["원문 링크가 지금 열리는지"], "unverified")
        self.assertIn("10월 21일", next(i["detail"] for i in check["items"] if i["name"] == "카드 속 날짜와 원문 대조"))

    def test_layout_change_or_image_only_fix_clears_final_approval_and_keeps_other_cards(self):
        self.import_all()
        self.approve_final()
        before = {k: v["sha256"] for k, v in self.p["renders"].items()}
        self.act("layout-card", card_id=self.cards[2]["id"], position="bottom", title_size=56, body_size=32, text_color="#1E1E1E", panel=0.7)
        self.assertEqual(self.p["status"], "images_ready")
        self.assertIsNone(self.p["final_approval"])
        self.approve_final()
        self.act("fix-card", card_id=self.cards[3]["id"], storyboard_version=1, request="4번 그림이 너무 어두워. 밝게 다시 만들어 줘.", scope="image")
        self.assertEqual(self.p["status"], "images_partial")
        self.assertIsNone(self.p["final_approval"])
        self.assertNotIn(self.cards[3]["id"], self.p["renders"])
        self.assertEqual(self.p["image_results"][self.cards[3]["id"]]["status"], "needs_image")
        self.assertEqual(self.p["renders"][self.cards[0]["id"]]["sha256"], before[self.cards[0]["id"]])

    def test_overflowing_text_blocks_final_approval(self):
        self.import_all()
        self.act("layout-card", card_id=self.cards[0]["id"], position="top", title_size=80, body_size=44, text_color="#24384A", panel=0.8)
        self.act("edit-card", storyboard_version=1, card_id=self.cards[0]["id"], title="가나다라마바사아자차" * 4, message="긴 핵심 문장입니다 " * 6, body="긴 본문입니다 " * 22)
        self.assertTrue(any(x["level"] == "error" for x in self.p["renders"][self.cards[0]["id"]]["checks"]))
        self.act("approve", stage="storyboard", storyboard_version=2)
        with self.assertRaises(Problem):
            self.approve_final()

    def test_symbol_without_glyph_is_replaced_or_blocks_approval(self):
        self.import_all()
        self.act("edit-card", storyboard_version=1, card_id=self.cards[0]["id"], title="✔ 정리", message="체크 표시가 있는 핵심 문장", body="✔ 발표일 확인")
        self.assertTrue(all(x["level"] != "error" for x in self.p["renders"][self.cards[0]["id"]]["checks"]))
        self.assertEqual(self.p["storyboard"]["cards"][0]["title"], "✔ 정리")
        self.act("edit-card", storyboard_version=2, card_id=self.cards[0]["id"], title="🚀 정리", message="체크 표시가 있는 핵심 문장", body="발표일 확인")
        self.assertTrue(any("빈 네모" in x["text"] and x["level"] == "error" for x in self.p["renders"][self.cards[0]["id"]]["checks"]))

    def test_text_fix_through_same_session_changes_only_that_card(self):
        self.import_all()
        self.approve_final()
        before = {k: v["sha256"] for k, v in self.p["renders"].items()}
        target = self.cards[2]
        self.act("fix-card", card_id=target["id"], storyboard_version=1, request="3번 본문이 길어. 한 문장으로 줄여 줘.", scope="text")
        self.assertEqual(self.p["status"], "revising")
        engine = FakeEngine({"status": "card_fixed", "change": "text", "title": target["title"], "message": target["message"],
                             "body": "10월 21일 발표 내용을 한 문장으로 줄였습니다.", "image_note": "", "reason": "본문을 한 문장으로 줄였습니다.",
                             "fact_refs": [0], "source_urls": [URL]})
        JobManager(self.store, engine).work(self.store.get(self.p["id"]), threading.Event())
        p = self.store.get(self.p["id"])
        self.assertEqual(p["status"], "storyboard_ready")
        self.assertIsNone(p["final_approval"])
        self.assertEqual(p["storyboard"]["cards"][2]["body"], "10월 21일 발표 내용을 한 문장으로 줄였습니다.")
        self.assertEqual([c for i, c in enumerate(p["storyboard"]["cards"]) if i != 2], [c for i, c in enumerate(self.cards) if i != 2])
        for card in self.cards:
            same = p["renders"][card["id"]]["sha256"] == before[card["id"]]
            self.assertEqual(same, card["id"] != target["id"])

    def test_failed_text_fix_keeps_approved_cards(self):
        self.import_all()
        self.approve_final()
        self.act("fix-card", card_id=self.cards[0]["id"], storyboard_version=1, request="1번 제목을 바꿔 줘.", scope="text")
        engine = FakeEngine({"status": "card_fixed", "change": "image", "title": "", "message": "", "body": "", "image_note": "x", "reason": "", "fact_refs": [], "source_urls": []})
        JobManager(self.store, engine).work(self.store.get(self.p["id"]), threading.Event())
        p = self.store.get(self.p["id"])
        self.assertEqual(p["status"], "final_approved")
        self.assertIn("글만 고치기", p["card_fix"]["error"])
        self.assertEqual(p["storyboard"]["version"], 1)


if __name__ == "__main__":
    unittest.main()
