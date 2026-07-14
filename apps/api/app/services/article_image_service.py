"""Deterministic, metadata-rich editorial images for Writer articles."""

import io
import re

import requests
from PIL import Image, ImageDraw, ImageOps

from app.ingestion.media_processor import finalize_seo_image, validate_image_bytes
from app.ingestion.storage_archive import upload_to_r2


SIZE = (1200, 630)


def select_featured_fonts(body_html: str, fonts: list[dict], limit: int = 4) -> list[dict]:
    """Select by first link appearance, then referenced-font order."""
    positions = {}
    for index, font in enumerate(fonts):
        match = re.search(rf'/font/{re.escape(font["slug"])}(?:/|["\'])', body_html)
        positions[font["slug"]] = (match.start() if match else 10**9, index)
    return sorted(fonts, key=lambda font: positions[font["slug"]])[:limit]


def _download_image(url: str) -> Image.Image:
    response = requests.get(url, timeout=30)
    response.raise_for_status()
    validate_image_bytes(response.content)
    return Image.open(io.BytesIO(response.content)).convert("RGB")


def compose_article_image(fonts: list[dict]) -> bytes:
    if not fonts:
        raise ValueError("An article image requires at least one referenced font")
    fonts = fonts[:4]
    canvas = Image.new("RGB", SIZE, "#0b0b0a")
    if len(fonts) == 1:
        boxes = [(0, 0, 1200, 630)]
    elif len(fonts) == 2:
        boxes = [(0, 0, 600, 630), (600, 0, 1200, 630)]
    elif len(fonts) == 3:
        boxes = [(0, 0, 600, 630), (600, 0, 1200, 315), (600, 315, 1200, 630)]
    else:
        boxes = [(0, 0, 600, 315), (600, 0, 1200, 315), (0, 315, 600, 630), (600, 315, 1200, 630)]
    for font, box in zip(fonts, boxes):
        if not font.get("seo_image_url"):
            raise ValueError(f"Referenced font has no hero image: {font['slug']}")
        width, height = box[2] - box[0], box[3] - box[1]
        tile = ImageOps.fit(_download_image(font["seo_image_url"]), (width, height), Image.Resampling.LANCZOS)
        canvas.paste(tile, box[:2])
    draw = ImageDraw.Draw(canvas)
    for x1, y1, x2, y2 in boxes:
        draw.rectangle((x1, y1, x2 - 1, y2 - 1), outline=(210, 210, 200), width=1)
    output = io.BytesIO()
    canvas.save(output, "JPEG", quality=92, optimize=True)
    return output.getvalue()


def finalize_article_image(
    raw_bytes: bytes,
    article_slug: str,
    title: str,
    target_keyword: str,
    secondary_keywords: list[str],
    alt_text: str,
) -> str:
    source = Image.open(io.BytesIO(validate_image_bytes(raw_bytes))).convert("RGB")
    fitted = ImageOps.fit(source, SIZE, Image.Resampling.LANCZOS)
    normalized = io.BytesIO()
    fitted.save(normalized, "JPEG", quality=92, optimize=True)
    export = finalize_seo_image(
        raw_image_bytes=normalized.getvalue(),
        target_keyword=target_keyword,
        secondary_keywords=secondary_keywords,
        image_title=title,
        image_description=alt_text,
        rights="SINPES editorial composite. Referenced fonts remain subject to their original licenses.",
    )
    return upload_to_r2(
        data=export["webp_bytes"],
        key=f"articles/{article_slug}/{export['filename_base']}.webp",
        content_type="image/webp",
        cache_control="public, max-age=31536000",
    )


def build_generated_article_image(article: dict, fonts: list[dict]) -> tuple[str, str]:
    selected = select_featured_fonts(article["body_html"], fonts)
    raw = compose_article_image(selected)
    names = [font["display_name"] for font in selected]
    alt = f"Editorial typography examples featuring {', '.join(names)} for {article['target_keyword']}"
    url = finalize_article_image(
        raw, article["slug"], article["title"], article["target_keyword"],
        article.get("secondary_keywords", []), alt,
    )
    return url, alt
