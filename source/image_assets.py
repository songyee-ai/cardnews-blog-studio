"""Validate and keep imported backgrounds without changing the source pixels."""
import base64
import binascii
import hashlib
import io
from datetime import datetime, timezone, timedelta
from pathlib import Path


class ImageAssetError(Exception):
    pass


def inspect_image(raw):
    if not raw or len(raw) > 16 * 1024 * 1024:
        raise ImageAssetError("이미지는 16MB 이하의 PNG·JPEG·WebP 파일이어야 합니다.")
    try:
        from PIL import Image
    except ImportError:
        raise ImageAssetError("이미지 검사 도구가 없습니다. README의 .venv/bin/python으로 서버를 실행해 주세요.")
    try:
        with Image.open(io.BytesIO(raw)) as image:
            fmt = image.format
            width, height = image.size
            if fmt not in ("PNG", "JPEG", "WEBP") or not 128 <= width <= 8192 or not 128 <= height <= 8192:
                raise ImageAssetError("PNG·JPEG·WebP 형식, 가로·세로 128~8192px 범위의 이미지를 골라 주세요.")
            image.verify()
        # verify checks integrity without decoding all pixels; reopen and decode too.
        with Image.open(io.BytesIO(raw)) as image:
            image.load()
    except ImageAssetError:
        raise
    except Exception:
        raise ImageAssetError("파일을 실제 이미지로 열지 못했습니다. 손상되거나 이미지가 아닌 파일입니다.")
    return {"format": fmt, "width": width, "height": height, "sha256": hashlib.sha256(raw).hexdigest()}


def import_background(data_root, project, data):
    encoded = data.get("image_base64")
    generator, prompt = data.get("generator"), data.get("prompt")
    if not isinstance(encoded, str) or len(encoded) > 23 * 1024 * 1024:
        raise ImageAssetError("이미지 데이터가 없거나 너무 큽니다.")
    if not isinstance(generator, str) or not 1 <= len(generator.strip()) <= 200 or not isinstance(prompt, str) or len(prompt) > 10000:
        raise ImageAssetError("이미지 도구·출처와 10000자 이내 생성 기록을 입력해 주세요.")
    card_id = data.get("card_id")
    board = project.get("storyboard") or {}
    if not any(card["id"] == card_id for card in board.get("cards", [])):
        raise ImageAssetError("현재 기획에서 이미지를 넣을 카드를 찾지 못했습니다.")
    try:
        raw = base64.b64decode(encoded, validate=True)
    except (binascii.Error, ValueError):
        raise ImageAssetError("이미지 전송 내용을 읽을 수 없습니다.")
    info = inspect_image(raw)
    suffix = {"PNG": ".png", "JPEG": ".jpg", "WEBP": ".webp"}[info["format"]]
    relative = Path("images") / project["id"] / card_id / (info["sha256"] + suffix)
    target = Path(data_root) / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    if not target.exists():
        target.write_bytes(raw)
    return dict(info, status="ready", relative_path=relative.as_posix(), generator=generator.strip(), prompt=prompt,
                created_at=datetime.now(timezone(timedelta(hours=9))).isoformat(),
                explanation="설명용 생성·제공 이미지. 실제 제품 화면이나 현장 사진이 아닙니다.",
                storyboard_version=board["version"])
