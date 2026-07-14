"""Groq-powered conversion of search evidence into grounded SEO actions."""

import json

import requests

from app.core.config import config

ALLOWED_TYPES = {"article", "collection_page", "new_font_demand", "existing_page_improvement"}
ALLOWED_CONFIDENCE = {"low", "medium", "high"}


def enrich_keywords(candidates: list[dict], context: dict) -> list[dict]:
    if not candidates:
        return []
    if not config.oracle.groq_api_key:
        raise RuntimeError("GROQ_ORACLE_API_KEY is not configured")

    fonts = [
        {key: font.get(key) for key in ("slug", "display_name", "category", "use_cases", "status")}
        for font in context.get("fonts", [])[:30]
    ]
    safe_candidates = [
        {key: item.get(key) for key in (
            "slug", "name", "sources", "normalized_score", "trend", "seen_days", "evidence",
            "eligible_font_slugs",
        )}
        for item in candidates[:12]
    ]
    prompt = (
        "You are the SEO opportunity analyst for SINPES, an open-source font archive. Convert only the supplied "
        "search evidence into specific actions. Do not invent volume, growth, font characteristics, licenses, or trends. "
        "Reject vague queries without a useful action. Use only supplied font slugs. Avoid topics duplicating recent titles. "
        "Return exactly one decision for every supplied slug. Set relevant=false when no focused SINPES action exists. "
        "Choose exactly one opportunity_type: article, collection_page, new_font_demand, existing_page_improvement. "
        "matched_font_slugs may only use that candidate's eligible_font_slugs. A collection_page requires at least two "
        "matched fonts. An article requires at least one matched font. "
        "existing_page_improvement requires Bing evidence. With no matching font, use new_font_demand. "
        "Return JSON with an items array. Each item: slug, relevant, cluster, intent, opportunity_type, reason, "
        "recommended_action, matched_font_slugs, confidence (low/medium/high), translations (en/es/pt), and up to five "
        "secondary_keywords. Cluster close variants using the same short cluster value.\n\n"
        + json.dumps({
            "candidates": safe_candidates,
            "font_inventory": fonts,
            "recent_article_titles": context.get("recent_titles", [])[:30],
        }, ensure_ascii=False)
    )
    response = requests.post(
        "https://api.groq.com/openai/v1/chat/completions",
        headers={"Authorization": f"Bearer {config.oracle.groq_api_key}", "Content-Type": "application/json"},
        json={
            "model": config.oracle.groq_model,
            "messages": [{"role": "user", "content": prompt}],
            "response_format": {"type": "json_object"},
            "temperature": 0.1,
            "max_completion_tokens": 2600,
            "reasoning_effort": "low",
        },
        timeout=120,
    )
    response.raise_for_status()
    raw_items = json.loads(response.json()["choices"][0]["message"]["content"]).get("items", [])
    classifications = {item.get("slug"): item for item in raw_items if item.get("slug")}
    enriched = []
    for original in candidates:
        result = classifications.get(original["slug"])
        if not result or not result.get("relevant"):
            continue
        eligible_slugs = set(original.get("eligible_font_slugs") or [])
        matches = [slug for slug in result.get("matched_font_slugs", []) if slug in eligible_slugs][:4]
        kind = result.get("opportunity_type")
        if kind not in ALLOWED_TYPES:
            continue
        if kind == "collection_page" and len(matches) < 2:
            kind = "article" if matches else "new_font_demand"
        if kind == "article" and not matches:
            kind = "new_font_demand"
        if kind == "existing_page_improvement" and "Bing" not in original.get("sources", []):
            kind = "article" if matches else "new_font_demand"
        confidence = result.get("confidence") if result.get("confidence") in ALLOWED_CONFIDENCE else "low"
        translations = result.get("translations") if isinstance(result.get("translations"), dict) else {}
        enriched.append({
            **original,
            "cluster": str(result.get("cluster") or original["slug"]),
            "intent": str(result.get("intent") or ""),
            "opportunity_type": kind,
            "reason": str(result.get("reason") or "Supported by collected search evidence."),
            "recommended_action": str(result.get("recommended_action") or "Review this opportunity."),
            "matched_font_slugs": matches,
            "confidence": confidence,
            "translations": {locale: str(translations.get(locale) or original["name"]) for locale in ("en", "es", "pt")},
            "secondary_keywords": [str(value) for value in result.get("secondary_keywords", [])[:5]],
        })
    return enriched
