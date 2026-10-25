"""Approved ivory-gradient theme: separately editable text, backdrop position and adaptive page numbers."""
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageOps
from render import contrast, wrap, SYMBOLS
INK, PAPER = (36, 56, 74), (247, 243, 232)
FONT_PATHS = [str(Path(__file__).resolve().parent / "fonts/NotoSansKR-VF.ttf"), "/mnt/c/Windows/Fonts/NotoSansKR-VF.ttf", "C:/Windows/Fonts/NotoSansKR-VF.ttf"]

def face(size, bold=False):
    f = ImageFont.truetype(next((p for p in FONT_PATHS if Path(p).is_file()), FONT_PATHS[0]), size)
    axes = f.get_variation_axes()
    f.set_variation_by_axes([700 if a["name"] == b"Weight" and bold else 400 if a["name"] == b"Weight" else a["default"] for a in axes])
    return f


def number_color(image, box):
    """Prefer navy; invert to white when the actual number area needs it."""
    pixels = list(image.crop(box).convert("RGB").resize((24, 12)).get_flattened_data())
    def floor_ratio(color):
        ratios = sorted(contrast(color, p) for p in pixels)
        return ratios[int(len(ratios) * .1)]
    dark, light = floor_ratio(INK), floor_ratio((255, 255, 255))
    color = (255, 255, 255) if dark < 4.5 and light > dark else INK
    chosen = light if color == (255, 255, 255) else dark
    return color, {"navy_contrast": round(dark, 2), "white_contrast": round(light, 2),
                   "color": "#FFFFFF" if color == (255, 255, 255) else "#24384A", "outline": chosen < 4.5}


def gradient(canvas):
    stops = [(0, 1), (.35, .98), (.49, .92), (.59, .75), (.73, .28), (.86, 0), (1, 0)]
    overlay = Image.new("RGBA", canvas.size)
    d = ImageDraw.Draw(overlay)
    for y in range(canvas.height):
        t = y / (canvas.height - 1)
        for (a, av), (b, bv) in zip(stops, stops[1:]):
            if a <= t <= b:
                opacity = av + (bv - av) * (t - a) / (b - a)
                break
        d.line((0, y, canvas.width, y), fill=PAPER + (round(opacity * 255),))
    return Image.alpha_composite(canvas.convert("RGBA"), overlay).convert("RGB")


def render_gradient(card, background, layout):
    art = ImageOps.fit(Image.open(background).convert("RGB"), (1080, 1350), method=Image.Resampling.LANCZOS)
    image_offset = layout["image_offset_y"]
    backdrop = Image.new("RGB", (1080, 1350), PAPER)
    backdrop.paste(art, (0, image_offset))
    canvas = gradient(backdrop)
    d = ImageDraw.Draw(canvas)
    y, last = 108, 0
    blocks = [(card["title"], face(layout["title_size"], True), round(layout["title_size"] * 1.35), round(layout["title_size"] * .58)),
              (card["message"], face(round(layout["body_size"] * 1.12), True), round(round(layout["body_size"] * 1.12) * 1.5), round(layout["body_size"] * 1.06)), (card["body"].translate(SYMBOLS), face(layout["body_size"]), round(layout["body_size"] * 1.5), 0)]
    for text, font, line_height, gap in blocks:
        for line in wrap(d, text, font, 864):
            d.text((108, y), line, font=font, fill=INK, anchor="lt")
            last = y + line_height
            y += line_height
        y += gap

    label = f"{card['order']:02d} / 07"
    number_font = face(27, True)
    box0 = d.textbbox((0, 0), label, font=number_font, anchor="lt")
    number_width = box0[2] - box0[0]
    x, ny = 1008 - number_width, 1275
    sample = (int(x - 4), ny - 4, 1012, ny + 40)
    color, number_info = number_color(canvas, sample)
    stroke = 1 if number_info["outline"] else 0
    d.text((x, ny), label, font=number_font, fill=color, anchor="lt", stroke_width=stroke,
           stroke_fill=INK if color == (255, 255, 255) else (255, 255, 255))
    return canvas, {"image_offset_y": image_offset, "text_bottom": last, "number": number_info, "size": [1080, 1350]}


