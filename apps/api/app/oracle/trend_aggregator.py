"""SEO demand collection and ranking for the SINPES Oracle."""

import json
import logging
import re
import time
from datetime import datetime, timezone

from app.oracle.scrapers.bing import scrape_bing_trends
from app.oracle.scrapers.pinterest import scrape_pinterest
from app.oracle.scrapers.yandex import scrape_yandex_trends
from app.oracle.gemini_enricher import enrich_keywords

logger = logging.getLogger("sinpes.oracle.aggregator")

SOURCES = {
    "Pinterest": scrape_pinterest,
    "Bing": scrape_bing_trends,
    "Yandex": scrape_yandex_trends,
}


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")[:80]


def run_oracle(db_conn) -> dict:
    """Collect from each configured source, persist results, and return run status."""
    started = time.time()
    statuses = {}
    combined = []
    for source, scraper in SOURCES.items():
        try:
            rows = scraper()
            combined.extend(rows)
            statuses[source] = {"status": "ok", "count": len(rows)}
        except Exception as exc:
            message = str(exc)
            state = "not_configured" if "not configured" in message else "error"
            statuses[source] = {"status": state, "count": 0, "error": message[:300]}
            logger.warning("Oracle source %s: %s", source, message)

    archived = {
        row["slug"] for row in db_conn.execute("SELECT slug FROM font_registry").fetchall()
    }
    best = {}
    for item in combined:
        name = str(item.get("name", "")).strip()
        slug = _slug(name)
        if not slug or slug in archived:
            continue
        normalized = {
            **item,
            "slug": slug,
            "keywords": {
                "en": f"free {name} font alternative",
                "es": f"alternativa gratis de fuente {name}",
                "pt": f"alternativa gratuita de fonte {name}",
            },
        }
        if slug not in best or float(normalized.get("score", 0)) > float(best[slug].get("score", 0)):
            best[slug] = normalized

    ranked = sorted(best.values(), key=lambda item: float(item.get("score", 0)), reverse=True)[:48]
    try:
        ranked = enrich_keywords(ranked)
        statuses["Gemini"] = {"status": "ok", "count": len(ranked)}
    except Exception as exc:
        # Data collection remains useful if AI enrichment is temporarily unavailable.
        message = str(exc)
        state = "not_configured" if "not configured" in message else "error"
        statuses["Gemini"] = {"status": state, "count": 0, "error": message[:300]}
        logger.warning("Oracle Gemini enrichment: %s", exc)
    run_at = datetime.now(timezone.utc).isoformat()
    db_conn.execute("DELETE FROM oracle_keywords")
    for rank, item in enumerate(ranked, start=1):
        db_conn.execute(
            "INSERT INTO oracle_keywords(slug, name, source, region, score, metric, rank, payload, collected_at) "
            "VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (item["slug"], item["name"], item["source"], item.get("region"),
             float(item.get("score", 0)), item.get("metric"), rank, json.dumps(item), run_at),
        )
    summary = {
        "started_at": run_at,
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "duration_seconds": round(time.time() - started, 2),
        "keyword_count": len(ranked),
        "sources": statuses,
    }
    db_conn.execute(
        "INSERT OR REPLACE INTO meta(key, value) VALUES('oracle_last_run', ?)",
        (json.dumps(summary),),
    )
    db_conn.commit()
    return summary


def fetch_oracle_hitlist(db_conn) -> list[dict]:
    rows = db_conn.execute(
        "SELECT payload FROM oracle_keywords ORDER BY rank ASC LIMIT 48"
    ).fetchall()
    return [json.loads(row["payload"]) for row in rows]


def get_oracle_status(db_conn) -> dict:
    row = db_conn.execute("SELECT value FROM meta WHERE key = 'oracle_last_run'").fetchone()
    if not row:
        return {"status": "never_run", "keyword_count": 0, "sources": {}}
    return {"status": "ready", **json.loads(row["value"])}


def format_oracle_briefing(results: list[dict], limit: int = 12) -> str:
    if not results:
        return "Oracle morning briefing: no keyword opportunities were collected. Use /oracle_status for details."
    lines = [f"Oracle morning briefing: {len(results)} SEO opportunities."]
    for index, item in enumerate(results[:limit], start=1):
        lines.append(f"{index}. {item['name']} — {item['source']}")
    return "\n".join(lines)
