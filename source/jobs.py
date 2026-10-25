"""Background jobs and validated state transitions for live Claude research."""
import json
import threading
import time
import uuid
from datetime import date
from engine import (ClaudeEngine, EngineError, RESEARCH_SCHEMA, EDITORIAL_SCHEMA, STORY_SCHEMA, CARD_FIX_SCHEMA,
                    research_prompt, editorial_prompt, storyboard_prompt, card_fix_prompt, valid_url, clean_url)

RUNNING = {"researching", "verifying", "continuing", "planning", "revising"}


def checked_card_fix(data, p):
    fix, board = p["card_fix"], p["storyboard"]
    card = next(c for c in board["cards"] if c["id"] == fix["card_id"])
    if data.get("status") != "card_fixed" or data.get("change") not in ("text", "image") or not isinstance(data.get("reason"), str):
        raise EngineError("카드 고치기 결과 형식이 올바르지 않습니다. 기존 카드를 보존했습니다.")
    if fix["scope"] == "text" and data["change"] != "text":
        raise EngineError("글만 고치기를 요청했는데 그림 수정 결과가 반환됐습니다. 기존 카드를 보존했습니다.")
    if data["change"] == "image":
        if not isinstance(data.get("image_note"), str) or not data["image_note"].strip():
            raise EngineError("그림을 어떻게 다시 만들지 설명이 없습니다. 기존 카드를 보존했습니다.")
        return {"change": "image", "image_note": data["image_note"].strip(), "reason": data["reason"].strip()}
    changed = {}
    for key, maximum in (("title", 45), ("message", 75), ("body", 180)):
        value = data.get(key)
        if not isinstance(value, str) or not 1 <= len(value.strip()) <= maximum:
            raise EngineError(f"고친 {key} 문구가 비어 있거나 {maximum}자를 넘습니다. 기존 카드를 보존했습니다.")
        changed[key] = value.strip()
    if all(changed[k] == card[k] for k in changed):
        raise EngineError("요청을 반영한 문구 변경이 없습니다. 요청을 더 구체적으로 적어 다시 시도해 주세요.")
    others = {c["message"].strip().casefold() for c in board["cards"] if c["id"] != card["id"]}
    if changed["message"].casefold() in others:
        raise EngineError("고친 핵심 문장이 다른 카드와 같습니다. 기존 카드를 보존했습니다.")
    facts = (p.get("editorial_brief") or {}).get("facts", [])
    refs, urls = data.get("fact_refs"), data.get("source_urls")
    if not isinstance(refs, list) or not refs or any(type(i) is not int or not 0 <= i < len(facts) or facts[i]["kind"] == "unknown" for i in refs):
        raise EngineError("고친 문구의 확인된 사실 근거를 찾지 못했습니다. 기존 카드를 보존했습니다.")
    allowed = {clean_url(facts[i]["source_url"]) for i in refs}
    if not isinstance(urls, list) or not urls or any(not valid_url(u) or clean_url(u) not in allowed or clean_url(u) not in p.get("read_urls", []) for u in urls):
        raise EngineError("고친 문구의 출처가 실제 읽은 근거와 일치하지 않습니다. 기존 카드를 보존했습니다.")
    return dict(changed, change="text", fact_refs=refs, source_urls=urls, reason=data["reason"].strip())


def checked_storyboard(data, p):
    cards = data.get("cards")
    if data.get("status") != "storyboard_ready" or not isinstance(cards, list) or not 5 <= len(cards) <= 8:
        raise EngineError("기획은 5~8장의 카드로 구성돼야 합니다. 이전 기획은 보존했습니다.")
    facts = (p.get("editorial_brief") or {}).get("facts", [])
    normalized = []
    for index, card in enumerate(cards):
        if not isinstance(card, dict):
            raise EngineError("카드 기획 형식이 올바르지 않습니다.")
        for key, maximum in (("role", 80), ("title", 45), ("message", 75), ("body", 180), ("image_brief", 1800)):
            value = card.get(key)
            if not isinstance(value, str) or not 1 <= len(value.strip()) <= maximum:
                raise EngineError(f"{index+1}번 카드의 {key} 항목을 확인해 주세요. 문구가 비어 있거나 길이 제한을 초과했습니다.")
        refs = card.get("fact_refs")
        if not isinstance(refs, list) or not refs or any(type(i) is not int or not 0 <= i < len(facts) or facts[i]["kind"] == "unknown" for i in refs):
            raise EngineError(f"{index+1}번 카드의 확인된 사실 근거를 찾지 못했습니다.")
        urls = card.get("source_urls")
        allowed = {clean_url(facts[i]["source_url"]) for i in refs}
        if not isinstance(urls, list) or not urls or any(not valid_url(u) or clean_url(u) not in allowed or clean_url(u) not in p.get("read_urls", []) for u in urls):
            raise EngineError(f"{index+1}번 카드 출처가 실제 읽은 근거와 일치하지 않습니다.")
        normalized.append(dict(card, id=uuid.uuid4().hex, order=index+1, edited_by_user=False))
    messages = [card["message"].strip().casefold() for card in normalized]
    if len(messages) != len(set(messages)):
        raise EngineError("카드별 핵심 메시지가 중복돼 있습니다. 이전 기획을 보존했으니 다시 시도해 주세요.")
    for key in ("format", "design_direction", "review_notes"):
        if not isinstance(data.get(key), str):
            raise EngineError("기획의 형식·디자인·검수 설명이 빠져 있습니다.")
    previous = p.get("storyboard") or {}
    return {"version": previous.get("version", 0)+1, "format": data["format"], "card_size": p.get("card_size"),
            "design_direction": data["design_direction"], "review_notes": data["review_notes"],
            "cards": normalized, "approved_version": None}


def checked_research(data, meta, period):
    if data.get("status") != "research_ready" or not isinstance(data.get("candidates"), list):
        raise EngineError("조사 결과 형식이 올바르지 않습니다.")
    if not meta.get("searched"):
        raise EngineError("실제 WebSearch 호출 기록이 없어 조사 완료로 처리하지 않았습니다.")
    found, seen = [], set()
    for c in data["candidates"][:12]:
        if not isinstance(c, dict):
            raise EngineError("후보 데이터 형식이 올바르지 않습니다.")
        for key in ("title", "summary", "category", "value", "uncertainty", "source_url", "evidence", "event_key"):
            if not isinstance(c.get(key), str) or not c[key].strip() and key not in ("uncertainty",):
                raise EngineError("후보에 필수 항목 또는 근거가 빠져 있습니다.")
        if not valid_url(c["source_url"]):
            raise EngineError("후보 원문 링크가 올바른 HTTPS 주소가 아닙니다.")
        for field in ("published_at", "event_at"):
            if c.get(field) is not None:
                try:
                    date.fromisoformat(c[field])
                except (TypeError, ValueError):
                    raise EngineError("후보 날짜는 YYYY-MM-DD 또는 미확인이어야 합니다.")
        # Event date wins over the date of a newly written recap of old news.
        when = c.get("event_at") or c.get("published_at")
        if when and not period["start"] <= when <= period["end"]:
            continue
        key = c["event_key"].strip().casefold()
        if key in seen:
            continue
        seen.add(key)
        c = dict(c, id=uuid.uuid4().hex)
        c["source_read"] = bool(c.get("source_read") and clean_url(c["source_url"]) in meta.get("read_urls", []))
        if not c["source_read"]:
            c["uncertainty"] = "원문 읽기 미확인. " + c["uncertainty"]
        if not when:
            c["uncertainty"] = "날짜 미확인: 기간 내 소식 여부 미확정. " + c["uncertainty"]
        found.append(c)
    return found, str(data.get("notes", ""))[:3000]


def checked_editorial(data, read_urls, has_answer):
    status = data.get("status")
    if status == "need_input":
        if has_answer:
            raise EngineError("이미 답한 방향 대신 추가 질문이 반환됐습니다. 기존 답을 보존했으며 재시도할 수 있습니다.")
        q = data.get("question")
        if not isinstance(q, dict) or not isinstance(q.get("text"), str) or not q["text"].strip():
            raise EngineError("질문 형식이 올바르지 않습니다.")
        options = q.get("options")
        if not isinstance(options, list) or not 2 <= len(options) <= 4 or any(not isinstance(o, dict) or not isinstance(o.get("value"), str) or not o["value"].strip() or not isinstance(o.get("detail"), str) for o in options):
            raise EngineError("질문 선택지가 올바르지 않습니다.")
        if len({o["value"] for o in options}) != len(options):
            raise EngineError("질문 선택지가 중복되어 처리하지 않았습니다.")
        return "waiting_for_user", dict(q, id=uuid.uuid4().hex, version=1), None
    b = data.get("brief")
    if status != "brief_ready" or not isinstance(b, dict):
        raise EngineError("편집 방향 결과 형식이 올바르지 않습니다.")
    for key in ("recommended_format", "format_comparison", "reason", "limitations"):
        if not isinstance(b.get(key), str):
            raise EngineError("편집 방향에 필수 설명이 빠져 있습니다.")
    if not isinstance(b.get("hooks"), list) or not 2 <= len(b["hooks"]) <= 3 or any(not isinstance(h, str) for h in b["hooks"]):
        raise EngineError("후킹 문구 형식이 올바르지 않습니다.")
    if not isinstance(b.get("facts"), list):
        raise EngineError("사실 검증 목록이 없습니다.")
    for fact in b["facts"]:
        if not isinstance(fact, dict) or not isinstance(fact.get("text"), str) or fact.get("kind") not in ("fact", "company_claim", "unknown"):
            raise EngineError("사실 검증 항목의 형식이 올바르지 않습니다.")
        if fact["kind"] != "unknown" and (not valid_url(fact.get("source_url")) or clean_url(fact["source_url"]) not in read_urls):
            raise EngineError("핵심 사실의 원문 읽기 기록을 확인하지 못했습니다. 검증 완료로 처리하지 않았으니 다시 시도해 주세요.")
    if not any(f["kind"] != "unknown" for f in b["facts"]):
        raise EngineError("원문으로 뒷받침된 핵심 사실이 없어 편집안을 확정하지 않았습니다.")
    return "brief_ready", None, b


class JobManager:
    def __init__(self, store, engine=None):
        self.store = store
        self.engine = engine or ClaudeEngine(store.path.parent / "engine")
        self.lock = threading.Lock()
        self.active = {}

    def update(self, project_id, run_id, change):
        with self.store.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            p = self.store._get(db, project_id)
            if p.get("run_id") != run_id or p["status"] not in RUNNING:
                return
            change(p)
            db.execute("UPDATE projects SET body=? WHERE id=?", (json.dumps(p, ensure_ascii=False), project_id))

    def recover(self):
        for summary in self.store.list():
            p = self.store.get(summary["id"])
            if p["status"] in RUNNING:
                def interrupted(current):
                    current["status"] = "interrupted"
                    current["error"] = "서버가 다시 시작되어 작업이 중단됐습니다. 저장한 자료·선택·답변을 유지했습니다. 다시 시도를 눌러 주세요."
                    current["version"] += 1
                self.update(p["id"], p["run_id"], interrupted)

    def ensure(self, state):
        run_id = state.get("run_id")
        if not run_id or state["status"] not in RUNNING:
            return
        with self.lock:
            if run_id in self.active:
                return
            current = self.store.get(state["id"])
            if current.get("run_id") != run_id or current["status"] not in RUNNING:
                return
            flag = threading.Event()
            self.active[run_id] = flag
            threading.Thread(target=self.work, args=(current, flag), daemon=True).start()

    def cancel(self, run_id):
        with self.lock:
            if run_id in self.active:
                self.active[run_id].set()

    def shutdown(self):
        with self.lock:
            for flag in self.active.values():
                flag.set()
        deadline = time.monotonic() + 8
        while time.monotonic() < deadline:
            with self.lock:
                if not self.active:
                    return
            time.sleep(.1)

    def work(self, p, cancelled):
        project_id, run_id, stage = p["id"], p["run_id"], p["job_stage"]

        def log(text):
            self.update(project_id, run_id, lambda current: current.update(events=(current.get("events", []) + [text])[-100:]))

        def session(sid):
            self.update(project_id, run_id, lambda current: current.update(engine_session_id=sid))

        try:
            if stage == "research":
                prompt, schema = research_prompt(p), RESEARCH_SCHEMA
            elif stage == "storyboard":
                prompt, schema = storyboard_prompt(p), STORY_SCHEMA
            elif stage == "card_fix":
                prompt, schema = card_fix_prompt(p), CARD_FIX_SCHEMA
            else:
                prompt, schema = editorial_prompt(p, continuing=stage == "continue"), EDITORIAL_SCHEMA
            data, meta = self.engine.run(project_id, prompt, schema,
                                         p.get("engine_session_id"), log, session, cancelled)
            current = self.store.get(project_id)
            sid = meta.get("session_id")
            if not sid or sid != current.get("engine_session_id"):
                raise EngineError("Claude의 최종 세션 ID를 확인하지 못했습니다.")
            reads = sorted(set(current.get("read_urls", [])) | set(meta.get("read_urls", [])))
            if stage == "research":
                candidates, notes = checked_research(data, meta, p["period"])
                def finish(current):
                    current.update(status="selecting", candidates=candidates, research_notes=notes, read_urls=reads, error=None)
                    current["version"] += 1
            elif stage == "storyboard":
                board = checked_storyboard(data, dict(p, read_urls=reads))
                def finish(current):
                    history = current.get("storyboard_history", [])
                    if current.get("storyboard"):
                        history = (history + [current["storyboard"]])[-20:]
                    current.update(status="storyboard_ready", storyboard=board, storyboard_history=history,
                                   read_urls=reads, error=None)
                    current["version"] += 1
            elif stage == "card_fix":
                result = checked_card_fix(data, dict(p, read_urls=reads))
                def finish(current):
                    fix = current["card_fix"]
                    current.update(read_urls=reads, error=None)
                    if current["storyboard"]["version"] != fix["storyboard_version"]:
                        raise EngineError("고치는 동안 기획이 바뀌어 결과를 적용하지 않았습니다.")
                    if result["change"] == "image":
                        self.store.request_new_image(current, fix["card_id"], result["image_note"])
                    else:
                        board = current["storyboard"]
                        current["storyboard_history"] = (current.get("storyboard_history", []) + [json.loads(json.dumps(board))])[-20:]
                        card = next(c for c in board["cards"] if c["id"] == fix["card_id"])
                        card.update({k: result[k] for k in ("title", "message", "body", "fact_refs", "source_urls")}, edited_by_user=False, revised_by_request=fix["request"])
                        board["version"] += 1
                        board["approved_version"] = None
                        current["status"] = "storyboard_ready"
                    fix["result"] = {"change": result["change"], "reason": result["reason"]}
                    self.store.refresh_renders(current)
                    current["version"] += 1
            else:
                state, question, brief = checked_editorial(data, reads, bool(p.get("answer") or p.get("editorial_goal")))
                def finish(current):
                    current.update(status=state, question=question if question else current.get("question"), editorial_brief=brief, read_urls=reads, error=None)
                    current["version"] += 1
            self.update(project_id, run_id, finish)
        except Exception as e:
            message = str(e) if isinstance(e, EngineError) else "조사 작업 중 오류가 발생했습니다. 저장된 자료를 유지했으니 다시 시도해 주세요."
            def failed(current):
                if stage == "card_fix":
                    # The approved cards stay usable; the failed request can be sent again from the card fix form.
                    current["card_fix"]["error"] = message
                    current.update(status=self.store.image_status(current), error=None)
                    self.store.refresh_renders(current)
                else:
                    current.update(status="error", error=message)
                current["version"] += 1
            self.update(project_id, run_id, failed)
        finally:
            with self.lock:
                self.active.pop(run_id, None)
