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
