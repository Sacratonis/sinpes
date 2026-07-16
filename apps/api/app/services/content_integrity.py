"""Shared, deterministic content-integrity rules for SINPES workflows."""

from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import asdict, dataclass


FUZZY_THRESHOLD = 0.70
ACTIVE_CONTENT_STATUSES = (
    "awaiting_image",
    "pending_review",
    "edited",
    "approved",
    "published",
)
GENERIC_TERMS = {
    "a", "an", "and", "best", "design", "font", "fonts", "for", "free",
    "guide", "in", "of", "the", "to", "top", "type", "typography", "with",
}


class ContentIntegrityError(ValueError):
    """Raised when a deterministic integrity rule blocks publication."""


@dataclass(frozen=True)
class ContentConflict:
    article_id: str
    title: str
    slug: str
    target_keyword: str
    status: str
    reason: str
    score: float = 1.0


def normalize_keyword(value: str) -> str:
    """Normalize case, accents, punctuation, and whitespace without changing intent."""
    separated = "".join(
        " " if unicodedata.category(character).startswith(("P", "S")) else character
        for character in str(value or "")
    )
    normalized = unicodedata.normalize("NFKD", separated)
    ascii_value = normalized.encode("ascii", "ignore").decode("ascii").lower()
    return " ".join(re.findall(r"[a-z0-9]+", ascii_value))


def _fuzzy_terms(value: str) -> set[str]:
    return {term for term in normalize_keyword(value).split() if term not in GENERIC_TERMS}


def keyword_overlap(left: str, right: str) -> float:
    """Return deterministic Jaccard overlap after removing generic SEO terms."""
    left_terms = _fuzzy_terms(left)
    right_terms = _fuzzy_terms(right)
    union = left_terms | right_terms
    return len(left_terms & right_terms) / len(union) if union else 0.0


def _stored_intent_key(raw_source_data: str | None) -> str:
    try:
        payload = json.loads(raw_source_data or "{}")
    except (TypeError, json.JSONDecodeError):
        return ""
    return normalize_keyword(payload.get("intent_key", ""))


def analyze_keyword_conflicts(
    conn,
    target_keyword: str,
    language: str,
    *,
    intent_key: str | None = None,
    exclude_article_id: str | None = None,
) -> dict:
    """Block exact keyword/intent conflicts and report fuzzy overlap as advisory only."""
    normalized_keyword = normalize_keyword(target_keyword)
    normalized_intent = normalize_keyword(intent_key or "")
    if not normalized_keyword and not normalized_intent:
        return {"blocked": False, "hard_conflicts": [], "advisories": []}

    placeholders = ",".join("?" for _ in ACTIVE_CONTENT_STATUSES)
    rows = conn.execute(
        f"""SELECT id,title,slug,target_keyword,status,source_keyword_data
            FROM article_queue
            WHERE language=? AND status IN ({placeholders})""",
        (language, *ACTIVE_CONTENT_STATUSES),
    ).fetchall()
    hard_conflicts: list[ContentConflict] = []
    advisories: list[ContentConflict] = []
    for row in rows:
        row = dict(row)
        if exclude_article_id and row["id"] == exclude_article_id:
            continue
        existing_keyword = str(row.get("target_keyword") or "")
        existing_normalized = normalize_keyword(existing_keyword)
        existing_intent = _stored_intent_key(row.get("source_keyword_data"))
        reason = ""
        if normalized_keyword and normalized_keyword == existing_normalized:
            reason = "exact_target_keyword"
        elif normalized_intent and normalized_intent == existing_intent:
            reason = "exact_intent_key"
        if reason:
            hard_conflicts.append(ContentConflict(
                article_id=str(row["id"]), title=str(row.get("title") or ""),
                slug=str(row.get("slug") or ""), target_keyword=existing_keyword,
                status=str(row.get("status") or ""), reason=reason,
            ))
            continue
        score = keyword_overlap(target_keyword, existing_keyword or str(row.get("title") or ""))
        if score >= FUZZY_THRESHOLD:
            advisories.append(ContentConflict(
                article_id=str(row["id"]), title=str(row.get("title") or ""),
                slug=str(row.get("slug") or ""), target_keyword=existing_keyword,
                status=str(row.get("status") or ""), reason="fuzzy_keyword_overlap",
                score=round(score, 3),
            ))
    return {
        "blocked": bool(hard_conflicts),
        "hard_conflicts": [asdict(item) for item in hard_conflicts],
        "advisories": [asdict(item) for item in advisories],
    }


def enforce_keyword_integrity(
    conn,
    target_keyword: str,
    language: str,
    *,
    intent_key: str | None = None,
    exclude_article_id: str | None = None,
) -> dict:
    report = analyze_keyword_conflicts(
        conn, target_keyword, language, intent_key=intent_key,
        exclude_article_id=exclude_article_id,
    )
    if report["blocked"]:
        conflict = report["hard_conflicts"][0]
        raise ContentIntegrityError(
            f"Target keyword conflicts with {conflict['status']} article "
            f"'{conflict['title']}' ({conflict['reason']})."
        )
    return report


def font_capabilities(font: dict) -> dict:
    try:
        weights = sorted({int(value) for value in json.loads(font.get("weights") or "[]")})
    except (TypeError, ValueError, json.JSONDecodeError):
        weights = []
    try:
        variants = json.loads(font.get("variants") or "[]")
    except (TypeError, json.JSONDecodeError):
        variants = []
    styles = sorted({str(item.get("style", "normal")) for item in variants})
    raw_variable = font.get("is_variable", False)
    if isinstance(raw_variable, str):
        is_variable = raw_variable.strip().lower() in {"1", "true", "yes", "on"}
    else:
        is_variable = bool(raw_variable)
    if not is_variable:
        is_variable = any(bool(item.get("is_variable")) for item in variants if isinstance(item, dict))
    return {"weights": weights, "styles": styles or ["normal"], "is_variable": is_variable}


def validate_evidence_bound_text(title: str, body_html: str, evidence_level: str = "none") -> None:
    """Reject unsupported editorial claims using one shared rule set."""
    plain_text = re.sub(r"<[^>]+>", " ", body_html)
    opening = " ".join(plain_text.split()[:70]).lower()
    if any(phrase in opening for phrase in (
        "plays a pivotal role", "as we move into", "continues to evolve",
        "in today's world", "in today’s world", "have you ever wondered",
    )):
        raise ContentIntegrityError("Content begins with generic scene-setting filler")
    if any(phrase in plain_text.lower() for phrase in (
        "reduce ink", "ink efficient", "ink-efficient", "environmental impact", "eco-conscious",
    )):
        raise ContentIntegrityError("Content contains an unsupported environmental claim")
    linked_font_paragraphs = re.findall(
        r"<p\b[^>]*>(?:(?!</p>).)*?/font/(?:(?!</p>).)*?</p>",
        body_html,
        re.I | re.S,
    )
    if any(
        re.search(
            r"\b(x[‑-]?height|stroke contrast|stroke thickness|ascenders?|descenders?|glyph shapes?|letterform proportions|small caps|average character width|designed for|clean|modern|elegant|geometric|expressive|decorative|versatile)\b",
            paragraph, re.I,
        )
        for paragraph in linked_font_paragraphs
    ):
        raise ContentIntegrityError("Content makes an unsupported font-anatomy claim")
    if evidence_level != "measured_trend":
        if re.search(r"\btrends?\b|\b20\d{2}\b", title, re.I):
            raise ContentIntegrityError("Content title claims a trend or year without measured trend evidence")
        combined = f"{title} {plain_text}".lower()
        if any(re.search(pattern, combined) for pattern in (
            r"\b20\d{2}\s+is\s+(witnessing|seeing)", r"\blatest trends?\b",
            r"\bcurrent trends?\b", r"\bsurge in\b", r"\bon the rise\b",
        )):
            raise ContentIntegrityError("Content makes current-trend claims without measured trend evidence")


def validate_font_claims(claims: list[dict], fonts: list[dict], referenced: list[str], body: str) -> list[dict]:
    """Allow only font capabilities backed by structured registry fields."""
    if not isinstance(claims, list):
        raise ContentIntegrityError("font_claims must be an array")
    by_slug = {font["slug"]: font for font in fonts}
    claim_by_slug = {claim.get("slug"): claim for claim in claims if isinstance(claim, dict)}
    if not set(referenced).issubset(claim_by_slug):
        raise ContentIntegrityError("Every referenced font requires a structured font claim")
    for slug in referenced:
        capabilities = font_capabilities(by_slug[slug])
        claim = claim_by_slug[slug]
        claimed_weights = {int(value) for value in claim.get("weights", [])}
        claimed_styles = {str(value) for value in claim.get("styles", [])}
        if not claimed_weights.issubset(set(capabilities["weights"])):
            raise ContentIntegrityError(f"Unsupported weight claim for {slug}")
        if not claimed_styles.issubset(set(capabilities["styles"])):
            raise ContentIntegrityError(f"Unsupported style claim for {slug}")
        if claim.get("is_variable") and not capabilities["is_variable"]:
            raise ContentIntegrityError(f"Unsupported variable-font claim for {slug}")
    lowered = body.lower()
    plain_body = re.sub(r"</(?:p|li|h[1-6]|blockquote)>", ". ", body, flags=re.I)
    plain_body = re.sub(r"<[^>]+>", " ", plain_body)
    if "variable font" in lowered and not any(font_capabilities(font)["is_variable"] for font in fonts):
        raise ContentIntegrityError("Content makes an unsupported variable-font claim")
    for font in fonts:
        name = str(font.get("display_name") or "").lower()
        if not name:
            continue
        capabilities = font_capabilities(font)
        sentences = [part.strip() for part in re.split(r"[.!?]", plain_body.lower()) if name in part]
        for sentence in sentences:
            if not re.match(r"^(apply|test|compare|use|set|switch|repeat|try|swap|run)\b", sentence):
                raise ContentIntegrityError(f"Font reference for {font['slug']} must be a neutral action statement")
            if re.search(r"\b(because|for its|with its|feels|looks|appears|offers|provides|features|known for|suited for|ideal for|perfect for)\b", sentence):
                raise ContentIntegrityError(f"Font reference for {font['slug']} contains an unsupported descriptive claim")
            if re.search(r"wide range of weights|multiple weights|range of weights", sentence) and len(capabilities["weights"]) < 3:
                raise ContentIntegrityError(f"Content exaggerates available weights for {font['slug']}")
            if re.search(r"italics?|italic styles?", sentence) and "italic" not in capabilities["styles"]:
                raise ContentIntegrityError(f"Content makes an unsupported italic claim for {font['slug']}")
            if re.search(r"\bbold\b", sentence) and not any(weight >= 600 for weight in capabilities["weights"]):
                raise ContentIntegrityError(f"Content makes an unsupported bold claim for {font['slug']}")
    return [claim_by_slug[slug] for slug in referenced]
