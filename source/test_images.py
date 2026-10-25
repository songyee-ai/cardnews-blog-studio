import base64
import io
import json
import tempfile
import unittest
from pathlib import Path
from PIL import Image
from app import Store, Problem
from image_assets import inspect_image, ImageAssetError


class ImportedImageTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.tmp.name) / "projects.sqlite3")
        self.p = self.store.create({"topic": "이미지 검사", "mode": "claude"})
        self.p.update(status="storyboard_approved", storyboard={"version": 1, "approved_version": 1, "cards": [
            {"id": "card1", "order": 1, "title": "제목", "message": "핵심", "body": "본문", "source_urls": ["https://example.org/a"]},
            {"id": "card2", "order": 2, "title": "다른 제목", "message": "다른 핵심", "body": "다른 본문", "source_urls": ["https://example.org/a"]}]})
        with self.store.connect() as db:
            db.execute("UPDATE projects SET body=? WHERE id=?", (json.dumps(self.p), self.p["id"]))
        stream = io.BytesIO()
        Image.new("RGB", (256, 320), "ivory").save(stream, format="PNG")
        self.raw = stream.getvalue()

    def tearDown(self):
        self.tmp.cleanup()

    def data(self):
        return dict(version=self.p["version"], request_id="image", card_id="card1", image_base64=base64.b64encode(self.raw).decode(), generator="unit-test fixture", prompt="검사용 단색 이미지")

    def test_real_decode_and_exact_source_preservation(self):
        p = self.store.mutate(self.p["id"], "import-image", self.data())
        self.assertEqual(p["status"], "images_partial")
        info = p["image_results"]["card1"]
        self.assertEqual((info["width"], info["height"]), (256, 320))
        self.assertEqual((Path(self.tmp.name) / info["relative_path"]).read_bytes(), self.raw)
        with self.store.connect() as db:
            signature = db.execute("SELECT signature FROM requests").fetchone()[0]
        self.assertEqual(len(signature), 64)
        self.assertEqual(p, self.store.mutate(self.p["id"], "import-image", self.data()))

    def test_fake_or_truncated_image_is_rejected(self):
        for raw in (b"not an image", self.raw[:50]):
            with self.assertRaises(ImageAssetError):
                inspect_image(raw)
        data = self.data()
        data["image_base64"] = "invalid%%%"
        with self.assertRaises(Problem):
            self.store.mutate(self.p["id"], "import-image", data)
        self.assertNotIn("image_results", self.store.get(self.p["id"]))

    def test_text_only_edit_keeps_background_and_reapproval_restores_state(self):
        p = self.store.mutate(self.p["id"], "import-image", self.data())
        image = p["image_results"]["card1"].copy()
        p = self.store.mutate(p["id"], "edit-card", dict(version=p["version"],request_id="edit",storyboard_version=1,card_id="card1",title="새 제목",message="새 핵심",body="새 본문"))
        self.assertEqual(p["image_results"]["card1"], image)
        self.assertIsNone(p["storyboard"]["approved_version"])
        p = self.store.mutate(p["id"], "approve", dict(version=p["version"],request_id="approve",stage="storyboard",storyboard_version=2))
        self.assertEqual(p["status"], "images_partial")


if __name__ == "__main__":
    unittest.main()
