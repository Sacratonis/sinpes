"""Queue and submit changed public URLs to Bing and other IndexNow engines."""

from __future__ import annotations

import json
from urllib.parse import urljoin, urlsplit

import requests

from app.core.config import config
from app.repositories.meta_repo import MetaRepository


PENDING_KEY = "pending_indexnow_urls"
LAST_ERROR_KEY = "last_indexnow_error"
LAST_SUBMITTED_KEY = "last_indexnow_submitted_urls"
LOCALES = ("en", "es", "pt")


def localized_urls(path: str, locales: tuple[str, ...] | list[str] | None = None) -> list[str]:
    trimmed = path.strip("/")
    normalized = f"/{trimmed}/" if trimmed else "/"
    site = config.SITE_URL.rstrip("/") + "/"
    locales = tuple(dict.fromkeys(locale for locale in (locales or LOCALES) if locale in LOCALES))
    urls = [urljoin(site, normalized.lstrip("/"))]
    urls.extend(
        urljoin(site, f"{locale}{normalized}")
        for locale in locales
        if locale != "en"
    )
    return urls


def queue_indexnow_urls(conn, urls: list[str]) -> list[str]:
    """Persist canonical same-host URLs until a deployment is confirmed."""
    meta = MetaRepository(conn)
    site_host = urlsplit(config.SITE_URL).netloc.lower()
    try:
        pending = json.loads(meta.get_value(PENDING_KEY) or "[]")
    except json.JSONDecodeError:
        pending = []

    combined = {str(url).strip() for url in pending if str(url).strip()}
    for url in urls:
        candidate = str(url).strip()
        parsed = urlsplit(candidate)
        if parsed.scheme == "https" and parsed.netloc.lower() == site_host:
            combined.add(candidate)

    ordered = sorted(combined)
    meta.set_value(PENDING_KEY, json.dumps(ordered))
    return ordered


def remove_queued_indexnow_urls(conn, urls: list[str]) -> list[str]:
    """Remove URLs whose matching content/deployment was rolled back."""
    meta = MetaRepository(conn)
    try:
        pending = json.loads(meta.get_value(PENDING_KEY) or "[]")
    except json.JSONDecodeError:
        pending = []
    removed = {str(url).strip() for url in urls if str(url).strip()}
    remaining = sorted(
        str(url).strip() for url in pending
        if str(url).strip() and str(url).strip() not in removed
    )
    meta.set_value(PENDING_KEY, json.dumps(remaining))
    return remaining


def submit_pending_indexnow(conn) -> dict:
    """Submit queued URLs after the corresponding website build is live."""
    meta = MetaRepository(conn)
    try:
        urls = json.loads(meta.get_value(PENDING_KEY) or "[]")
    except json.JSONDecodeError:
        urls = []

    if not urls:
        return {"status": "skipped", "reason": "no changed URLs"}
    if not config.INDEXNOW_ENABLED:
        return {"status": "skipped", "reason": "IndexNow is disabled", "count": len(urls)}
    if not config.INDEXNOW_KEY:
        return {"status": "skipped", "reason": "IndexNow key is not configured", "count": len(urls)}

    site = config.SITE_URL.rstrip("/")
    payload = {
        "host": urlsplit(site).netloc,
        "key": config.INDEXNOW_KEY,
        "keyLocation": f"{site}/{config.INDEXNOW_KEY}.txt",
        "urlList": urls[:10000],
    }
    try:
        response = requests.post(
            "https://api.indexnow.org/indexnow",
            json=payload,
            timeout=20,
        )
        if response.status_code not in (200, 202):
            raise RuntimeError(f"IndexNow returned HTTP {response.status_code}")
    except Exception as exc:
        meta.set_value(LAST_ERROR_KEY, str(exc))
        conn.commit()
        return {"status": "error", "reason": str(exc), "count": len(urls)}

    submitted = len(payload["urlList"])
    remaining = urls[submitted:]
    meta.set_value(PENDING_KEY, json.dumps(remaining))
    meta.set_value(LAST_ERROR_KEY, "")
    meta.set_value(LAST_SUBMITTED_KEY, str(submitted))
    conn.commit()
    return {"status": "submitted", "count": submitted}
