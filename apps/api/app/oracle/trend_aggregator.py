"""Evidence-backed SEO opportunity collection for the SINPES Oracle."""

import json
import logging
import re
import time
from collections import defaultdict
from datetime import datetime, timezone

from app.core.config import config
from app.oracle.groq_enricher import enrich_keywords
from app.oracle.scrapers.autocomplete import scrape_autocomplete
from app.oracle.scrapers.bing import scrape_bing_trends
from app.oracle.scrapers.pinterest import scrape_pinterest
from app.oracle.scrapers.yandex import scrape_yandex_trends

logger = logging.getLogger("sinpes.oracle.aggregator")

SOURCE_RELIABILITY = {
    "Bing": 1.0,
    "Pinterest": 0.9,
    "Google Autocomplete": 0.75,
    "Yandex": 0.85,
}
STOP_WORDS = {
    "a", "an", "and", "best", "choose", "design", "font", "fonts", "for", "free",
    "how", "of", "the", "to", "typography", "your",
}
UNSUPPORTED_INTENT = re.compile(r"(?i)\b(commercial use|licen[cs](?:e|ed|es|ing)?)\b")


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")[:100]


def _table_columns(db_conn, table: str) -> set[str]:
    try:
        return {row["name"] for row in db_conn.execute(f"PRAGMA table_info({table})").fetchall()}
    except Exception:
        return set()


def _load_site_context(db_conn) -> dict:
    fonts = []
    font_columns = _table_columns(db_conn, "font_registry")
    if font_columns:
        wanted = [name for name in ("slug", "display_name", "category", "use_cases", "status") if name in font_columns]
        rows = db_conn.execute(f"SELECT {', '.join(wanted)} FROM font_registry").fetchall()
        for row in rows:
            item = dict(row)
            try:
                item["use_cases"] = json.loads(item.get("use_cases") or "[]")
            except (TypeError, json.JSONDecodeError):
                item["use_cases"] = []
            fonts.append(item)

    categories = []
    if _table_columns(db_conn, "categories"):
        categories = [dict(row) for row in db_conn.execute(
            "SELECT slug, display_name FROM categories ORDER BY slug"
        ).fetchall()]

    recent_titles = []
    article_columns = _table_columns(db_conn, "article_queue")
    if "title" in article_columns:
        recent_titles = [row["title"] for row in db_conn.execute(
            "SELECT title FROM article_queue WHERE title IS NOT NULL ORDER BY created_at DESC LIMIT 30"
        ).fetchall()]
    return {"fonts": fonts, "categories": categories, "recent_titles": recent_titles}


def _autocomplete_seeds(context: dict) -> list[str]:
    seeds = [
        "best fonts for", "free fonts for", "font pairing for", "font alternative to",
        "typography for", "how to choose fonts for",
    ]
    categories = [item.get("slug", "").replace("-", " ") for item in context["categories"]]
    if not categories:
        categories = sorted({item.get("category", "").replace("-", " ") for item in context["fonts"]})
    for category in [value for value in categories if value][:6]:
        seeds.extend((f"free {category} fonts", f"{category} font for"))

    use_cases = []
    for font in context["fonts"]:
        use_cases.extend(font.get("use_cases") or [])
    for use_case in list(dict.fromkeys(str(value).lower() for value in use_cases if value))[:8]:
        seeds.append(f"best fonts for {use_case}")
    return list(dict.fromkeys(seeds))[:26]


def _meaningful_tokens(value: str) -> set[str]:
    tokens = set()
    for token in re.findall(r"[a-z0-9]+", value.lower()):
        normalized = token[:-1] if token.endswith("s") and len(token) > 4 else token
        if normalized not in STOP_WORDS:
            tokens.add(normalized)
    return tokens


def _eligible_font_slugs(query: str, context: dict) -> list[str]:
    query_tokens = _meaningful_tokens(query)
    if not query_tokens:
        return []
    category_token_sets = {
        item.get("slug"): _meaningful_tokens(item.get("slug", "").replace("-", " "))
        for item in context.get("categories", [])
    }
    if not category_token_sets:
        category_token_sets = {
            font.get("category"): _meaningful_tokens(str(font.get("category", "")).replace("-", " "))
            for font in context["fonts"] if font.get("category")
        }
    category_vocabulary = set().union(*category_token_sets.values()) if category_token_sets else set()
    requested_category_tokens = query_tokens & category_vocabulary
    requested_use_case_tokens = query_tokens - category_vocabulary
    matches = []
    for font in context["fonts"]:
        if font.get("status") not in (None, "active"):
            continue
        font_category_tokens = _meaningful_tokens(str(font.get("category", "")).replace("-", " "))
        font_use_case_tokens = _meaningful_tokens(" ".join(font.get("use_cases") or []))
        category_matches = not requested_category_tokens or font_category_tokens <= query_tokens
        use_case_matches = not requested_use_case_tokens or bool(requested_use_case_tokens & font_use_case_tokens)
        if category_matches and use_case_matches:
            matches.append(font.get("slug"))
    return [value for value in matches if value][:6]


def _evidence_reason(item: dict) -> str:
    reasons = []
    for row in item.get("evidence", []):
        source = row.get("source")
        if source == "Google Autocomplete":
            appearances = int(row.get("appearances") or 1)
            position = row.get("best_position")
            reasons.append(
                f"Google Autocomplete returned it from {appearances} tracked seed{'s' if appearances != 1 else ''}"
                + (f"; best position {position}" if position else "")
            )
        elif source == "Bing":
            reasons.append(f"Bing recorded {row.get('impressions', 0)} impressions and {row.get('clicks', 0)} clicks")
        elif source == "Pinterest":
            reasons.append(f"Pinterest reported {row.get('score', 0)}% growth in {row.get('region', 'the tracked region')}")
        else:
            reasons.append(f"{source} supplied a {row.get('metric', 'search')} signal")
    history = f"seen on {item.get('seen_days', 1)} tracked day{'s' if item.get('seen_days', 1) != 1 else ''}"
    return ("; ".join(reasons) + f"; {history}.").strip("; ")


def _ground_contract(item: dict) -> dict:
    matches = [slug for slug in item.get("matched_font_slugs", []) if slug in item.get("eligible_font_slugs", [])][:4]
    kind = item.get("opportunity_type")
    if kind == "collection_page" and len(matches) < 2:
        kind = "article" if matches else "new_font_demand"
    if kind == "article" and not matches:
        kind = "new_font_demand"
    if kind == "existing_page_improvement" and "Bing" not in item.get("sources", []):
        kind = "article" if matches else "new_font_demand"
    if kind not in {"article", "collection_page", "new_font_demand", "existing_page_improvement"}:
        kind = "article" if matches else "new_font_demand"

    if kind == "existing_page_improvement":
        action = f"Improve the existing page receiving Bing impressions for “{item['name']}”."
    elif kind == "collection_page":
        action = f"Build a focused “{item['name']}” collection using {', '.join(matches)} as archive examples."
    elif kind == "article":
        action = f"Write a practical article answering “{item['name']}” and use {', '.join(matches)} as archive examples."
    else:
        action = f"Research and ingest an open-source font that directly addresses “{item['name']}”."

    appearances = max((int(row.get("appearances") or 1) for row in item.get("evidence", [])), default=1)
    source_count = len(item.get("sources") or [])
    seen_days = int(item.get("seen_days") or 1)
    confidence = "high" if source_count > 1 or seen_days >= 3 else "medium" if appearances > 1 or seen_days > 1 else "low"
    return {
        **item,
        "opportunity_type": kind,
        "matched_font_slugs": matches,
        "recommended_action": action,
        "reason": _evidence_reason(item),
        "confidence": confidence,
    }


def _default_sources(context: dict) -> dict:
    sources = {
        "Bing": lambda: scrape_bing_trends(),
        "Google Autocomplete": lambda: scrape_autocomplete(_autocomplete_seeds(context)),
    }
    if config.oracle.pinterest_enabled:
        sources["Pinterest"] = lambda: scrape_pinterest()
    return sources


# Tests may replace this with deterministic collectors. Production builds sources from site context.
SOURCES = None


def _normalize_source_rows(source: str, rows: list[dict], db_conn) -> list[dict]:
    cleaned = []
    for row in rows:
        name = str(row.get("name", "")).strip()
        slug = _slug(name)
        if not slug:
            continue
        cleaned.append({**row, "name": name, "slug": slug, "source": source})
    cleaned.sort(key=lambda item: float(item.get("score", 0)), reverse=True)
    count = len(cleaned)
    reliability = SOURCE_RELIABILITY.get(source, 0.7)
    for index, item in enumerate(cleaned):
        percentile = 100.0 if count == 1 else 40.0 + 60.0 * (count - index - 1) / (count - 1)
        repeat_boost = min(max(int(item.get("appearances", 1)) - 1, 0), 5) * 3
        current_day = datetime.now(timezone.utc).date().isoformat()
        previous = db_conn.execute(
            "SELECT MAX(normalized_score) AS normalized_score FROM oracle_keyword_history "
            "WHERE slug = ? AND source = ? AND substr(collected_at, 1, 10) < ? "
            "GROUP BY substr(collected_at, 1, 10) ORDER BY substr(collected_at, 1, 10) DESC LIMIT 6",
            (item["slug"], source, current_day),
        ).fetchall()
        previous_scores = [float(row["normalized_score"]) for row in previous]
        specificity_boost = min(max(len(_meaningful_tokens(item["name"])) - 1, 0) * 2, 8)
        score = min(
            100.0,
            percentile * reliability + repeat_boost + specificity_boost + min(len(previous_scores), 5) * 2,
        )
        if not previous_scores:
            trend = "new"
        else:
            average = sum(previous_scores) / len(previous_scores)
            trend = "rising" if score > average + 5 else "falling" if score < average - 5 else "stable"
        item["normalized_score"] = round(score, 1)
        item["seen_days"] = len(previous_scores) + 1
        item["trend"] = trend
    return cleaned


def _fallback_contract(item: dict, context: dict) -> dict:
    matches = item.get("eligible_font_slugs", [])[:4]
    source_names = item.get("sources") or [item.get("source")]
    if "Bing" in source_names:
        kind = "existing_page_improvement"
        action = f"Improve the existing page that is already receiving impressions for “{item['name']}”."
    elif len(matches) >= 2:
        kind = "collection_page"
        action = f"Create a focused collection page for “{item['name']}” using the matched archive fonts."
    elif matches:
        kind = "article"
        action = f"Draft a practical article for “{item['name']}” and link the matched font."
    else:
        kind = "new_font_demand"
        action = f"Find and ingest an open-source font that directly answers “{item['name']}”."
    return _ground_contract({
        **item,
        "opportunity_type": kind,
        "recommended_action": action,
        "matched_font_slugs": matches,
        "confidence": "low",
        "reason": "",
        "cluster": item["slug"],
        "translations": {"en": item["name"], "es": item["name"], "pt": item["name"]},
        "secondary_keywords": [],
    })


def _deduplicate_clusters(items: list[dict]) -> list[dict]:
    best = {}
    for item in items:
        cluster = _slug(str(item.get("cluster") or item["slug"])) or item["slug"]
        if cluster not in best or item["normalized_score"] > best[cluster]["normalized_score"]:
            best[cluster] = item
    return sorted(best.values(), key=lambda item: item["normalized_score"], reverse=True)[:10]


def run_oracle(db_conn) -> dict:
    """Collect evidence, preserve history, build opportunities, and persist the latest hitlist."""
    started_clock = time.time()
    started_at = datetime.now(timezone.utc).isoformat()
    context = _load_site_context(db_conn)
    statuses = {}
    combined = []
    sources = SOURCES if SOURCES is not None else _default_sources(context)

    statuses["Pinterest"] = {"status": "disabled", "count": 0}
    if config.oracle.pinterest_enabled and "Pinterest" not in sources:
        sources = {**sources, "Pinterest": lambda: scrape_pinterest()}
    for source, scraper in sources.items():
        try:
            rows = scraper()
            combined.extend(_normalize_source_rows(source, rows, db_conn))
            statuses[source] = {"status": "ok", "count": len(rows)}
        except Exception as exc:
            message = str(exc)
            state = "not_configured" if "not configured" in message else "error"
            statuses[source] = {"status": state, "count": 0, "error": message[:300]}
            logger.warning("Oracle source %s: %s", source, message)

    if config.oracle.yandex_enabled:
        try:
            rows = scrape_yandex_trends()
            combined.extend(_normalize_source_rows("Yandex", rows, db_conn))
            statuses["Yandex"] = {"status": "ok", "count": len(rows)}
        except Exception as exc:
            message = str(exc)
            statuses["Yandex"] = {"status": "error", "count": 0, "error": message[:300]}
    else:
        statuses["Yandex"] = {"status": "disabled", "count": 0}

    archived = {row["slug"] for row in db_conn.execute("SELECT slug FROM font_registry").fetchall()}
    grouped = defaultdict(list)
    for item in combined:
        if item["slug"] not in archived:
            grouped[item["slug"]].append(item)

    candidates = []
    for slug, evidence_rows in grouped.items():
        strongest = max(evidence_rows, key=lambda item: item["normalized_score"])
        if UNSUPPORTED_INTENT.search(strongest["name"]):
            continue
        category_names = {item.get("slug", "").replace("-", " ") for item in context.get("categories", [])}
        malformed = re.match(r"^fonts? for (.+)$", strongest["name"].lower())
        if malformed and malformed.group(1).strip() in category_names:
            continue
        sources_for_query = list(dict.fromkeys(item["source"] for item in evidence_rows))
        candidates.append({
            **strongest,
            "sources": sources_for_query,
            "evidence": [{key: item.get(key) for key in (
                "source", "region", "metric", "score", "normalized_score", "appearances",
                "best_position", "impressions", "clicks", "query_seeds",
            ) if item.get(key) is not None} for item in evidence_rows],
            "normalized_score": min(100.0, strongest["normalized_score"] + 5 * (len(sources_for_query) - 1)),
            "eligible_font_slugs": _eligible_font_slugs(strongest["name"], context),
        })
    candidates.sort(key=lambda item: item["normalized_score"], reverse=True)
    candidates = candidates[:12]

    for item in combined:
        db_conn.execute(
            "INSERT INTO oracle_keyword_history(slug, name, source, raw_score, normalized_score, metric, payload, collected_at) "
            "VALUES(?, ?, ?, ?, ?, ?, ?, ?)",
            (item["slug"], item["name"], item["source"], float(item.get("score", 0)),
             float(item.get("normalized_score", 0)), item.get("metric"), json.dumps(item), started_at),
        )

    groq_succeeded = False
    try:
        enriched = enrich_keywords(candidates, context)
        groq_succeeded = True
        statuses["Groq"] = {"status": "ok", "count": len(enriched), "reviewed": len(candidates)}
    except Exception as exc:
        message = str(exc)
        statuses["Groq"] = {"status": "error", "count": 0, "error": message[:300]}
        logger.warning("Oracle Groq enrichment: %s", exc)
        enriched = []

    if groq_succeeded:
        opportunities = [_ground_contract(item) for item in enriched]
    else:
        opportunities = [_fallback_contract(item, context) for item in candidates]
    opportunities = _deduplicate_clusters(opportunities)

    db_conn.execute("DELETE FROM oracle_keywords")
    collected_at = datetime.now(timezone.utc).isoformat()
    for rank, item in enumerate(opportunities, start=1):
        db_conn.execute(
            "INSERT INTO oracle_keywords(slug, name, source, region, score, metric, rank, payload, collected_at) "
            "VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (item["slug"], item["name"], ", ".join(item.get("sources") or [item.get("source", "Unknown")]),
             item.get("region"), float(item.get("normalized_score", 0)), "normalized_opportunity_score",
             rank, json.dumps(item), collected_at),
        )
    summary = {
        "started_at": started_at,
        "finished_at": collected_at,
        "duration_seconds": round(time.time() - started_clock, 2),
        "keyword_count": len(opportunities),
        "sources": statuses,
    }
    db_conn.execute(
        "INSERT OR REPLACE INTO meta(key, value) VALUES('oracle_last_run', ?)",
        (json.dumps(summary),),
    )
    db_conn.commit()
    return summary


def fetch_oracle_hitlist(db_conn) -> list[dict]:
    rows = db_conn.execute("SELECT payload FROM oracle_keywords ORDER BY rank ASC LIMIT 48").fetchall()
    return [json.loads(row["payload"]) for row in rows]


def get_oracle_status(db_conn) -> dict:
    row = db_conn.execute("SELECT value FROM meta WHERE key = 'oracle_last_run'").fetchone()
    if not row:
        return {"status": "never_run", "keyword_count": 0, "sources": {}}
    return {"status": "ready", **json.loads(row["value"])}


def _type_label(value: str) -> str:
    return {
        "article": "Article",
        "collection_page": "Collection page",
        "new_font_demand": "New font demand",
        "existing_page_improvement": "Existing-page improvement",
    }.get(value, value.replace("_", " ").title())


def format_oracle_hitlist(results: list[dict], limit: int = 8, heading: str = "Oracle opportunities") -> str:
    if not results:
        return "No useful SEO opportunities were collected. Use /oracle_status for source details."
    lines = [f"{heading}: {len(results)} total."]
    for index, item in enumerate(results[:limit], start=1):
        fonts = ", ".join(item.get("matched_font_slugs") or []) or "No archive match"
        evidence = "; ".join(
            f"{row.get('source')}: {row.get('metric', 'signal')} {row.get('score', '')}".strip()
            for row in item.get("evidence", [])
        )
        lines.extend([
            f"\n{index}. {item['name']}",
            f"Type: {_type_label(item.get('opportunity_type', ''))} · Priority: {round(item.get('normalized_score', 0))}/100 · {item.get('confidence', 'low')} confidence",
            f"Why: {item.get('reason', 'Search evidence collected.')}",
            f"Action: {item.get('recommended_action', 'Review this opportunity.')}",
            f"Fonts: {fonts}",
            f"Evidence: {evidence or item.get('source', 'Unknown source')} · {item.get('trend', 'new')}",
        ])
    return "\n".join(lines)[:4000]


def format_oracle_briefing(results: list[dict], limit: int = 5) -> str:
    return format_oracle_hitlist(results, limit=limit, heading="Oracle morning briefing")
