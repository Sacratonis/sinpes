"""Testable administrator actions used by the Telegram bot."""

import json
import io
import os
import tempfile
import time
import zipfile
from datetime import datetime, timezone
from urllib.parse import unquote, urlparse

import requests

from app.core.config import config
from app.ingestion.storage_archive import delete_r2_objects
from app.ingestion.storage_archive import upload_to_r2


def _r2_key(url: str | None) -> str | None:
    if not url:
        return None
    base = config.R2_PUBLIC_BASE_URL.rstrip("/") + "/"
    if not url.startswith(base):
        return None
    return unquote(url[len(base):].split("?", 1)[0])


def font_asset_keys(conn, slug: str) -> list[str]:
    row = conn.execute(
        "SELECT variants, woff2_url, download_zip_url FROM font_registry WHERE slug = ?",
        (slug,),
    ).fetchone()
    if not row:
        return []
    urls = [row["woff2_url"], row["download_zip_url"]]
    try:
        urls.extend(item.get("url") for item in json.loads(row["variants"] or "[]"))
    except (TypeError, ValueError):
        pass
    urls.extend(
        result[0] for result in conn.execute(
            "SELECT DISTINCT seo_image_url FROM font_translations WHERE slug = ?",
            (slug,),
        ).fetchall()
    )
    return sorted(set(key for url in urls if (key := _r2_key(url))))


def prepare_erase(conn, slug: str) -> tuple[dict | None, list[str]]:
    row = conn.execute(
        "SELECT slug, display_name, status FROM font_registry WHERE slug = ?",
        (slug,),
    ).fetchone()
    if not row:
        return None, []
    keys = font_asset_keys(conn, slug)
    token = json.dumps({"slug": slug, "expires": time.time() + 300})
    conn.execute(
        "INSERT OR REPLACE INTO meta(key, value) VALUES(?, ?)",
        (f"erase_confirmation:{slug}", token),
    )
    conn.commit()
    return dict(row), keys


def confirm_erase(conn, slug: str) -> int:
    row = conn.execute(
        "SELECT value FROM meta WHERE key = ?", (f"erase_confirmation:{slug}",)
    ).fetchone()
    if not row:
        raise ValueError("Run /erase <slug> first.")
    confirmation = json.loads(row["value"])
    if confirmation.get("slug") != slug or confirmation.get("expires", 0) < time.time():
        raise ValueError("Erase confirmation expired. Run /erase <slug> again.")

    keys = font_asset_keys(conn, slug)
    deleted = delete_r2_objects(keys)
    conn.execute("DELETE FROM font_translations WHERE slug = ?", (slug,))
    conn.execute("DELETE FROM font_registry WHERE slug = ?", (slug,))

    # Remove queue history only when its JSON payload belongs to this font.
    for queue_row in conn.execute("SELECT id, text_payload FROM upload_queue").fetchall():
        try:
            payload = json.loads(queue_row["text_payload"])
        except (TypeError, ValueError):
            continue
        if payload.get("slug") == slug:
            conn.execute("DELETE FROM upload_queue WHERE id = ?", (queue_row["id"],))
    conn.execute("DELETE FROM meta WHERE key = ?", (f"erase_confirmation:{slug}",))
    conn.commit()
    return deleted


def regenerate_font_poster(conn, slug: str) -> str:
    """Rebuild an existing poster from its archived original font ZIP."""
    from app.ingestion.media_processor import process_hero_image

    row = conn.execute(
        "SELECT slug, display_name, category, use_cases, download_zip_url "
        "FROM font_registry WHERE slug = ?",
        (slug,),
    ).fetchone()
    if not row:
        raise ValueError(f"Font '{slug}' was not found.")
    if not row["download_zip_url"]:
        raise ValueError(f"Font '{slug}' has no archived ZIP file.")

    response = requests.get(row["download_zip_url"], timeout=60)
    response.raise_for_status()
    try:
        archive = zipfile.ZipFile(io.BytesIO(response.content))
    except zipfile.BadZipFile as exc:
        raise ValueError(f"Font '{slug}' has an invalid archived ZIP file.") from exc
    font_member = next(
        (name for name in archive.namelist() if name.lower().endswith((".otf", ".ttf"))),
        None,
    )
    if not font_member:
        raise ValueError(f"Font '{slug}' ZIP contains no OTF or TTF file.")

    try:
        use_cases = json.loads(row["use_cases"] or "[]")
    except (TypeError, ValueError):
        use_cases = [item.strip() for item in str(row["use_cases"] or "").split(",") if item.strip()]

    suffix = os.path.splitext(font_member)[1].lower()
    with tempfile.NamedTemporaryFile(suffix=suffix) as font_file:
        font_file.write(archive.read(font_member))
        font_file.flush()
        existing_image_urls = [
            result[0]
            for result in conn.execute(
                "SELECT DISTINCT t.seo_image_url "
                "FROM font_translations t WHERE t.slug != ? AND t.seo_image_url != ''",
                (slug,),
            ).fetchall()
        ]
        url = process_hero_image(
            slug=row["slug"],
            display_name=row["display_name"],
            category=row["category"],
            use_cases=use_cases,
            keyword_phrases={"en": f"{row['display_name']}, {row['category']} font"},
            upload_callback=upload_to_r2,
            font_path=font_file.name,
            existing_image_urls=existing_image_urls,
        )

    conn.execute(
        "UPDATE font_translations SET seo_image_url = ? WHERE slug = ?", (url, slug)
    )
    conn.execute(
        "UPDATE font_registry SET last_updated = ? WHERE slug = ?",
        (datetime.now(timezone.utc).isoformat(), slug),
    )
    conn.commit()
    return url
