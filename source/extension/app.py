"""Isolated dog-blog studio: public trends -> human topic selection -> research brief."""
import argparse
import json
import sqlite3
import uuid
from contextlib import contextmanager
from pathlib import Path
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from urllib.parse import urlparse
from trends import fetch_public,candidates,read_datalab_csv,InputError
from research import validate_research
from content import validate_content,audit,article_html,export_zip
from card_editor import apply_editor,valid_asset_set,font_path,FONTS
from editor_options import options as editor_options

ROOT=Path(__file__).resolve().parent

class Store:
    def __init__(self,path):
        path.parent.mkdir(parents=True,exist_ok=True);self.path=path
        with self.db() as db:
            db.execute("CREATE TABLE IF NOT EXISTS state(id INTEGER PRIMARY KEY,body TEXT NOT NULL)")
            db.execute("CREATE TABLE IF NOT EXISTS requests(id TEXT PRIMARY KEY,input TEXT NOT NULL,result TEXT NOT NULL)")
            db.execute("INSERT OR IGNORE INTO state VALUES(1,?)",(json.dumps({"version":1,"status":"needs_trends","snapshot":None,"history":[],"datalab":None,"selection":None,"error":None},ensure_ascii=False),))
    @contextmanager
    def db(self):
        db=sqlite3.connect(self.path,timeout=10)
        try:
            with db:yield db
        finally:db.close()
    def get(self):
        with self.db() as db:state=json.loads(db.execute("SELECT body FROM state WHERE id=1").fetchone()[0])
        state["candidates"]=candidates(state["snapshot"] or {})
        return state
    def mutate(self,action,data,snapshot=None):
        rid=data.get("request_id")
        if not isinstance(rid,str) or not 1<=len(rid)<=120:raise InputError("요청 번호가 없어요. 다시 조작해 주세요.")
        signature=json.dumps([action,data],ensure_ascii=False,sort_keys=True)
        with self.db() as db:
            db.execute("BEGIN IMMEDIATE")
            prior=db.execute("SELECT input,result FROM requests WHERE id=?",(rid,)).fetchone()
            if prior:
                if prior[0]!=signature:raise InputError("같은 요청 번호로 다른 내용을 저장할 수 없어요.")
                return json.loads(prior[1])
            p=json.loads(db.execute("SELECT body FROM state WHERE id=1").fetchone()[0])
            if data.get("version")!=p["version"]:raise InputError("화면이 지난 버전이에요. 새로고침한 뒤 다시 선택해 주세요.")
            if action=="collect":
                if not snapshot:raise InputError("수집한 자료가 없어요.")
                if p["snapshot"]:p["history"]=(p["history"]+[p["snapshot"]])[-10:]
                p.update(snapshot=snapshot,status="choose_topic",selection=None,research=None,content=None,error=None)
            elif action=="select":
                item=next((c for c in candidates(p["snapshot"] or {}) if c["id"]==data.get("candidate_id")),None)
                if not item:raise InputError("현재 자료에 있는 소재를 선택해 주세요.")
                angle=data.get("angle",item["angle"])
                if not isinstance(angle,str) or not 1<=len(angle.strip())<=300:raise InputError("글의 관점을 1~300자로 적어 주세요.")
                p.update(selection={**item,"angle":angle.strip(),"snapshot_date":p["snapshot"]["snapshot_date"],"source_url":p["snapshot"]["source_url"]},status="topic_selected",research=None,content=None,error=None)
            elif action=="research":
                p["research"]=validate_research(data.get("research"),p.get("selection"))
                p.update(status="plan_review",content=None,error=None)
            elif action=="approve_plan":
                research=p.get("research")
                if not research:raise InputError("확인할 기획이 없어요. 소재와 조사 자료를 먼저 준비해 주세요.")
                title=data.get("title_index")
                if type(title)!=int or not 0<=title<len(research["titles"]):raise InputError("제목 후보를 선택해 주세요.")
                research["approval"]={"title_index":title,"title":research["titles"][title],"revision":research["revision"]}
                p.update(status="plan_approved",content=None,error=None)
            elif action=="content":
                p["content"]=validate_content(data.get("content"),p.get("research"))
                p.update(status="content_review",error=None)
            elif action in ("init_editor","save_layout","save_layouts"):
                c=p.get("content")
                if not c:raise InputError("편집할 카드뉴스가 없어요.")
                if action=="save_layouts" and not isinstance(data.get("layouts"),list):raise InputError("전체10장의 배치를 보내 주세요.")
                if action=="save_layout" and (type(data.get("order"))!=int or not 1<=data["order"]<=10):raise InputError("저장할 카드 번호를 확인해 주세요.")
                if action=="init_editor" and c.get("card_editor"):raise InputError("이미 편집 배치가 있어요. 화면을 새로고침해 주세요.")
                if not c.get("card_editor"):
                    originals=json.loads((ROOT/"maltipoo-content.json").read_text(encoding="utf-8"))
                    for item in c["images"]:item["alt"]=originals["images"][item["order"]-1]["alt"]
                if action=="save_layouts" and not c.get("card_editor"):raise InputError("먼저 편집기를 열어 배치를 준비해 주세요.")
                c=apply_editor(c,ROOT,data.get("order") if action=="save_layout" else None,data.get("layout"),batch=data.get("layouts") if action=="save_layouts" else None,font_style=data.get("font_style"),font_bases=data.get("font_bases"))
                p["content"]=validate_content(c,p.get("research"));p.update(status="content_review",error=None)
            elif action=="edit_content":
                c=p.get("content")
                if not c:raise InputError("수정할 원고가 없어요.")
                c["title"]=data.get("title",c["title"])
                for field in ("intro","sections","checklist","closing","hashtags"):
                    if field in data:c[field]=data[field]
                if "avoid_terms" in data:
                    terms=data["avoid_terms"]
                    if not isinstance(terms,list) or len(terms)>100 or not all(isinstance(t,str) and 1<=len(t)<=80 for t in terms):raise InputError("회피어는 1~80자로 100개까지 적어 주세요.")
                    c["writing_settings"]["custom_avoid_terms"]=terms
                c["revision"]+=1;p["content"]=validate_content(c,p.get("research"))
                p.update(status="content_review",error=None)
            elif action=="approve_content":
                c=p.get("content")
                if not c:raise InputError("검수할 원고가 없어요.")
                a=audit(c)
                if a["findings"]:raise InputError("점검된 표현을 확인·수정한 뒤 승인해 주세요.")
                c["approval"]={"revision":c["revision"],"checked_by":"user","note":"원고·이미지 최종 검수 승인 · 네이버 미발행"}
                relationship=data.get("commercial_relationship")
                if relationship is not None:
                    if relationship not in ("none","present","unknown"):raise InputError("협찬·광고 관계 확인값을 확인해 주세요.")
                    c["approval"]["commercial_relationship"]=relationship
                p.update(status="content_approved",error=None)
            elif action=="datalab":
                if not isinstance(data.get("csv"),str) or len(data["csv"])>500000:raise InputError("가져올 표의 크기를 확인해 주세요.")
                p["datalab"]=read_datalab_csv(data["csv"]);p["error"]=None
            else:raise InputError("지원하지 않는 작업이에요.")
            p["version"]+=1
            db.execute("UPDATE state SET body=? WHERE id=1",(json.dumps(p,ensure_ascii=False),))
            result={**p,"candidates":candidates(p["snapshot"] or {})}
            db.execute("INSERT INTO requests VALUES(?,?,?)",(rid,signature,json.dumps(result,ensure_ascii=False)))
            return result

class Handler(BaseHTTPRequestHandler):
    def json(self,value,status=200):
        raw=json.dumps(value,ensure_ascii=False).encode();self.send_response(status);self.send_header("Content-Type","application/json; charset=utf-8");self.send_header("Content-Length",str(len(raw)));self.send_header("Cache-Control","no-store");self.end_headers();self.wfile.write(raw)
    def do_GET(self):
        path=urlparse(self.path).path
        if path=="/api/state":return self.json(self.server.store.get())
        if path=="/api/health":return self.json({"ok":True,"app":"dog-blog-studio","version":"0.1"})
        if path=="/api/editor-options":return self.json(editor_options())
        if path.startswith("/font-study/"):
            name=path.removeprefix("/font-study/") or "index.html"
            allowed={"index.html","serif.png","sans.png","hand.png","overview.jpg","body.html"}
            allowed.update(f"body-{n:02d}-{style}.png" for n in (4,7) for style in ("serif","sans","hand"))
            allowed.update(f"body-{n:02d}-overview.jpg" for n in (4,7))
            if name not in allowed:return self.json({"error":"없는 조합 예시입니다."},404)
            file=ROOT/"output/font-study-v1"/name
            if not file.is_file():return self.json({"error":"조합 예시를 준비 중입니다."},404)
            return self.raw(file.read_bytes(),{".html":"text/html; charset=utf-8",".png":"image/png",".jpg":"image/jpeg"}[file.suffix])
        if path in ("/editor/","/editor/index.html","/editor/editor.js","/editor/editor.css"):
            name={"/editor/":"editor.html","/editor/index.html":"editor.html","/editor/editor.js":"editor.js","/editor/editor.css":"editor.css"}[path]
            mime={".html":"text/html; charset=utf-8",".js":"text/javascript; charset=utf-8",".css":"text/css; charset=utf-8"}[Path(name).suffix]
            return self.raw((ROOT/"web"/name).read_bytes(),mime)
        if path=="/editor/font.ttf":return self.raw(font_path().read_bytes(),"font/ttf")
        if path.startswith("/editor/fonts/"):
            name=path.removeprefix("/editor/fonts/")
            allowed={f"{family}-{weight}.ttf":(family,weight) for family in FONTS for weight in (400,700)}
            if name not in allowed:return self.json({"error":"없는 글꼴입니다."},404)
            return self.raw(font_path(*allowed[name]).read_bytes(),"font/ttf")
        if path.startswith("/editor-original/"):
            name=path.removeprefix("/editor-original/")
            if name not in {f"{n:02d}.png" for n in range(1,11)}:return self.json({"error":"없는 원본입니다."},404)
            return self.raw((ROOT/"output/maltipoo-v1/backgrounds"/name).read_bytes(),"image/png")
        if path.startswith("/style-study/"):
            name=path.removeprefix("/style-study/") or "index.html"
            if name not in {"index.html","A.png","B.png","C.png","D.png","overview.jpg"}:return self.json({"error":"없는 비교 자료예요."},404)
            file=ROOT/"output/style-study-v1"/name
            if not file.is_file():return self.json({"error":"비교안을 준비 중입니다."},404)
            mime={".html":"text/html; charset=utf-8",".png":"image/png",".jpg":"image/jpeg"}[file.suffix]
            return self.raw(file.read_bytes(),mime)
        if path in ("/api/article-preview","/api/export"):
            p=self.server.store.get();c=p.get("content")
            if not c:return self.json({"error":"원고가 아직 없어요."},409)
            if path=="/api/article-preview":
                return self.raw(article_html(c,p["research"]["sources"],"/assets/"+c.get("asset_set","maltipoo-v1")+"/").encode(),"text/html; charset=utf-8")
            try:return self.raw(export_zip(p,ROOT),"application/zip",'attachment; filename="maltipoo-blog-review.zip"')
            except InputError as e:return self.json({"error":str(e)},409)
        if path.startswith("/assets/") and len(path.split("/",3))==4:
            _,_,asset_set,name=path.split("/",3)
            if not valid_asset_set(asset_set):return self.json({"error":"없는 이미지 버전입니다."},404)
            if name not in {f"{i:02d}.png" for i in range(1,11)}:return self.json({"error":"없는 이미지예요."},404)
            file=ROOT/"output"/asset_set/name
            if not file.is_file():return self.json({"error":"이미지 제작 중입니다."},404)
            return self.raw(file.read_bytes(),"image/png")
        if path=="/api/brief":
            p=self.server.store.get()
            if not p["selection"]:return self.json({"error":"소재를 먼저 선택해 주세요."},409)
            return self.json({"audience":"강아지 보호자","publication":"사용자가 네이버에 직접 등록","selected_topic":p["selection"],"snapshot":p["snapshot"],"datalab":p["datalab"],"research":p.get("research"),"content":p.get("content"),"next":"원고·이미지 검수 후 직접 발행","article_generated":bool(p.get("content"))})
        static={"/":"index.html","/app.js":"app.js","/style.css":"style.css"}
        if path not in static:return self.json({"error":"찾을 수 없는 주소입니다."},404)
        file=ROOT/"web"/static[path];raw=file.read_bytes();mime={".html":"text/html",".js":"text/javascript",".css":"text/css"}[file.suffix]
        self.send_response(200);self.send_header("Content-Type",mime+"; charset=utf-8");self.send_header("Content-Length",str(len(raw)));self.end_headers();self.wfile.write(raw)
    def raw(self,raw,mime,disposition=None):
        self.send_response(200);self.send_header("Content-Type",mime);self.send_header("Content-Length",str(len(raw)));self.send_header("Cache-Control","no-store")
        if disposition:self.send_header("Content-Disposition",disposition)
        self.end_headers();self.wfile.write(raw)
    def do_POST(self):
        try:
            if self.headers.get("Origin") and self.headers["Origin"]!="http://"+self.headers.get("Host",""):return self.json({"error":"다른 사이트에서 보낸 요청은 처리하지 않습니다."},403)
            length=int(self.headers.get("Content-Length","0"))
            if not 0<length<=600000:raise InputError("요청 크기를 확인해 주세요.")
            data=json.loads(self.rfile.read(length))
            if not isinstance(data,dict):raise InputError("요청 형식이 올바르지 않아요.")
            action=urlparse(self.path).path.removeprefix("/api/")
            snapshot=fetch_public() if action=="collect" else None
            self.json(self.server.store.mutate(action,data,snapshot))
        except (InputError,ValueError) as e:self.json({"error":str(e)},400)
        except Exception:self.json({"error":"요청을 처리하지 못했어요. 이전 저장 자료는 유지됩니다."},500)
    def log_message(self,*args):pass

def main():
    parser=argparse.ArgumentParser();parser.add_argument("--port",type=int,default=8770);parser.add_argument("--data-dir",type=Path,default=ROOT/"data")
    args=parser.parse_args();server=ThreadingHTTPServer(("127.0.0.1",args.port),Handler);server.store=Store(args.data_dir/"studio.sqlite3")
    print(f"Dog blog studio http://127.0.0.1:{args.port}",flush=True)
    try:server.serve_forever()
    except KeyboardInterrupt:pass
    finally:server.server_close()

if __name__=="__main__":main()
