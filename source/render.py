"""Render final card PNGs: background pixels + separately stored Korean text."""
import hashlib
import io
import json
import re
from pathlib import Path

FONTS = [("/usr/share/fonts/opentype/noto/NotoSansCJK-{w}.ttc", 1),
         ("C:/Windows/Fonts/malgun{b}.ttf", 0), ("/mnt/c/Windows/Fonts/malgun{b}.ttf", 0)]
COLORS = {"#24384A": "딥네이비", "#1E1E1E": "검정", "#FFFFFF": "흰색"}
# Text area as (top, bottom) fractions of the card height; the footer strip stays below.
ZONES = {"top": (0.08, 0.47), "bottom": (0.50, 0.90), "full": (0.08, 0.72)}
MOBILE_WIDTH = 375
RENDERER = 4  # includes the approved ivory-gradient design
# Same-meaning symbols the Korean font can draw; the stored text is not changed.
SYMBOLS = str.maketrans({"✔": "✓", "✅": "✓", "☑": "✓"})


class RenderError(Exception):
    pass


def default_layout(card):
    brief = card.get("image_brief", "")
    bottom = "하단 1/3 본문" in brief or "하단 본문" in brief
    wide = "넓은 여백" in brief
    return {"position": "full" if wide else "bottom" if bottom else "top", "title_size": 62, "body_size": 34,
            "text_color": "#24384A", "panel": 0.82}


def checked_layout(data):
    layout = {"position": data.get("position"), "title_size": data.get("title_size"), "body_size": data.get("body_size"),
              "text_color": data.get("text_color"), "panel": data.get("panel")}
    if layout["position"] not in ZONES or layout["text_color"] not in COLORS:
        raise RenderError("글자 위치(위/아래/넓게)와 글자색을 확인해 주세요.")
    if type(layout["title_size"]) is not int or not 44 <= layout["title_size"] <= 80 or type(layout["body_size"]) is not int or not 26 <= layout["body_size"] <= 44:
        raise RenderError("제목 44~80px, 본문 26~44px 범위에서 골라 주세요.")
    if not isinstance(layout["panel"], (int, float)) or not 0 <= layout["panel"] <= 0.95:
        raise RenderError("글자 배경 상자의 진하기는 0~0.95 사이여야 합니다.")
    layout["panel"] = round(float(layout["panel"]), 2)
    if data.get("theme"):
        if data["theme"] != "ivory-gradient" or type(data.get("image_offset_y")) is not int or not -200 <= data["image_offset_y"] <= 300:
            raise RenderError("배경 테마와 그림 위치(-200~300px)를 확인해 주세요.")
        layout.update(theme="ivory-gradient", image_offset_y=data["image_offset_y"])
    return layout


def font(size, bold=False):
    from PIL import ImageFont
    for pattern, index in FONTS:
        path = pattern.format(w="Bold" if bold else "Regular", b="bd" if bold else "")
        if Path(path).is_file():
            return ImageFont.truetype(path, size, index=index)
    raise RenderError("한글 글꼴을 찾지 못했습니다. Ubuntu에서 fonts-noto-cjk 설치 여부를 확인해 주세요.")


def wrap(draw, text, face, width):
    lines = []
    for paragraph in text.split("\n"):
        line = ""
        for word in paragraph.split(" "):
            trial = (line + " " + word).strip()
            if draw.textlength(trial, font=face) <= width:
                line = trial
                continue
            if line:
                lines.append(line)
            line = ""
            # A single word longer than the box is split by characters.
            for ch in word:
                if draw.textlength(line + ch, font=face) > width and line:
                    lines.append(line)
                    line = ""
                line += ch
        lines.append(line)
    return lines


def luminance(rgb):
    def channel(v):
        v /= 255
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4
    r, g, b = (channel(v) for v in rgb[:3])
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(a, b):
    la, lb = sorted((luminance(a), luminance(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def missing_glyphs(text):
    """Characters the bundled font would draw as an empty box (.notdef)."""
    from PIL import Image, ImageDraw

    def pixels(face, ch):
        image = Image.new("L", (64, 64))
        ImageDraw.Draw(image).text((8, 4), ch, font=face, fill=255)
        return image.tobytes()

    missing = set()
    for face in (font(40), font(40, True)):
        blank = pixels(face, "")
        missing |= {ch for ch in set(text) if not ch.isspace() and pixels(face, ch) == blank}
    return sorted(missing)


def input_hash(card, layout, image, meta):
    data = [RENDERER, card["title"], card["message"], card["body"], layout, image["sha256"], meta]
    return hashlib.sha256(json.dumps(data, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()


def render_card(background, card, layout, meta):
    """Return PNG bytes and measured checks. The source background bytes are never modified."""
    from PIL import Image, ImageDraw
    if layout.get("theme") == "ivory-gradient":
        if meta["card_size"] != "1080x1350":
            raise RenderError("현재 그라데이션 디자인은 세로형 1080×1350 카드용입니다.")
        from gradient_theme import render_gradient
        canvas, measured = render_gradient(card, background, layout)
        number = measured["number"]
        checks = [{"level": "ok" if measured["text_bottom"] <= 1210 else "error",
                   "text": f"글 영역 하단 {measured['text_bottom']}px · 순번 영역과 겹침 검사"},
                  {"level": "ok", "text": f"고딕·그라데이션 배경 · 그림 이동 {layout['image_offset_y']}px · 출처 띠 없음"},
                  {"level": "warning" if number["outline"] else "ok",
                   "text": f"순번 {'흰색' if number['color'] == '#FFFFFF' else '네이비'} 자동 선택"},
                  {"level": "ok", "text": f"휴대폰 375px 화면에서 본문 약 {round(layout['body_size'] * 375 / 1080, 1)}px"}]
        missing = missing_glyphs("".join(card[k] for k in ("title", "message", "body")).translate(SYMBOLS))
        if missing:
            checks.append({"level": "error", "text": f"글꼴에 없는 글자 {' '.join(missing)}가 빈 네모로 보입니다."})
        out = io.BytesIO()
        canvas.save(out, format="PNG", optimize=True)
        return out.getvalue(), checks
    width, height = (int(x) for x in meta["card_size"].split("x"))
    with Image.open(background) as source:
        source = source.convert("RGB")
        scale = max(width / source.width, height / source.height)
        resized = source.resize((round(source.width * scale), round(source.height * scale)), Image.LANCZOS)
    left, top = (resized.width - width) // 2, (resized.height - height) // 2
    canvas = resized.crop((left, top, left + width, top + height)).convert("RGBA")
    margin, footer_h = 84, 96
    zone = tuple(round(height * f) for f in ZONES[layout["position"]])
    faces = [font(layout["title_size"], True), font(round(layout["body_size"] * 1.12), True), font(layout["body_size"])]
    gaps = [round(layout["title_size"] * 0.45), round(layout["body_size"] * 0.7), 0]
    draw = ImageDraw.Draw(canvas)
    blocks = []
    texts = [card[k].translate(SYMBOLS) for k in ("title", "message", "body")]
    # A checklist body reads better with one item per line.
    texts[2] = re.sub(r"\s*✓\s*", "\n✓ ", texts[2]).strip()
    missing = missing_glyphs("".join(texts))
    for text, face, gap in zip(texts, faces, gaps):
        line_h = round(face.size * 1.42)
        lines = wrap(draw, text, face, width - margin * 2 - 48)
        blocks.append((lines, face, line_h, gap))
    needed = sum(len(lines) * line_h + gap for lines, _, line_h, gap in blocks)
    pad = 24
    box = (margin - pad, zone[0] - pad, width - margin + pad, zone[0] + min(needed, zone[1] - zone[0]) + pad)
    overlay = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    panel_rgb = (20, 28, 36) if layout["text_color"] == "#FFFFFF" else (247, 243, 232)
    ImageDraw.Draw(overlay).rounded_rectangle(box, radius=22, fill=panel_rgb + (round(255 * layout["panel"]),))
    canvas = Image.alpha_composite(canvas, overlay)
    behind = canvas.crop(box).convert("RGB").resize((1, 1), Image.BOX).getpixel((0, 0))
    draw = ImageDraw.Draw(canvas)
    color = tuple(int(layout["text_color"][i:i + 2], 16) for i in (1, 3, 5))
    y, clipped = zone[0], 0
    for lines, face, line_h, gap in blocks:
        for line in lines:
            if y + line_h > zone[1]:
                clipped += 1
            else:
                draw.text((margin, y), line, font=face, fill=color)
            y += line_h
        y += gap
    footer = f"출처 {meta['source']} · 조사 기준 {meta['as_of']} · {card['order']}/{meta['total']}"
    small = font(24)
    footer_box = (0, height - footer_h, width, height)
    ImageDraw.Draw(canvas).rectangle(footer_box, fill=(247, 243, 232, 255))
    draw.text((margin, height - footer_h + 32), footer, font=small, fill=(36, 56, 74))
    ratio = contrast(color, behind)
    mobile_px = round(layout["body_size"] * MOBILE_WIDTH / width, 1)
    checks = [{"level": "error", "text": f"글자 {clipped}줄이 정해진 영역을 넘어 잘렸습니다. 문구를 줄이거나 글자 크기를 낮춰 주세요."} if clipped else
              {"level": "ok", "text": f"글자 잘림 없음 · 필요한 높이 {needed}px / 영역 {zone[1] - zone[0]}px"},
              {"level": "warning" if ratio < 4.5 else "ok", "text": f"글자와 배경 명암비 {ratio:.1f}:1 (기준 4.5:1)"},
              {"level": "warning" if mobile_px < 11.5 else "ok", "text": f"휴대폰 375px 화면에서 본문 약 {mobile_px}px"}]
    if missing:
        checks.append({"level": "error", "text": f"글꼴에 없는 글자 {' '.join(missing)}가 빈 네모로 보입니다. 다른 글자로 바꿔 주세요."})
    out = io.BytesIO()
    canvas.convert("RGB").save(out, format="PNG", optimize=True)
    return out.getvalue(), checks
