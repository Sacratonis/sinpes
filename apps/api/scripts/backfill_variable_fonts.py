"""Backfill is_variable for existing families by inspecting their stored WOFF2 files."""

import io
import json

import requests
from fontTools.ttLib import TTFont

from app.db.database import get_db


def stored_urls(row) -> list[str]:
    urls = {str(row["woff2_url"] or "").strip()}
    try:
        variants = json.loads(row["variants"] or "[]")
    except (TypeError, json.JSONDecodeError):
        variants = []
    urls.update(str(item.get("url") or "").strip() for item in variants if isinstance(item, dict))
    return sorted(url for url in urls if url.startswith(("http://", "https://")))


def url_is_variable(url: str) -> bool:
    response = requests.get(url, timeout=30)
    response.raise_for_status()
    font = TTFont(io.BytesIO(response.content), lazy=True)
    try:
        return "fvar" in font
    finally:
        font.close()


def backfill() -> tuple[int, int]:
    checked = 0
    variable = 0
    with get_db() as conn:
        rows = conn.execute("SELECT slug,woff2_url,variants FROM font_registry ORDER BY rowid").fetchall()
        for row in rows:
            checked += 1
            detected = any(url_is_variable(url) for url in stored_urls(row))
            conn.execute(
                "UPDATE font_registry SET is_variable=? WHERE slug=?",
                (int(detected), row["slug"]),
            )
            variable += int(detected)
        conn.commit()
    return checked, variable


if __name__ == "__main__":
    checked_count, variable_count = backfill()
    print(f"Checked {checked_count} families; verified {variable_count} variable families.")
