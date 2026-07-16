"""Read-only SEO audits built on the shared content-integrity rules."""

import re

from app.services.content_integrity import analyze_keyword_conflicts


def audit_candidate(conn, target_keyword: str, language: str = "en", intent_key: str | None = None) -> dict:
    """Evaluate a proposed page without changing any database state."""
    return analyze_keyword_conflicts(conn, target_keyword, language, intent_key=intent_key)


def audit_article_cannibalization(conn) -> dict:
    """Inspect existing editorial rows and return each conflict pair once."""
    rows = conn.execute(
        """SELECT id,title,target_keyword,language,status
           FROM article_queue
           WHERE status IN ('awaiting_image','pending_review','edited','approved','published')
             AND target_keyword IS NOT NULL
           ORDER BY created_at"""
    ).fetchall()
    hard_pairs = {}
    advisory_pairs = {}
    for row in rows:
        report = analyze_keyword_conflicts(
            conn, row["target_keyword"], row["language"], exclude_article_id=row["id"],
        )
        for conflict in report["hard_conflicts"]:
            pair = tuple(sorted((str(row["id"]), conflict["article_id"])))
            hard_pairs[pair] = {
                "left_id": pair[0], "right_id": pair[1], "reason": conflict["reason"],
            }
        for conflict in report["advisories"]:
            pair = tuple(sorted((str(row["id"]), conflict["article_id"])))
            advisory_pairs[pair] = {
                "left_id": pair[0], "right_id": pair[1], "reason": conflict["reason"],
                "score": conflict["score"],
            }
    return {
        "pages_checked": len(rows),
        "hard_conflicts": list(hard_pairs.values()),
        "advisories": list(advisory_pairs.values()),
    }


def audit_font_images(conn) -> dict:
    """Report missing, insecure, and cross-family duplicate hero-image URLs."""
    active_fonts = conn.execute(
        "SELECT slug FROM font_registry WHERE status='active' ORDER BY slug"
    ).fetchall()
    slugs = [row["slug"] for row in active_fonts]
    rows = conn.execute(
        """SELECT f.slug,t.locale,t.seo_image_url
           FROM font_registry f
           LEFT JOIN font_translations t ON t.slug=f.slug
           WHERE f.status='active'
           ORDER BY f.slug,t.locale"""
    ).fetchall()
    translations = {slug: {} for slug in slugs}
    for row in rows:
        if row["locale"]:
            translations[row["slug"]][row["locale"]] = str(row["seo_image_url"] or "").strip()
    missing = []
    insecure = []
    url_slugs: dict[str, set[str]] = {}
    for slug in slugs:
        for locale in ("en", "es", "pt"):
            url = translations[slug].get(locale, "")
            if not url:
                missing.append({"slug": slug, "locale": locale})
                continue
            if not url.startswith("https://"):
                insecure.append({"slug": slug, "locale": locale, "url": url})
            url_slugs.setdefault(url, set()).add(slug)
    duplicates = [
        {"url": url, "slugs": sorted(families)}
        for url, families in url_slugs.items() if len(families) > 1
    ]
    return {
        "active_fonts": len(slugs),
        "expected_localized_images": len(slugs) * 3,
        "missing": missing,
        "insecure": insecure,
        "cross_family_duplicates": duplicates,
    }


def audit_article_font_links(conn) -> dict:
    """Find article links that point to missing or non-public font pages."""
    active = {
        row["slug"] for row in conn.execute(
            "SELECT slug FROM font_registry WHERE status='active'"
        ).fetchall()
    }
    rows = conn.execute(
        """SELECT id,title,status,COALESCE(body_html,body_markdown,'') AS body
           FROM article_queue
           WHERE status IN ('awaiting_image','pending_review','edited','approved','published')"""
    ).fetchall()
    broken = []
    articles_with_links = 0
    for row in rows:
        slugs = sorted(set(re.findall(r'href=["\']/font/([a-z0-9-]+)/?', row["body"], re.I)))
        if slugs:
            articles_with_links += 1
        missing = [slug for slug in slugs if slug not in active]
        if missing:
            broken.append({
                "id": row["id"], "title": row["title"], "status": row["status"],
                "missing_font_slugs": missing,
            })
    return {
        "articles_checked": len(rows),
        "articles_with_font_links": articles_with_links,
        "broken": broken,
    }


def build_read_only_report(conn) -> dict:
    return {
        "content": audit_article_cannibalization(conn),
        "images": audit_font_images(conn),
        "links": audit_article_font_links(conn),
    }
