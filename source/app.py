"""Local card-news app with explicit mock/live Claude CLI modes."""
import argparse
import json
import sqlite3
import shutil
import hashlib
from contextlib import contextmanager
import uuid
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse
from jobs import JobManager, RUNNING
from image_assets import import_background, ImageAssetError
from render import render_card, default_layout, checked_layout, input_hash, RenderError
from export import build_export, verify_export

ROOT = Path(__file__).resolve().parent
KST = timezone(timedelta(hours=9))
STATIC = {"/": ("index.html", "text/html"), "/app.js": ("app.js", "text/javascript"), "/style.css": ("style.css", "text/css")}
BOARD_STATES = ("storyboard_ready", "storyboard_approved", "images_partial", "images_ready", "final_approved")
IMAGE_STATES = ("storyboard_approved", "images_partial", "images_ready", "final_approved")


class Problem(Exception):
    def __init__(self, status, message):
        self.status, self.message = status, message


class Store:
    def __init__(self, path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        with self.connect() as db:
            db.execute("CREATE TABLE IF NOT EXISTS projects (id TEXT PRIMARY KEY, body TEXT NOT NULL)")
            db.execute("CREATE TABLE IF NOT EXISTS requests (project TEXT, id TEXT, signature TEXT, result TEXT, PRIMARY KEY(project,id))")

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=15)
        try:
            with db:
                yield db
        finally:
            db.close()

    def list(self):
        with self.connect() as db:
            rows = db.execute("SELECT body FROM projects ORDER BY rowid DESC").fetchall()
        return [{k: p[k] for k in ("id", "topic", "status", "created_at")} for (body,) in rows for p in [json.loads(body)]]

    def get(self, project_id):
        with self.connect() as db:
            return self._get(db, project_id)

    def _get(self, db, project_id):
        row = db.execute("SELECT body FROM projects WHERE id=?", (project_id,)).fetchone()
        if not row:
            raise Problem(404, "프로젝트를 찾을 수 없습니다.")
        return json.loads(row[0])

    def create(self, data):
        topic = data.get("topic", "")
        if not isinstance(topic, str) or not 1 <= len(topic.strip()) <= 120:
            raise Problem(400, "주제를 1~120자로 입력해 주세요.")
        mode = data.get("mode", "mock")
        if mode not in ("mock", "claude"):
            raise Problem(400, "모드는 mock 또는 claude여야 합니다.")
        now = datetime.now(KST)
        titles = ["새 AI 도우미의 기능 변화", "AI 학습 도구의 활용 사례", "이미지 도구의 새로운 편집 방식", "AI 검색의 출처 확인 방식", "개발 도구의 작업 자동화", "AI 서비스의 사용 조건 비교"]
        p = {"id": uuid.uuid4().hex, "topic": topic.strip(), "mode": "mock", "version": 1,
             "status": "selecting", "created_at": now.isoformat(), "updated_at": now.isoformat(),
             "period": {"timezone": "Asia/Seoul", "as_of": now.isoformat(), "start": (now - timedelta(days=6)).date().isoformat(), "end": now.date().isoformat()},
             "audience": "AI 입문자", "formats": ["목록형", "이야기형"], "selected_ids": [],
             "question": None, "answer": None, "continuation_count": 0,
             "candidates": [{"id": f"mock-{i+1}", "title": t if topic.strip() == "AI 최신소식" else f"{topic.strip()} · 예시 {i+1}",
                             "category": ["제품", "교육", "이미지", "검색", "개발", "이용 조건"][i],
                             "summary": "화면 흐름을 확인하기 위한 가상 소식입니다. 실제 발표나 출시를 뜻하지 않습니다.",
                             "value": "입문자에게 무엇이 달라지고 어떤 조건을 확인해야 하는지 설명하는 구성 연습",
                             "uncertainty": "실제 조사 전: 원문·게시일·발표일·기능 모두 미확인", "source_url": None, "published_at": None, "event_at": None}
                            for i, t in enumerate(titles)]}
        p.update(engine_session_id=None, events=[], read_urls=[], research_notes="", editorial_brief=None,
                 run_id=None, job_stage=None, error=None)
        if mode == "claude":
            p.update(mode="claude", status="ready", candidates=[])
        with self.connect() as db:
            db.execute("INSERT INTO projects VALUES (?,?)", (p["id"], json.dumps(p, ensure_ascii=False)))
        return p

    def mutate(self, project_id, action, data):
        request_id = data.get("request_id")
        if not isinstance(request_id, str) or not 1 <= len(request_id) <= 120:
            raise Problem(400, "request_id가 필요합니다.")
        signature_data = json.dumps([action, data], ensure_ascii=False, sort_keys=True)
        signature = hashlib.sha256(signature_data.encode("utf-8")).hexdigest()
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            cached = db.execute("SELECT signature,result FROM requests WHERE project=? AND id=?", (project_id, request_id)).fetchone()
            if cached:
                if cached[0] not in (signature, signature_data):
                    raise Problem(409, "같은 요청 번호에 다른 내용을 보낼 수 없습니다.")
                return json.loads(cached[1])
            p = self._get(db, project_id)
            # Repeated delivery of an identical answer is safe, even with a new request ID.
            repeated = (action == "answers" and p["answer"] is not None and
                        data.get("question_id") == p["answer"]["question_id"] and
                        data.get("question_version") == p["answer"]["question_version"] and
                        data.get("answer") == p["answer"]["text"])
            if not repeated:
                if data.get("version") != p["version"]:
                    raise Problem(409, "이전 화면의 요청입니다. 최신 상태를 불러온 뒤 다시 시도해 주세요.")
                if action in ("research", "expand", "retry"):
                    if p["mode"] != "claude":
                        raise Problem(409, "실제 조사 모드의 프로젝트에서 실행해 주세요.")
                    if action == "research" and p["status"] != "ready":
                        raise Problem(409, "이미 시작한 조사입니다.")
                    if action == "retry" and p["status"] not in ("error", "interrupted", "cancelled"):
                        raise Problem(409, "재시도할 실패 또는 중단 작업이 없습니다.")
                    if action == "expand":
                        if p["status"] != "selecting" or len(p["candidates"]) >= 7 or p["period"].get("days", 7) != 7:
                            raise Problem(409, "7일 조사에서 후보가 부족할 때 30일로 넓힐 수 있습니다.")
                        p["period"]["start"] = (datetime.fromisoformat(p["period"]["as_of"]) - timedelta(days=29)).date().isoformat()
                        p["period"]["days"] = 30
                        p["selected_ids"] = []
                    stage = p["job_stage"] if action == "retry" else "research"
                    self.start_job(p, stage)
                elif action == "cancel":
                    if p["status"] not in RUNNING:
                        raise Problem(409, "실행 중인 작업이 없습니다.")
                    p.update(status="cancelled", error="작업을 취소했습니다. 기존 결과와 선택은 보존했습니다.")
                elif action == "preferences":
                    if p["status"] not in ("selecting", "brief_ready"):
                        raise Problem(409, "소식 선택 또는 편집안 확인 단계에서 설정해 주세요.")
                    goal, size = data.get("editorial_goal"), data.get("card_size")
                    if not isinstance(goal, str) or not 1 <= len(goal.strip()) <= 500 or size not in ("1080x1350", "1080x1080"):
                        raise Problem(400, "전달 목적과 카드 크기를 확인해 주세요.")
                    if p["status"] == "brief_ready" and goal.strip() != p.get("editorial_goal", (p.get("answer") or {}).get("text")):
                        raise Problem(409, "이미 만든 편집안과 다른 목적은 새 프로젝트에서 시작해 주세요.")
                    p.update(editorial_goal=goal.strip(), card_size=size)
                elif action == "storyboard":
                    if p["mode"] != "claude" or p["status"] not in ("brief_ready",) + BOARD_STATES or not p.get("editorial_brief"):
                        raise Problem(409, "실제 조사 편집안을 확인한 뒤 기획을 만들 수 있습니다.")
                    size = data.get("card_size", p.get("card_size"))
                    feedback = data.get("feedback", "")
                    if size not in ("1080x1350", "1080x1080") or not isinstance(feedback, str) or len(feedback) > 1000:
                        raise Problem(400, "카드 크기와 1000자 이내 피드백을 확인해 주세요.")
                    p.update(card_size=size, storyboard_feedback=feedback)
                    self.start_job(p, "storyboard")
                elif action == "edit-card":
                    board = p.get("storyboard")
                    if p["status"] not in BOARD_STATES or not board or data.get("storyboard_version") != board["version"]:
                        raise Problem(409, "현재 기획 버전에서 수정해 주세요.")
                    card = next((c for c in board["cards"] if c["id"] == data.get("card_id")), None)
                    if not card:
                        raise Problem(404, "수정할 카드를 찾지 못했습니다.")
                    for key, maximum in (("title", 45), ("message", 75), ("body", 180)):
                        if not isinstance(data.get(key), str) or not 1 <= len(data[key].strip()) <= maximum:
                            raise Problem(400, f"{key} 문구를 1~{maximum}자로 입력해 주세요.")
                    p["storyboard_history"] = (p.get("storyboard_history", []) + [json.loads(json.dumps(board))])[-20:]
                    card.update({key: data[key].strip() for key in ("title", "message", "body")})
                    card["edited_by_user"] = True
                    board["version"] += 1
                    board["approved_version"] = None
                    p["status"] = "storyboard_ready"
                elif action == "approve" and data.get("stage") == "final":
                    self.refresh_renders(p)
                    board, renders = p.get("storyboard"), p.get("renders", {})
                    if not board or board.get("approved_version") != board["version"] or p["status"] != "images_ready":
                        raise Problem(409, "기획 승인과 모든 카드의 배경 준비가 끝난 뒤 최종 승인할 수 있습니다.")
                    if data.get("render_signature") != self.render_signature(p):
                        raise Problem(409, "화면에서 본 카드와 현재 카드가 다릅니다. 새로고침한 뒤 다시 확인해 주세요.")
                    if any(x["level"] == "error" for c in board["cards"] for x in renders[c["id"]]["checks"]):
                        raise Problem(409, "글자가 잘린 카드가 있어 최종 승인할 수 없습니다. 문구나 글자 배치를 고쳐 주세요.")
                    p["final_approval"] = {"signature": self.render_signature(p), "approved_at": datetime.now(KST).isoformat(),
                                           "storyboard_version": board["version"]}
                    p["final_approval"]["export_path"] = build_export(self.path.parent, p)
                    p.update(status="final_approved", export_check=None)
                elif action == "approve":
                    board = p.get("storyboard")
                    if data.get("stage") != "storyboard" or not board or data.get("storyboard_version") != board["version"] or p["status"] not in ("storyboard_ready", "storyboard_approved"):
                        raise Problem(409, "현재 스토리보드를 확인한 뒤 승인해 주세요.")
                    board["approved_version"] = board["version"]
                    p["status"] = self.image_status(p)
                elif action == "layout-card":
                    board = p.get("storyboard")
                    if p["status"] not in BOARD_STATES or not board or not any(c["id"] == data.get("card_id") for c in board["cards"]):
                        raise Problem(409, "현재 기획의 카드에서 글자 배치를 바꿔 주세요.")
                    try:
                        p.setdefault("layouts", {})[data["card_id"]] = checked_layout(data)
                    except RenderError as e:
                        raise Problem(400, str(e))
                elif action == "fix-card":
                    board = p.get("storyboard")
                    card = next((c for c in (board or {}).get("cards", []) if c["id"] == data.get("card_id")), None)
                    request, scope = data.get("request"), data.get("scope")
                    if p["status"] not in IMAGE_STATES or not board or board.get("approved_version") != board["version"] or data.get("storyboard_version") != board["version"]:
                        raise Problem(409, "승인한 현재 기획에서 카드를 골라 고쳐 주세요.")
                    if not card:
                        raise Problem(404, "고칠 카드를 찾지 못했습니다.")
                    if not isinstance(request, str) or not 1 <= len(request.strip()) <= 500 or scope not in ("auto", "text", "image"):
                        raise Problem(400, "카드 번호와 문제, 원하는 결과를 500자 이내로 적고 고칠 범위를 골라 주세요.")
                    p["card_fix"] = {"card_id": card["id"], "order": card["order"], "request": request.strip(), "scope": scope,
                                     "storyboard_version": board["version"]}
                    if scope == "image":
                        if p.get("image_results", {}).get(card["id"], {}).get("status") != "ready":
                            raise Problem(409, "이 카드에는 다시 만들 배경이 아직 없습니다. 먼저 배경을 가져와 주세요.")
                        self.request_new_image(p, card["id"], request.strip())
                    else:
                        if p["mode"] != "claude":
                            raise Problem(409, "문구 고치기는 실제 조사 모드의 프로젝트에서 실행해 주세요.")
                        self.start_job(p, "card_fix")
                elif action == "verify-export":
                    if p["status"] != "final_approved" or not p.get("final_approval"):
                        raise Problem(409, "최종 승인한 뒤 내보낸 파일을 검사할 수 있습니다.")
                    p["export_check"] = verify_export(self.path.parent, p)
                elif action == "import-image":
                    board = p.get("storyboard")
                    if not board or board.get("approved_version") != board["version"] or p["status"] not in IMAGE_STATES:
                        raise Problem(409, "현재 기획을 승인한 뒤 이미지를 가져와 주세요.")
                    try:
                        record = import_background(self.path.parent, p, data)
                    except ImageAssetError as e:
                        raise Problem(400, str(e))
                    p.setdefault("image_results", {})[data["card_id"]] = record
                    p["status"] = self.image_status(p)
                elif action == "selection":
                    if p["status"] != "selecting":
                        raise Problem(409, "후보 선택이 이미 확정되었습니다.")
                    ids = data.get("candidate_ids")
                    valid = {c["id"] for c in p["candidates"]}
                    if not isinstance(ids, list) or not all(isinstance(x, str) for x in ids) or len(ids) > 3 or len(set(ids)) != len(ids) or not set(ids) <= valid:
                        raise Problem(400, "현재 프로젝트의 후보를 최대 3개 골라 주세요.")
                    p["selected_ids"] = ids
                elif action == "next":
                    if p["status"] != "selecting" or not 1 <= len(p["selected_ids"]) <= 3:
                        raise Problem(409, "소식 1~3개를 선택한 뒤 진행해 주세요.")
                    if p["mode"] == "claude":
                        self.start_job(p, "verify")
                    else:
                        p["status"] = "waiting_for_user"
                        p["question"] = {"id": uuid.uuid4().hex, "version": 1,
                                     "text": "AI 입문자에게 어떤 도움을 주고 싶나요?",
                                     "options": [{"value": "변화 이해하기", "detail": "무엇이 왜 달라졌는지 쉬운 흐름으로 설명합니다.", "recommended": True},
                                                 {"value": "직접 써보기", "detail": "시작 방법과 이용 조건을 먼저 안내합니다.", "recommended": False}],
                                     "recommendation": "처음 접하는 독자가 변화의 의미를 파악하기에 좋아요. 추천은 자동 선택되지 않습니다."}
                elif action == "answers":
                    q = p["question"]
                    if p["status"] != "waiting_for_user" or not q or data.get("question_id") != q["id"] or data.get("question_version") != q["version"]:
                        raise Problem(409, "이미 처리했거나 현재 질문과 다른 답변입니다.")
                    answer = data.get("answer")
                    if not isinstance(answer, str) or not 1 <= len(answer.strip()) <= 500:
                        raise Problem(400, "선택지를 고르거나 원하는 방향을 500자 이내로 적어 주세요.")
                    p["answer"] = {"question_id": q["id"], "question_version": q["version"], "text": answer.strip()}
                    if p["mode"] == "claude":
                        self.start_job(p, "continue")
                    else:
                        p["status"] = "brief_ready"
                    p["continuation_count"] += 1
                else:
                    raise Problem(404, "지원하지 않는 작업입니다.")
                self.refresh_renders(p)
                p["version"] += 1
                p["updated_at"] = datetime.now(KST).isoformat()
                db.execute("UPDATE projects SET body=? WHERE id=?", (json.dumps(p, ensure_ascii=False), project_id))
            result = json.dumps(p, ensure_ascii=False)
            db.execute("INSERT INTO requests VALUES (?,?,?,?)", (project_id, request_id, signature, result))
        return p

    def refresh_all(self):
        """Card PNGs are derived from saved text, layout and backgrounds, so they can be rebuilt at startup."""
        for summary in self.list():
            with self.connect() as db:
                db.execute("BEGIN IMMEDIATE")
                p = self._get(db, summary["id"])
                if p.get("storyboard") and p["status"] not in RUNNING:
                    before = p.get("render_signature")
                    self.refresh_renders(p)
                    if p.get("render_signature") != before:
                        db.execute("UPDATE projects SET body=? WHERE id=?", (json.dumps(p, ensure_ascii=False), p["id"]))

    def image_status(self, p):
        cards = (p.get("storyboard") or {}).get("cards", [])
        count = sum(p.get("image_results", {}).get(c["id"], {}).get("status") == "ready" for c in cards)
        return "images_ready" if cards and count == len(cards) else "images_partial" if count else "storyboard_approved"

    def request_new_image(self, p, card_id, reason):
        old = p["image_results"][card_id]
        p["image_history"] = (p.get("image_history", []) + [dict(old, card_id=card_id)])[-50:]
        p["image_results"][card_id] = {"status": "needs_image", "reason": reason, "previous_generator": old.get("generator"),
                                       "previous_prompt": old.get("prompt", ""), "requested_at": datetime.now(KST).isoformat()}
        p["status"] = self.image_status(p)

    def render_signature(self, p):
        board = p.get("storyboard") or {}
        shas = [p.get("renders", {}).get(c["id"], {}).get("sha256") for c in board.get("cards", [])]
        return hashlib.sha256(json.dumps([board.get("version"), shas]).encode()).hexdigest()

    def refresh_renders(self, p):
        """Re-render only cards whose text, layout or background changed; others keep identical files."""
        board = p.get("storyboard")
        if not board:
            return
        data_root, renders = self.path.parent, p.get("renders", {})
        meta = {"card_size": board.get("card_size") or p.get("card_size") or "1080x1350", "as_of": p["period"]["as_of"][:10],
                "total": len(board["cards"])}
        kept = {}
        for card in board["cards"]:
            image = p.get("image_results", {}).get(card["id"], {})
            if image.get("status") != "ready":
                continue
            layout = p.get("layouts", {}).get(card["id"]) or default_layout(card)
            card_meta = dict(meta, source=card["source_urls"][0].split("://", 1)[-1].rstrip("/"))
            key = input_hash(card, layout, image, card_meta)
            if renders.get(card["id"], {}).get("input_hash") == key:
                kept[card["id"]] = renders[card["id"]]
                continue
            raw, checks = render_card(data_root / image["relative_path"], card, layout, card_meta)
            sha = hashlib.sha256(raw).hexdigest()
            relative = Path("renders") / p["id"] / card["id"] / (sha + ".png")
            (data_root / relative).parent.mkdir(parents=True, exist_ok=True)
            if not (data_root / relative).exists():
                (data_root / relative).write_bytes(raw)
            kept[card["id"]] = {"relative_path": relative.as_posix(), "sha256": sha, "input_hash": key, "layout": layout,
                                "checks": checks, "background_sha256": image["sha256"], "storyboard_version": board["version"],
                                "rendered_at": datetime.now(KST).isoformat()}
        p["renders"] = kept
        p["render_signature"] = self.render_signature(p)
        approval = p.get("final_approval")
        if approval and approval["signature"] != self.render_signature(p):
            p.update(final_approval=None, export_check=None)
            if p["status"] == "final_approved":
                p["status"] = self.image_status(p)
        elif approval and p["status"] == "images_ready":
            # Re-importing the identical background leaves the approved cards unchanged.
            p["status"] = "final_approved"

    def start_job(self, p, stage):
        p.update(status={"research": "researching", "verify": "verifying", "continue": "continuing", "storyboard": "planning", "card_fix": "revising"}[stage],
                 run_id=uuid.uuid4().hex, job_stage=stage, error=None)
        p["events"] = (p.get("events", []) + [{"research": "실제 웹 조사를 시작합니다.", "verify": "선택한 소식의 원문과 사용 조건을 확인합니다.", "continue": "사용자 답변을 같은 Claude 세션에 전달합니다.", "storyboard": "확인한 사실을 카드별 기획과 그림 계획으로 구성합니다.", "card_fix": "고칠 카드 하나의 요청을 같은 Claude 세션에 전달합니다."}[stage]])[-100:]


class Handler(BaseHTTPRequestHandler):
    def send_json(self, status, value):
        raw = json.dumps(value, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(raw)

    def send_file(self, path, mime, download_name=None):
        data_root = self.server.store.path.parent.resolve()
        path = Path(path).resolve()
        if not path.is_relative_to(data_root) or not path.is_file():
            raise Problem(404, "파일을 찾지 못했습니다.")
        raw = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        if download_name:
            self.send_header("Content-Disposition", f'attachment; filename="{download_name}"')
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):
        path = urlparse(self.path).path
        try:
            if path == "/api/health":
                return self.send_json(200, {"ok": True, "modes": ["mock", "claude"], "claude_available": bool(shutil.which("claude"))})
            if path == "/api/projects":
                return self.send_json(200, self.server.store.list())
            parts = path.strip("/").split("/")
            if len(parts) == 3 and parts[:2] == ["api", "projects"]:
                return self.send_json(200, self.server.store.get(parts[2]))
            if len(parts) == 4 and parts[:2] == ["api", "projects"] and parts[3] == "export.zip":
                p = self.server.store.get(parts[2])
                approval = p.get("final_approval")
                if p["status"] != "final_approved" or not approval:
                    raise Problem(409, "최종 승인한 뒤에 내려받을 수 있습니다.")
                name = f"cardnews-{p['period']['as_of'][:10]}-v{approval['storyboard_version']}.zip"
                return self.send_file(self.server.store.path.parent / approval["export_path"], "application/zip", name)
            if len(parts) == 5 and parts[:2] == ["api", "projects"] and parts[3] == "renders":
                p = self.server.store.get(parts[2])
                card = next((c for c in (p.get("storyboard") or {}).get("cards", []) if c["id"] == parts[4]), None)
                record = p.get("renders", {}).get(parts[4])
                if not card or not record:
                    raise Problem(404, "아직 만든 카드 PNG가 없습니다.")
                download = urlparse(self.path).query == "download=1"
                if download and p["status"] != "final_approved":
                    raise Problem(409, "최종 승인한 뒤에 내려받을 수 있습니다.")
                return self.send_file(self.server.store.path.parent / record["relative_path"], "image/png",
                                      f"card-{card['order']:02d}.png" if download else None)
            if len(parts) == 5 and parts[:2] == ["api", "projects"] and parts[3] == "images":
                p = self.server.store.get(parts[2])
                if not any(c["id"] == parts[4] for c in (p.get("storyboard") or {}).get("cards", [])):
                    raise Problem(404, "현재 기획의 이미지가 아닙니다.")
                record = p.get("image_results", {}).get(parts[4])
                if not record or record.get("status") != "ready":
                    raise Problem(404, "아직 가져온 이미지가 없습니다.")
                data_root = self.server.store.path.parent.resolve()
                image_path = (data_root / record["relative_path"]).resolve()
                if not image_path.is_relative_to(data_root) or not image_path.is_file():
                    raise Problem(404, "이미지 파일을 찾지 못했습니다.")
                raw = image_path.read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", {"PNG": "image/png", "JPEG": "image/jpeg", "WEBP": "image/webp"}[record["format"]])
                self.send_header("Content-Length", str(len(raw)))
                self.send_header("Cache-Control", "no-store")
                self.send_header("X-Content-Type-Options", "nosniff")
                self.end_headers()
                self.wfile.write(raw)
                return
            if path not in STATIC:
                raise Problem(404, "페이지를 찾을 수 없습니다.")
            name, mime = STATIC[path]
            raw = (ROOT / "web" / name).read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", mime + "; charset=utf-8")
            self.send_header("Content-Length", str(len(raw)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Security-Policy", "default-src 'self'; style-src 'self'; script-src 'self'; img-src 'self'; frame-ancestors 'none'")
            self.end_headers()
            self.wfile.write(raw)
        except Problem as e:
            self.send_json(e.status, {"error": e.message})

    def do_POST(self):
        try:
            origin = self.headers.get("Origin")
            if origin and origin != f"http://{self.headers.get('Host')}":
                raise Problem(403, "같은 앱 화면에서 요청해 주세요.")
            path = urlparse(self.path).path
            length = int(self.headers.get("Content-Length", "0"))
            limit = 24 * 1024 * 1024 if path.endswith("/import-image") else 16384
            if not 0 < length <= limit:
                raise Problem(400, "요청 크기가 올바르지 않습니다.")
            data = json.loads(self.rfile.read(length))
            if not isinstance(data, dict):
                raise Problem(400, "JSON 객체가 필요합니다.")
            if path == "/api/projects":
                return self.send_json(201, self.server.store.create(data))
            parts = path.strip("/").split("/")
            if len(parts) == 4 and parts[:2] == ["api", "projects"]:
                result = self.server.store.mutate(parts[2], parts[3], data)
                if parts[3] == "cancel":
                    self.server.jobs.cancel(result.get("run_id"))
                else:
                    self.server.jobs.ensure(result)
                return self.send_json(202 if result["status"] in RUNNING else 200, result)
            raise Problem(404, "지원하지 않는 요청입니다.")
        except Problem as e:
            self.send_json(e.status, {"error": e.message})
        except (ValueError, TypeError):
            self.send_json(400, {"error": "요청 내용을 읽을 수 없습니다."})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--data-dir", type=Path, default=ROOT / "data")
    args = parser.parse_args()
    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    server.store = Store(args.data_dir / "projects.sqlite3")
    server.jobs = JobManager(server.store)
    server.jobs.recover()
    server.store.refresh_all()
    print(f"Card-news app (mock / Claude): http://127.0.0.1:{args.port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.jobs.shutdown()
        server.server_close()


if __name__ == "__main__":
    main()
