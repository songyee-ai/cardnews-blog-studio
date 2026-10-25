import copy
import io
import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from app import ROOT,Store
from content import audit,char_count,export_zip,body_text
from trends import InputError,parse_public

class ContentTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.store=Store(Path(self.tmp.name)/"test.sqlite3")
        self.c=json.loads((ROOT/"maltipoo-content.json").read_text(encoding="utf-8"))
        r=json.loads((ROOT/"maltipoo-research.json").read_text(encoding="utf-8"))
        html='<h2>2026-10-24</h2><h3>반려동물</h3><ol><li><span>1</span><a>말티푸</a></li></ol>'
        self.send("collect",snapshot=parse_public(html));self.send("select",candidate_id="rank-1");self.send("research",research=r)
    def tearDown(self):self.tmp.cleanup()
    def send(self,action,snapshot=None,**data):
        p=self.store.get();return self.store.mutate(action,{"version":p["version"],"request_id":f'{action}-{p["version"]}',**data},snapshot)
    def test_counts_use_all_whitespace_and_keep_normal_health_words(self):
        self.assertEqual(char_count("가 나\t다\n라\u3000마"),5)
        a=audit(self.c);self.assertTrue(a["body_in_target"]);self.assertEqual(a["body_chars_no_space"],2054)
        self.assertEqual(a["findings"],[]);self.assertEqual(a["image_count"],10)
        c=copy.deepcopy(self.c);c["intro"].append("수의사와 상담하고 알레르기를 확인해요.")
        self.assertEqual(audit(c)["findings"],[])
    def test_edit_rechecks_terms_resets_approval_and_keeps_sections(self):
        self.send("content",content=self.c);self.send("approve_content")
        p=self.send("edit_content",title=self.c["title"],avoid_terms=["돌봄"])
        self.assertIsNone(p["content"]["approval"]);self.assertTrue(p["content"]["audit"]["findings"])
        before=self.store.get()
        with self.assertRaises(InputError):self.send("approve_content")
        self.assertEqual(before,self.store.get())
        p=self.send("edit_content",avoid_terms=[]);p=self.send("approve_content",commercial_relationship="none")
        self.assertEqual(p["content"]["approval"]["revision"],3)
        self.assertEqual(p["content"]["approval"]["commercial_relationship"],"none")
        before=self.store.get()
        with self.assertRaises(InputError):self.send("approve_content",commercial_relationship="invalid")
        self.assertEqual(before,self.store.get())
        self.assertEqual(Store(self.store.path).get()["status"],"content_approved")
    def test_bad_edit_and_missing_sources_preserve_draft(self):
        self.send("content",content=self.c);before=self.store.get()
        with self.assertRaises(InputError):self.send("edit_content",sections=[])
        self.assertEqual(before,self.store.get())
        wrong=copy.deepcopy(self.c);wrong["sections"][0]["source_ids"]=["missing"]
        with self.assertRaises(InputError):self.send("content",content=wrong)
        self.assertEqual(before,self.store.get())
    def test_export_contains_ten_images_and_portable_preview(self):
        p=self.send("content",content=self.c)
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);assets=root/"output/maltipoo-v1";assets.mkdir(parents=True)
            (root/"WRITING_RULES.md").write_text("TEST",encoding="utf-8")
            for i in range(1,11):(assets/f"{i:02d}.png").write_bytes(b"synthetic test asset")
            with zipfile.ZipFile(io.BytesIO(export_zip(p,root))) as z:
                self.assertIsNone(z.testzip());self.assertEqual(len([n for n in z.namelist() if n.startswith("images/")]),10)
                html=z.read("미리보기.html").decode();self.assertEqual(html.count("<img "),10)
                self.assertIn('src="images/01.png"',html)
                self.assertIn(body_text(self.c),z.read("원고.txt").decode())
            revised=root/"output/maltipoo-v2";revised.mkdir()
            for i in range(1,11):(revised/f"{i:02d}.png").write_bytes(b"synthetic revised asset")
            p["content"]["asset_set"]="maltipoo-v2"
            with zipfile.ZipFile(io.BytesIO(export_zip(p,root))) as z:
                self.assertEqual(z.read("images/01.png"),b"synthetic revised asset")
            p["content"].pop("asset_set")
            (assets/"10.png").unlink()
            with self.assertRaises(InputError):export_zip(p,root)

    def test_only_registered_asset_versions_are_accepted(self):
        invalid=copy.deepcopy(self.c);invalid["asset_set"]="../../outside"
        with self.assertRaises(InputError):self.send("content",content=invalid)

if __name__=="__main__":unittest.main()
