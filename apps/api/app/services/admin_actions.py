"""Testable administrator actions used by the Telegram bot."""

import json
import time
from urllib.parse import unquote, urlparse

from app.core.config import config
from app.ingestion.storage_archive import delete_r2_objects


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
