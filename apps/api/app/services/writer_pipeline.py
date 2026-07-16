"""One-call, catalog-grounded SEO article generation for SINPES."""

import html
import json
import re
import uuid
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser

import requests

from app.core.config import config
from app.services.article_image_service import build_generated_article_image
from app.services.content_integrity import (
    ContentIntegrityError,
    enforce_keyword_integrity,
    font_capabilities as _font_capabilities,
    validate_evidence_bound_text,
    validate_font_claims as _validate_font_claims,
)


ALLOWED_LANGUAGES = {"en", "es", "pt"}
SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
SCOPE_ORDER = {"brief": 0, "guide": 1, "deep_dive": 2}
SCOPE_RANGES = {"brief": (450, 750), "guide": (650, 1200), "deep_dive": (1000, 1800)}
SCOPE_SECTIONS = {"brief": 3, "guide": 5, "deep_dive": 7}


class InsufficientDepth(ValueError):
    def __init__(self, scope: str, word_count: int, suggestion: str):
        self.scope = scope
        self.word_count = word_count
        self.suggestion = suggestion
        super().__init__(f"{scope} draft has {word_count} words; suggested narrower angle: {suggestion}")


class WriterValidationFailure(ValueError):
    def __init__(self, reason: str, draft: dict):
        self.reason = reason
        self.draft = draft
        super().__init__(reason)


def _required_scope(topic: str) -> str:
    value = topic.lower()
    if re.search(r"deep dive|comprehensive|history of|full analysis", value):
        return "deep_dive"
    if re.search(r"guide|essentials|mastering|checklist|workflow|system", value):
        return "guide"
    return "brief"


def _narrower_angle(topic: str) -> str:
    value = topic.lower()
    if "ui" in value or "user interface" in value:
        return "How to set font size, line height, and weight for readable UI body text"
    if "editorial" in value:
        return "How to build a clear editorial hierarchy with two complementary fonts"
    if "branding" in value:
        return "How to choose one display font and one supporting text font for a brand system"
    return "Focus on one concrete typography decision, constraint, and practical test"


class _ArticleHTMLValidator(HTMLParser):
    allowed = {"p", "h2", "h3", "ul", "ol", "li", "strong", "em", "a", "pre", "code", "blockquote"}

    def __init__(self):
        super().__init__()
        self.stack = []
        self.h2_ids = set()

    def handle_starttag(self, tag, attrs):
        if tag not in self.allowed:
            raise ValueError(f"Unsupported HTML tag: {tag}")
        attributes = dict(attrs)
        if tag == "h2":
            heading_id = attributes.get("id", "")
            if not SLUG_RE.fullmatch(heading_id) or heading_id in self.h2_ids:
                raise ValueError("Every H2 requires a unique kebab-case id")
            self.h2_ids.add(heading_id)
        if tag == "a" and not attributes.get("href", "").startswith("/font/"):
            raise ValueError("Article links must point to SINPES font pages")
        self.stack.append(tag)

    def handle_endtag(self, tag):
        if not self.stack or self.stack[-1] != tag:
            expected = self.stack[-1] if self.stack else "nothing"
            raise ValueError(f"Malformed HTML: expected </{expected}>, received </{tag}>")
        self.stack.pop()


def _validate_html(body: str) -> _ArticleHTMLValidator:
    parser = _ArticleHTMLValidator()
    parser.feed(body)
    parser.close()
    if parser.stack:
        raise ValueError(f"Malformed HTML: unclosed <{parser.stack[-1]}>")
    return parser


def _normalize_h2_ids(body: str) -> str:
    seen = set()
    def replace(match):
        content = match.group(1)
        text = re.sub(r"<[^>]+>", " ", content)
        base = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-") or "section"
        heading_id = base
        suffix = 2
        while heading_id in seen:
            heading_id = f"{base}-{suffix}"
            suffix += 1
        seen.add(heading_id)
        return f'<h2 id="{heading_id}">{content}</h2>'
    return re.sub(r"<h2(?:\s+[^>]*)?>(.*?)</h2>", replace, body, flags=re.I | re.S)


def _words(value: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", value.lower())


def _catalog_fonts(conn, topic: str, limit: int = 4) -> list[dict]:
    rows = conn.execute(
        """
        SELECT f.slug, f.display_name, f.category, f.use_cases, f.weights, f.variants, f.is_variable,
               COALESCE(t.description, '') AS description,
               COALESCE(t.seo_image_url, '') AS seo_image_url
        FROM font_registry f
        LEFT JOIN font_translations t ON t.slug = f.slug AND t.locale = 'en'
        WHERE f.status = 'active'
        ORDER BY f.rowid DESC LIMIT 100
        """
    ).fetchall()
    topic_terms = set(_words(topic))

    def score(row):
        text = " ".join(str(row[key] or "") for key in ("display_name", "category", "use_cases", "description"))
        return len(topic_terms.intersection(_words(text)))

    ranked = sorted(rows, key=score, reverse=True)
    return [dict(row) for row in ranked[:limit]]


def _recent_articles(conn) -> list[str]:
    cutoff = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
    rows = conn.execute(
        """SELECT title FROM article_queue
           WHERE created_at >= ? AND title IS NOT NULL
             AND status IN ('pending_review','edited','approved','published')
           ORDER BY created_at DESC LIMIT 10""",
        (cutoff,),
    ).fetchall()
    return [row["title"] for row in rows]


def _topic_terms(value: str) -> set[str]:
    stop = {"a", "an", "and", "for", "in", "of", "the", "to", "top", "tier", "mastering", "secret"}
    return {word for word in _words(value) if word not in stop}


def _find_duplicate(topic: str, recent_titles: list[str]) -> str | None:
    topic_terms = _topic_terms(topic)
    if not topic_terms:
        return None
    for title in recent_titles:
        title_terms = _topic_terms(title)
        union = topic_terms | title_terms
        similarity = len(topic_terms & title_terms) / len(union) if union else 0
        if similarity >= 0.7:
            return title
    return None


def _oracle_signal(conn, topic: str) -> dict:
    row = conn.execute(
        "SELECT payload FROM oracle_keywords WHERE lower(name) = lower(?) LIMIT 1", (topic,)
    ).fetchone()
    return json.loads(row["payload"]) if row else {"name": topic, "source": "manual"}


def _validate_article(payload: dict, fonts: list[dict], language: str, evidence_level: str = "none", required_scope: str = "brief", fallback_suggestion: str = "Focus on one concrete typography decision") -> dict:
    if payload.get("validity") == "invalid":
        reason = str(payload.get("reasoning", "")).strip()
        if not reason:
            raise ValueError("Invalid topics require a reason")
        return {"validity": "invalid", "reasoning": reason}
    if payload.get("validity") != "valid":
        raise ValueError("Writer response must declare valid or invalid")

    required = ("title", "slug", "meta_description", "target_keyword", "secondary_keywords", "body_html", "referenced_font_slugs", "font_claims", "content_scope")
    missing = [key for key in required if not payload.get(key)]
    if missing:
        raise ValueError("Writer response is missing: " + ", ".join(missing))
    slug = str(payload["slug"]).strip().lower()
    if not SLUG_RE.fullmatch(slug):
        raise ValueError("Article slug is not valid kebab-case")
    meta = str(payload["meta_description"]).strip()
    if len(meta) > 160:
        raise ValueError("Meta description exceeds 160 characters")
    secondary_keywords = payload["secondary_keywords"]
    if not isinstance(secondary_keywords, list) or not all(isinstance(value, str) for value in secondary_keywords):
        raise ValueError("secondary_keywords must be an array of strings")
    body = str(payload["body_html"]).strip()
    if re.search(r"<\s*(script|iframe|object)\b", body, re.I):
        raise ValueError("Article contains unsafe HTML")
    html_structure = _validate_html(body)
    word_count = len(_words(re.sub(r"<[^>]+>", " ", body)))
    declared_scope = str(payload["content_scope"])
    if declared_scope not in SCOPE_RANGES:
        raise ValueError("content_scope must be brief, guide, or deep_dive")
    scope = required_scope
    minimum, maximum = SCOPE_RANGES[scope]
    content_sections = html_structure.h2_ids - {"conclusion"}
    if len(content_sections) < SCOPE_SECTIONS[scope]:
        raise InsufficientDepth(
            scope, word_count,
            str(payload.get("suggested_narrower_angle") or fallback_suggestion),
        )
    if word_count < minimum:
        suggestion = str(payload.get("suggested_narrower_angle") or fallback_suggestion)
        raise InsufficientDepth(scope, word_count, suggestion)
    if word_count > maximum:
        raise ValueError(f"{scope} article is too long at {word_count} words; maximum is {maximum}")
    validate_evidence_bound_text(str(payload["title"]), body, evidence_level)
    available = {font["slug"] for font in fonts}
    referenced = list(dict.fromkeys(payload["referenced_font_slugs"]))
    if len(referenced) < 2 or not set(referenced).issubset(available):
        raise ValueError("Article must reference at least two supplied SINPES fonts")
    for font_slug in referenced:
        if f'/font/{font_slug}/' not in body and f'/font/{font_slug}' not in body:
            raise ValueError(f"Article is missing an internal link to {font_slug}")
    claims = _validate_font_claims(payload["font_claims"], fonts, referenced, body)
    return {
        **payload,
        "slug": slug,
        "meta_description": meta,
        "secondary_keywords": secondary_keywords,
        "body_html": body,
        "word_count": word_count,
        "language": language,
        "referenced_font_slugs": referenced,
        "font_claims": claims,
        "content_scope": scope,
    }


def _body_word_count(payload: dict) -> int:
    body = str(payload.get("body_html", ""))
    return len(_words(re.sub(r"<[^>]+>", " ", body)))


def _evidence_level(signal: dict) -> str:
    if signal.get("source") == "Pinterest" and signal.get("metric") == "growth_percent":
        return "measured_trend"
    if signal.get("source") == "Bing":
        return "site_performance"
    if signal.get("source") == "Google Autocomplete":
        return "demand_hint"
    return "none"


def generate_article(conn, topic: str, language: str = "en") -> dict:
    language = language.lower()
    if language not in ALLOWED_LANGUAGES:
        raise ValueError("Language must be en, es, or pt")
    if not config.writer.groq_api_key:
        raise RuntimeError("GROQ_WRITER_API_KEY is not configured")
    fonts = _catalog_fonts(conn, topic)
    if len(fonts) < 2:
        raise RuntimeError("At least two active SINPES fonts are required")
    signal = _oracle_signal(conn, topic)
    evidence_level = _evidence_level(signal)
    required_scope = _required_scope(topic)
    recent = _recent_articles(conn)[:6]
    title_overlap_advisory = _find_duplicate(topic, recent)
    font_input = [
        {
            "slug": font["slug"],
            "display_name": font["display_name"],
            "category": font["category"],
            "use_cases": str(font["use_cases"] or "")[:180],
            "weights": _font_capabilities(font)["weights"],
            "styles": _font_capabilities(font)["styles"],
            "is_variable": _font_capabilities(font)["is_variable"],
        }
        for font in fonts
    ]
    compact_signal = {
        "name": signal.get("name", topic),
        "source": signal.get("source", "manual"),
        "region": signal.get("region"),
        "metric": signal.get("metric"),
        "seo": signal.get("seo"),
        "evidence_level": evidence_level,
    }
    current_date = datetime.now(timezone.utc).date().isoformat()
    prompt = f"""You are the editorial SEO writer for SINPES, an open-source typography archive.
Current date: {current_date}. Never present an older year as current. Use the current year and
current-trend language only when evidence_level is measured_trend. Otherwise omit the year and
reframe the topic as practical editorial directions or techniques.
Evaluate the underlying subject first. The submitted phrase may be promotional, vague, or
click-driven; rewrite that framing into a specific practical angle instead of rejecting it when the
underlying typography subject is useful. Duplicate detection has already been handled in Python, so
do not claim a duplicate. Reject only when the subject is unrelated to typography or genuinely
cannot support practical, accurate guidance. If invalid, return ONLY this JSON shape and stop:
{{"validity":"invalid","reasoning":"specific short reason"}}

If valid, write a practical, original article natively in {language}. The BODY alone MUST contain
the natural depth required by its scope. Scope rules: brief=450-750 words with at least 3 useful H2
sections; guide=650-1200 words with at least 5 useful H2 sections; deep_dive=1000-1800 words with at
least 7 useful H2 sections. Plan for a safe target inside each range: brief=650-700 words,
guide=950-1100 words, deep_dive=1400-1650 words. Develop the requested design problem with concrete
decisions, examples, and checks; do not add unrelated sections merely to reach a count. This
topic is classified by Python as exactly {required_scope}; return that exact content_scope. If you cannot reach the
minimum with substantive content, return a suggested_narrower_angle rather than padding. Start with
a specific design problem, observation, or decision. Never
open with "plays a pivotal role", "as we move into", or "continues to evolve". Avoid filler,
invented metrics, and unverifiable claims. Do not make environmental, ink-saving, cultural-origin,
designer-history, language-support, or OpenType claims because no trusted provenance source is supplied.
Do not describe a supplied font's anatomy or appearance—such as its x-height, stroke contrast,
proportions, ascenders, descenders, or glyph shapes—because that evidence is not supplied.
Use supplied fonts only as neutral examples to test or apply. Beyond weights, styles, and variable
status, do not state or compare any property of a supplied font. Any sentence containing a font
link or font name MUST begin with one of these action verbs: Apply, Test, Compare, Use, Set, Switch,
Repeat, Try, Swap, or Run. It may not describe why the font looks, feels, or suits the task.
Reference at least two supplied fonts naturally and link each one using /font/<slug>/. Body must be
safe semantic HTML using p, h2, h3, ul, ol, li, strong, em, a, pre, code, and blockquote tags. Every H2 needs a kebab-case
id. Return JSON only with:
validity, reasoning, title, slug, meta_description (one sentence, max 160 characters), target_keyword,
secondary_keywords, content_scope, suggested_narrower_angle, body_html, referenced_font_slugs,
font_claims, and image_alt_text. font_claims
must contain one object per referenced font with exactly: slug, weights, styles, is_variable. Copy
these values from the supplied structural data; never infer them. Do not create an image prompt.

Topic signal: {json.dumps(compact_signal, ensure_ascii=False)}
Recent titles: {json.dumps(recent, ensure_ascii=False)}
Available SINPES fonts: {json.dumps(font_input, ensure_ascii=False)}"""
    result = None
    retry_instruction = ""
    for attempt in range(2):
        response = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {config.writer.groq_api_key}", "Content-Type": "application/json"},
            json={
                "model": config.writer.groq_model,
                "messages": [{"role": "user", "content": prompt + retry_instruction}],
                "response_format": {"type": "json_object"},
                "temperature": 0.2,
                "max_completion_tokens": 4096,
                "reasoning_effort": "low",
            },
            timeout=120,
        )
        response.raise_for_status()
        raw = json.loads(response.json()["choices"][0]["message"]["content"])
        raw["content_scope"] = required_scope
        if raw.get("body_html"):
            raw["body_html"] = _normalize_h2_ids(str(raw["body_html"]))
        try:
            result = _validate_article(raw, fonts, language, evidence_level, required_scope, _narrower_angle(topic))
            break
        except (InsufficientDepth, ValueError) as exc:
            if attempt == 1:
                raise WriterValidationFailure(str(exc), raw) from exc
            retry_instruction = (
                "\n\nYour previous response was rejected by deterministic validation for this reason: "
                f"{exc}. Rewrite the complete article from scratch. Correct that exact problem while preserving "
                "the topic, required scope, factual limits, and anti-padding rules. Return the full JSON contract."
            )
    if result is None:
        raise RuntimeError("Writer did not return a validated article")
    if result["validity"] == "invalid":
        return result
    if conn.execute("SELECT 1 FROM article_queue WHERE slug = ?", (result["slug"],)).fetchone():
        raise ValueError(f"Article slug already exists: {result['slug']}")
    integrity_report = enforce_keyword_integrity(
        conn, result["target_keyword"], language, intent_key=signal.get("intent_key"),
    )
    if title_overlap_advisory:
        integrity_report["advisories"].append({
            "reason": "fuzzy_title_overlap",
            "title": title_overlap_advisory,
            "score": 0.7,
        })
    referenced_fonts = [font for font in fonts if font["slug"] in result["referenced_font_slugs"]]
    image_url, image_alt_text = build_generated_article_image(result, referenced_fonts)
    now = datetime.now(timezone.utc).isoformat()
    article_id = str(uuid.uuid4())
    conn.execute(
        """INSERT INTO article_queue (
            id, source_topic, source_keyword_data, language, validity, validity_reasoning,
            title, slug, meta_description, target_keyword, secondary_keywords, body_markdown, body_html,
            referenced_font_slugs, font_claims, image_prompt, image_url, image_alt_text, word_count,
            content_scope, status, created_at
        ) VALUES (?, ?, ?, ?, 'valid', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, ?, ?, ?, ?, 'pending_review', ?)""",
        (
            article_id, topic, json.dumps({**signal, "writer_model": config.writer.groq_model, "content_integrity": integrity_report}), language, result.get("reasoning"), result["title"],
            result["slug"], result["meta_description"], result["target_keyword"],
            json.dumps(result.get("secondary_keywords", [])), result["body_html"], result["body_html"],
            json.dumps(result["referenced_font_slugs"]), json.dumps(result["font_claims"]), image_url,
            image_alt_text,
            result["word_count"], result["content_scope"], now,
        ),
    )
    conn.commit()
    return {
        **result,
        "id": article_id,
        "image_url": image_url,
        "image_alt_text": image_alt_text,
        "status": "pending_review",
    }


def queue_manual_article(conn, title: str, meta: str, font_slugs: list[str], body_html: str) -> str:
    title, meta, body_html = title.strip(), meta.strip(), body_html.strip()
    if not title or not meta or not body_html:
        raise ValueError("Title, meta description, and HTML body are required")
    if len(meta) > 160:
        raise ValueError("Meta description exceeds 160 characters")
    referenced = list(dict.fromkeys(slug.strip() for slug in font_slugs if slug.strip()))
    if len(referenced) < 2:
        raise ValueError("At least two font slugs are required")
    placeholders = ",".join("?" for _ in referenced)
    fonts = conn.execute(
        f"""SELECT f.slug, f.weights, f.variants, f.is_variable, COALESCE(t.seo_image_url, '') AS seo_image_url
            FROM font_registry f LEFT JOIN font_translations t ON t.slug=f.slug AND t.locale='en'
            WHERE f.status='active' AND f.slug IN ({placeholders})""", referenced,
    ).fetchall()
    fonts = [dict(row) for row in fonts]
    if len({row["slug"] for row in fonts}) != len(referenced):
        raise ValueError("One or more font slugs are missing or inactive")
    for slug in referenced:
        if f"/font/{slug}" not in body_html:
            raise ValueError(f"Body is missing an internal link to {slug}")
    if re.search(r"<\s*(script|iframe|object)\b", body_html, re.I):
        raise ValueError("Article contains unsafe HTML")
    _validate_html(body_html)
    word_count = len(_words(re.sub(r"<[^>]+>", " ", body_html)))
    if not 700 <= word_count <= 1400:
        raise ValueError(f"Article length is {word_count} words; expected 700-1400")
    integrity_report = enforce_keyword_integrity(conn, title, "en")
    base_slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:80]
    slug = base_slug
    suffix = 2
    while conn.execute("SELECT 1 FROM article_queue WHERE slug=?", (slug,)).fetchone():
        slug = f"{base_slug}-{suffix}"
        suffix += 1
    article_id = str(uuid.uuid4())
    font_claims = [
        {"slug": row["slug"], **_font_capabilities(row)} for row in fonts
    ]
    conn.execute(
        """INSERT INTO article_queue (
            id, source_topic, source_keyword_data, language, validity, validity_reasoning,
            title, slug, meta_description, target_keyword, secondary_keywords, body_markdown, body_html,
            referenced_font_slugs, font_claims, image_url, image_alt_text, word_count, status, created_at,
            content_scope
        ) VALUES (?, 'manual', ?, 'en', 'valid', 'Manually submitted and validated',
                  ?, ?, ?, ?, '[]', ?, ?, ?, ?, NULL, NULL, ?, 'awaiting_image', ?, ?)""",
        (article_id, json.dumps({"content_integrity": integrity_report}), title, slug, meta, title, body_html, body_html, json.dumps(referenced),
         json.dumps(font_claims), word_count, datetime.now(timezone.utc).isoformat(),
         "deep_dive" if word_count >= 1000 else "guide"),
    )
    conn.commit()
    return article_id


def publication_integrity_report(conn, article_id: str) -> dict:
    """Re-run deterministic conflicts immediately before approval or publication."""
    row = conn.execute(
        "SELECT id,target_keyword,language,source_keyword_data FROM article_queue WHERE id=?",
        (article_id,),
    ).fetchone()
    if not row:
        raise ValueError("Article not found")
    try:
        source_data = json.loads(row["source_keyword_data"] or "{}")
    except json.JSONDecodeError:
        source_data = {}
    return enforce_keyword_integrity(
        conn,
        row["target_keyword"],
        row["language"],
        intent_key=source_data.get("intent_key"),
        exclude_article_id=row["id"],
    )
