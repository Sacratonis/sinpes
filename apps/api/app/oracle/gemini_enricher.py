"""Gemini-powered SEO classification without altering source metrics."""

import json
import requests

from app.core.config import config


OUTPUT_SCHEMA = {
    "type": "array",
    "items": {
        "type": "object",
        "properties": {
            "slug": {"type": "string"},
            "relevant": {"type": "boolean"},
            "intent": {
                "type": "string",
                "enum": ["download", "alternative", "identify", "inspiration", "informational"],
            },
            "cluster": {"type": "string"},
            "content_type": {
                "type": "string",
                "enum": ["font_page", "category_page", "use_case_page", "comparison_page", "blog_article"],
            },
            "reason": {"type": "string"},
            "translations": {
                "type": "object",
                "properties": {
                    "en": {"type": "string"},
                    "es": {"type": "string"},
                    "pt": {"type": "string"},
                },
                "required": ["en", "es", "pt"],
            },
            "secondary_keywords": {
                "type": "array", "items": {"type": "string"}, "maxItems": 5,
            },
        },
        "required": ["slug", "relevant", "intent", "cluster", "content_type", "reason", "translations", "secondary_keywords"],
    },
}

DISCOVERY_PROMPT = """You are the trend researcher for SINPES, an open-source font archive.
Use Google Search to find current, useful search demand and design interest around free fonts,
typefaces, typography styles, lettering, branding typography, editorial typography, UI fonts,
wedding fonts, poster fonts, and font alternatives. Focus on actionable phrases people could
search for in English, Spanish, or Portuguese. Exclude celebrity news, unrelated visual trends,
pirated commercial fonts, and generic topics without clear typography intent.

Return ONLY a JSON array with at most 20 objects. Each object must contain:
name (a natural search phrase), intent (download, alternative, identify, inspiration, or
informational), reason (one short sentence explaining the current evidence), and
secondary_keywords (up to 5 closely related phrases). Do not invent search volume, growth,
clicks, rankings, or percentages. Return [] if there is no grounded evidence."""


def _parse_json_array(value: str) -> list[dict]:
    value = value.strip()
    if value.startswith("```"):
        value = value.split("\n", 1)[1].rsplit("```", 1)[0]
        if value.lstrip().startswith("json"):
            value = value.lstrip()[4:].lstrip()
    result = json.loads(value)
    if not isinstance(result, list):
        raise RuntimeError("Gemini discovery did not return a JSON array")
    return result


def discover_keywords() -> list[dict]:
    """Discover current typography opportunities with Google Search grounding."""
    if not config.oracle.gemini_discovery:
        return []
    if not config.oracle.gemini_api_key:
        raise RuntimeError("GEMINI_ORACLE_API_KEY is not configured")
    response = requests.post(
        f"https://generativelanguage.googleapis.com/v1beta/models/{config.oracle.gemini_model}:generateContent",
        headers={"x-goog-api-key": config.oracle.gemini_api_key, "Content-Type": "application/json"},
        json={
            "contents": [{"parts": [{"text": DISCOVERY_PROMPT}]}],
            "tools": [{"google_search": {}}],
            "generationConfig": {"temperature": 0.2},
        },
        timeout=90,
    )
    response.raise_for_status()
    body = response.json()
    candidate = body["candidates"][0]
    text = candidate["content"]["parts"][0]["text"]
    metadata = candidate.get("groundingMetadata", {})
    search_queries = metadata.get("webSearchQueries", [])
    source_urls = [
        chunk.get("web", {}).get("uri")
        for chunk in metadata.get("groundingChunks", [])
        if chunk.get("web", {}).get("uri")
    ]
    discovered = []
    for item in _parse_json_array(text)[:20]:
        name = str(item.get("name", "")).strip()
        if not name:
            continue
        discovered.append({
            "name": name,
            "source": "Gemini Search",
            "region": "global",
            "score": 1.0,
            "metric": "grounded_discovery",
            "discovery": {
                "intent": item.get("intent"),
                "reason": item.get("reason"),
                "secondary_keywords": item.get("secondary_keywords", [])[:5],
                "search_queries": search_queries,
                "source_urls": source_urls[:10],
            },
        })
    return discovered


def enrich_keywords(keywords: list[dict]) -> list[dict]:
    if not config.oracle.gemini_enrichment:
        return keywords
    if not config.oracle.gemini_api_key:
        raise RuntimeError("GEMINI_ORACLE_API_KEY is not configured")
    if not keywords:
        return []

    enriched = []
    for start in range(0, len(keywords), 20):
        batch = keywords[start:start + 20]
        safe_input = [
            {"slug": item["slug"], "keyword": item["name"], "source": item["source"]}
            for item in batch
        ]
        prompt = (
            "You are the SEO classifier for SINPES, an open-source font archive. "
            "Classify only the supplied keywords. Reject unrelated topics. Group close variants. "
            "Translate the search phrase naturally into English, Spanish, and Portuguese. "
            "Recommend one useful page type. Never invent or estimate search volume, impressions, "
            "clicks, growth, rankings, or other metrics. Return one object for every supplied slug.\n\n"
            + json.dumps(safe_input, ensure_ascii=False)
        )
        response = requests.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/{config.oracle.gemini_model}:generateContent",
            headers={"x-goog-api-key": config.oracle.gemini_api_key, "Content-Type": "application/json"},
            json={
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {
                    "responseMimeType": "application/json",
                    "responseSchema": OUTPUT_SCHEMA,
                    "temperature": 0.1,
                },
            },
            timeout=60,
        )
        response.raise_for_status()
        body = response.json()
        text = body["candidates"][0]["content"]["parts"][0]["text"]
        classifications = {item["slug"]: item for item in json.loads(text)}
        for original in batch:
            classification = classifications.get(original["slug"])
            if not classification or not classification.get("relevant"):
                continue
            # Source metrics remain authoritative and untouched.
            enriched.append({**original, "seo": classification})
    return enriched
