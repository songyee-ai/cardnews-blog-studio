"""Build the approved ZIP and check the exported file itself, not the screen."""
import hashlib
import io
import json
import re
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from render import missing_glyphs, SYMBOLS

KST = timezone(timedelta(hours=9))


def card_files(p):
    board = p["storyboard"]
    return [(f"cards/card-{c['order']:02d}.png", c) for c in sorted(board["cards"], key=lambda c: c["order"])]


def sources_text(p):
    t, board = p["period"], p["storyboard"]
    lines = [f"# 출처 기록 · {p['topic']}", "", f"- 조사 기준 시각: {t['as_of']} ({t['timezone']})",
             f"- 조사 기간: {t['start']} ~ {t['end']}", f"- 독자: {p['audience']}",
             f"- 전달 목적: {p.get('editorial_goal') or (p.get('answer') or {}).get('text', '')}",
             f"- 형식: {board['format']} · 기획 v{board['version']}", "", "## 카드별 출처", ""]
    for _, c in card_files(p):
        lines.append(f"{c['order']}. {c['title']}")
        lines += [f"   - {u}" for u in c["source_urls"]]
    lines += ["", "## 확인한 사실과 구분", ""]
    names = {"fact": "확인한 사실", "company_claim": "발표 주체의 주장", "unknown": "미확인"}
    for f in (p.get("editorial_brief") or {}).get("facts", []):
        lines.append(f"- [{names.get(f['kind'], f['kind'])}] {f['text']} ({f.get('source_url') or '근거 없음'})")
    return "\n".join(lines) + "\n"


def image_log_text(p):
    lines = ["# 이미지 사용 기록", "", "모든 배경은 설명용 생성 이미지이며 실제 제품 화면이나 현장 사진이 아닙니다.",
             "제목·본문·순번은 이미지 생성 도구가 아니라 앱의 렌더러가 별도로 배치했습니다. 그라데이션 테마는 Noto Sans KR, 기존 테마는 Noto Sans CJK KR을 사용합니다. 카드별 테마와 위치는 아래 글자 배치 기록에 남깁니다.", ""]
    for _, c in card_files(p):
        image, render = p["image_results"][c["id"]], p["renders"][c["id"]]
        lines += [f"## {c['order']}. {c['title']}", f"- 생성 도구: {image['generator']}", f"- 가져온 시각: {image['created_at']}",
                  f"- 원본: {image['format']} {image['width']}×{image['height']} · SHA-256 {image['sha256']}",
                  f"- 최종 카드: SHA-256 {render['sha256']} · 글자 배치 {json.dumps(render['layout'], ensure_ascii=False)}",
                  "- 생성 프롬프트:", "", "```", image.get("prompt", "").strip() or "(기록 없음)", "```", ""]
    return "\n".join(lines)


def build_export(data_root, p):
    """Write the ZIP once per approved signature and return its relative path."""
    approval = p["final_approval"]
    relative = Path("exports") / p["id"] / f"cardnews-v{p['storyboard']['version']}-{approval['signature'][:12]}.zip"
    target = Path(data_root) / relative
    if target.exists():
        return relative.as_posix()
    files = []
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, c in card_files(p):
            raw = (Path(data_root) / p["renders"][c["id"]]["relative_path"]).read_bytes()
            archive.writestr(name, raw)
            files.append({"name": name, "order": c["order"], "title": c["title"], "sha256": hashlib.sha256(raw).hexdigest()})
        archive.writestr("sources.md", sources_text(p))
        archive.writestr("image-log.md", image_log_text(p))
        archive.writestr("manifest.json", json.dumps({"topic": p["topic"], "card_size": p["storyboard"]["card_size"],
                                                      "storyboard_version": p["storyboard"]["version"], "as_of": p["period"]["as_of"],
                                                      "approved_at": approval["approved_at"], "cards": files}, ensure_ascii=False, indent=2))
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(stream.getvalue())
    return relative.as_posix()


def verify_export(data_root, p):
    from PIL import Image
    items = []

    def add(name, result, detail):
        items.append({"name": name, "result": result, "detail": detail})

    path = Path(data_root) / p["final_approval"]["export_path"]
    try:
        archive = zipfile.ZipFile(path)
    except (OSError, zipfile.BadZipFile):
        add("ZIP 열기", "fail", "내보낸 ZIP을 열지 못했습니다.")
        return {"checked_at": datetime.now(KST).isoformat(), "export_path": p["final_approval"]["export_path"], "items": items}
    with archive:
        names = archive.namelist()
        add("ZIP 열기", "pass", f"파일 {len(names)}개")
        expected = card_files(p)
        pngs = sorted(n for n in names if n.startswith("cards/"))
        manifest = json.loads(archive.read("manifest.json")) if "manifest.json" in names else {"cards": []}
        order_ok = pngs == [n for n, _ in expected] and [c["name"] for c in manifest["cards"]] == pngs
        add("카드 수량·순서", "pass" if order_ok else "fail", f"PNG {len(pngs)}장 / 기획 {len(expected)}장, 파일 이름과 목록 순서 {'일치' if order_ok else '불일치'}")
        size = tuple(int(x) for x in p["storyboard"]["card_size"].split("x"))
        bad = []
        for name, c in expected:
            if name not in names:
                bad.append(f"{name} 없음")
                continue
            raw = archive.read(name)
            try:
                with Image.open(io.BytesIO(raw)) as image:
                    image.load()
                    if image.size != size:
                        bad.append(f"{name} 크기 {image.size}")
            except Exception:
                bad.append(f"{name} 열기 실패")
            if hashlib.sha256(raw).hexdigest() != p["renders"][c["id"]]["sha256"]:
                bad.append(f"{name}이 승인한 카드와 다름")
        add("PNG 열림·크기·승인본 일치", "fail" if bad else "pass", ", ".join(bad) or f"모두 {size[0]}×{size[1]} PNG, 승인한 렌더 파일과 같음")
        clipped = [c["order"] for _, c in expected if any(x["level"] == "error" for x in p["renders"][c["id"]]["checks"])]
        warnings = [f"{c['order']}번 {x['text']}" for _, c in expected for x in p["renders"][c["id"]]["checks"] if x["level"] == "warning"]
        add("글자 잘림 (렌더 시 측정)", "fail" if clipped else "pass", (f"잘린 카드 {clipped}" if clipped else "모든 카드가 글자 영역 안에 들어감") + (" · 경고: " + "; ".join(warnings) if warnings else ""))
        text = "".join(c[k] for _, c in expected for k in ("title", "message", "body"))
        missing = missing_glyphs(text.translate(SYMBOLS))
        add("한글 글자 누락 (빈 네모)", "fail" if missing else "pass", "글꼴에 없는 글자: " + " ".join(missing) if missing else f"카드 글자 {len(set(text))}종 모두 글꼴에 있음")
        sources = archive.read("sources.md").decode("utf-8") if "sources.md" in names else ""
        urls = sorted({u for _, c in expected for u in c["source_urls"]})
        miss = [u for u in urls if u not in sources]
        add("출처 기록", "fail" if miss or not urls else "pass", f"카드 출처 {len(urls)}개 기록" + (f", 누락 {miss}" if miss else ""))
        t = p["period"]
        dated = all(x in sources for x in (t["as_of"], t["start"], t["end"]))
        add("조사 기준 시각·기간", "pass" if dated else "fail", f"{t['as_of'][:16]} · {t['start']} ~ {t['end']}")
        log = archive.read("image-log.md").decode("utf-8") if "image-log.md" in names else ""
        logged = all(p["image_results"][c["id"]]["sha256"] in log for _, c in expected)
        add("이미지 사용 기록", "pass" if logged else "fail", "카드별 생성 도구·프롬프트·원본 SHA-256 기록" if logged else "기록이 빠진 카드가 있음")
    dates = sorted(set(re.findall(r"\d{4}-\d{2}-\d{2}|\d{4}년 \d{1,2}월 \d{1,2}일|\d{1,2}월 \d{1,2}일", text)))
    add("카드 속 날짜와 원문 대조", "unverified", f"카드에 적힌 날짜 {', '.join(dates) or '없음'} — 원문의 발표일과 직접 대조해 주세요.")
    add("원문 링크가 지금 열리는지", "unverified", "앱은 내보내기 검사 중 외부 사이트에 접속하지 않습니다. 링크를 직접 열어 주세요.")
    add("카드 문장이 원문 내용과 같은지", "unverified", "기능·조건 표현을 원문과 직접 대조해 주세요.")
    add("휴대폰에서 눈으로 읽기", "unverified", "측정값은 통과여도 실제 휴대폰에서 7장을 넘겨 읽어 확인해 주세요.")
    return {"checked_at": datetime.now(KST).isoformat(), "export_path": p["final_approval"]["export_path"], "items": items}
