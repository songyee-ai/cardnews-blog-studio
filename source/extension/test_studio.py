import json
import tempfile
import unittest
from pathlib import Path
from app import Store
from trends import parse_public,read_datalab_csv,InputError

HTML='''<h2>2026-10-24 기준 그룹별 상위 키워드</h2><h3>반려동물</h3><ol><li><span>1</span><a>말티푸</a></li><li><span>2</span><a>강아지 감</a></li></ol><h3>자동차</h3><ol><li><span>1</span><a>차</a></li></ol>'''

class StudioTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.store=Store(Path(self.tmp.name)/"test.sqlite3")
    def tearDown(self):self.tmp.cleanup()
    def collect(self):
        return self.store.mutate("collect",{"version":1,"request_id":"collect"},parse_public(HTML))
    def test_public_adapter_records_only_visible_category_and_missing_metrics(self):
        s=parse_public(HTML)
        self.assertEqual([r["keyword"] for r in s["rows"]],["말티푸","강아지 감"])
        self.assertIsNone(s["rows"][0]["search_volume"])
        self.assertFalse(s["upstream_verified"])
        for bad in ("<h1>로그인</h1>",HTML.replace("2026-10-24","날짜 없음"),HTML.replace('<span>2</span>','<span>1</span>')):
            with self.assertRaises(InputError):parse_public(bad)
    def test_selection_persists_and_repeated_request_is_idempotent(self):
        p=self.collect();data={"version":p["version"],"request_id":"select","candidate_id":"rank-1","angle":"초보 보호자 관점"}
        selected=self.store.mutate("select",data)
        self.assertEqual(self.store.mutate("select",data),selected)
        self.assertEqual(Store(self.store.path).get()["selection"]["angle"],"초보 보호자 관점")
        with self.assertRaises(InputError):self.store.mutate("select",dict(data,request_id="late"))
    def test_bad_or_missing_data_does_not_destroy_selection(self):
        p=self.collect();p=self.store.mutate("select",{"version":p["version"],"request_id":"select","candidate_id":"rank-1"})
        before=self.store.get()
        with self.assertRaises(InputError):self.store.mutate("datalab",{"version":p["version"],"request_id":"bad","csv":"말티푸\n강아지 감"})
        self.assertEqual(self.store.get(),before)
    def test_normalized_indices_validation(self):
        data=read_datalab_csv("date,keyword,index\n2026-10-01,검사용,20\n2026-10-02,검사용,40")
        self.assertEqual(len(data["rows"]),2);self.assertFalse(data["independently_verified"])
        for bad in ("date,keyword,index\n2026-10-01,검사용,101", "date,keyword,index\n2026-10-01,검사용,20", "date,keyword,index\n2026-10-01,검사용,20\n2026-10-01,검사용,30"):
            with self.assertRaises(InputError):read_datalab_csv(bad)
    def test_refresh_archives_snapshot_and_requires_new_choice(self):
        p=self.collect();p=self.store.mutate("select",{"version":p["version"],"request_id":"select","candidate_id":"rank-1"})
        p=self.store.mutate("collect",{"version":p["version"],"request_id":"refresh"},parse_public(HTML))
        self.assertEqual(len(p["history"]),1);self.assertIsNone(p["selection"])

    def test_research_requires_matching_topic_and_plan_approval_persists(self):
        research=json.loads(Path(__file__).with_name("maltipoo-research.json").read_text(encoding="utf-8"))
        p=self.collect()
        with self.assertRaises(InputError):self.store.mutate("research",{"version":p["version"],"request_id":"early","research":research})
        p=self.store.mutate("select",{"version":p["version"],"request_id":"select","candidate_id":"rank-1"})
        before=self.store.get()
        wrong=dict(research,keyword="다른 소재")
        with self.assertRaises(InputError):self.store.mutate("research",{"version":p["version"],"request_id":"wrong","research":wrong})
        self.assertEqual(before,self.store.get())
        p=self.store.mutate("research",{"version":p["version"],"request_id":"research","research":research})
        self.assertIsNone(p["research"]["approval"])
        with self.assertRaises(InputError):self.store.mutate("approve_plan",{"version":p["version"],"request_id":"invalid","title_index":True})
        request={"version":p["version"],"request_id":"approve","title_index":1}
        p=self.store.mutate("approve_plan",request)
        self.assertEqual(self.store.mutate("approve_plan",request),p)
        self.assertEqual(Store(self.store.path).get()["research"]["approval"]["title_index"],1)
        p=self.store.mutate("collect",{"version":p["version"],"request_id":"refresh"},parse_public(HTML))
        self.assertIsNone(p["research"])

    def test_unbacked_outline_is_rejected_without_replacing_data(self):
        research=json.loads(Path(__file__).with_name("maltipoo-research.json").read_text(encoding="utf-8"))
        p=self.collect();p=self.store.mutate("select",{"version":p["version"],"request_id":"select","candidate_id":"rank-1"})
        research["outline"][0]["source_ids"]=["unknown"]
        before=self.store.get()
        with self.assertRaises(InputError):self.store.mutate("research",{"version":p["version"],"request_id":"missing-source","research":research})
        self.assertEqual(before,self.store.get())

if __name__=="__main__":unittest.main()
