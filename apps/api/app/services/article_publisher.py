"""Publish validated editorial articles through one guarded website deployment."""

import json

from app.db.database import get_db
from app.ingestion.storage_archive import upload_to_r2
from app.routers.snapshot import export_blog_snapshot, export_snapshot
from app.services.content_integrity import ContentIntegrityError
from app.services.deployment_manager import (
    PENDING_ARTICLES_KEY,
    deployment_manifest,
    new_deployment_id,
    snapshot_hash,
    trigger_deployment,
)
from app.repositories.meta_repo import MetaRepository
from app.services.indexnow import PENDING_KEY, localized_urls
from app.services.writer_pipeline import validate_stored_article


def _upload_blog_snapshot(snapshot: str) -> None:
    upload_to_r2(
        data=snapshot.encode("utf-8"),
        key="build-artifacts/blog-registry.snapshot.json",
        content_type="application/json",
        cache_control="no-cache",
    )


def _read_json_list(value: str | None) -> list[str]:
    try:
        parsed = json.loads(value or "[]")
    except (TypeError, json.JSONDecodeError):
        return []
    return [str(item) for item in parsed] if isinstance(parsed, list) else []


def _restore_approved_articles(
    article_ids: list[str],
    pending_indexnow_urls: list[str],
    pending_article_ids: list[str],
    *,
    restore_snapshot: bool,
) -> None:
    """Restore database and R2 snapshot when no matching deployment was triggered."""
    if not article_ids:
        return
    placeholders = ",".join("?" for _ in article_ids)
    with get_db() as conn:
        conn.execute(
            f"""UPDATE article_queue SET status='approved', published_at=NULL
                WHERE id IN ({placeholders}) AND status='publishing'""",
            article_ids,
        )
        meta = MetaRepository(conn)
        # Leave a newer publisher's lock untouched.  If this batch still owns
        # the key (or the trigger never wrote it), restore the exact prior IDs.
        current_pending = _read_json_list(meta.get_value(PENDING_ARTICLES_KEY))
        if current_pending == article_ids or not current_pending:
            meta.set_value(PENDING_ARTICLES_KEY, json.dumps(pending_article_ids))
        meta.set_value(PENDING_KEY, json.dumps(pending_indexnow_urls))
        conn.commit()
    if restore_snapshot:
        _upload_blog_snapshot(export_blog_snapshot())


def publish_approved_articles(
    *,
    limit: int = 9,
    automatic: bool = False,
    source: str = "writer_batch",
    only_slug: str | None = None,
) -> dict:
    """Validate and publish multiple approved articles with one snapshot and deployment."""
    if not 1 <= limit <= 20:
        raise ValueError("Article batch limit must be between 1 and 20")

    rejected: list[dict] = []
    selected: list[dict] = []
    with get_db() as conn:
        # Serialize batch selection so concurrent commands cannot claim the same rows.
        conn.execute("BEGIN IMMEDIATE")
        build = conn.execute("SELECT value FROM meta WHERE key='build_in_progress'").fetchone()
        if build and build["value"] == "true":
            return {
                "published_count": 0,
                "pending_confirmation_count": 0,
                "reason": "website build is already running",
                "rejected": [],
                "slugs": [],
                "indexnow_url_count": 0,
            }
        if only_slug:
            rows = conn.execute(
                """SELECT id,slug,title,language FROM article_queue
                   WHERE status='approved' AND slug=? ORDER BY created_at LIMIT 1""",
                (only_slug,),
            ).fetchall()
        else:
            rows = conn.execute(
                """SELECT id,slug,title,language FROM article_queue
                   WHERE status='approved' ORDER BY created_at LIMIT ?""",
                (limit,),
            ).fetchall()
        if not rows:
            return {
                "published_count": 0,
                "pending_confirmation_count": 0,
                "reason": "no approved articles",
                "rejected": [],
                "slugs": [],
                "indexnow_url_count": 0,
            }

        for row in rows:
            row = dict(row)
            try:
                validate_stored_article(conn, row["id"], persist=True)
                selected.append(row)
            except (ContentIntegrityError, ValueError) as exc:
                note = f"Publication validation: {exc}"
                conn.execute(
                    "UPDATE article_queue SET status='pending_review', rejection_note=? WHERE id=?",
                    (note, row["id"]),
                )
                rejected.append({"id": row["id"], "slug": row["slug"], "reason": str(exc)})

        if not selected:
            conn.commit()
            return {
                "published_count": 0,
                "pending_confirmation_count": 0,
                "reason": "all approved articles failed publication validation",
                "rejected": rejected,
                "slugs": [],
                "indexnow_url_count": 0,
            }

        # Keep the article out of the published set until Cloudflare confirms the build.
        conn.executemany(
            "UPDATE article_queue SET status='publishing', published_at=NULL WHERE id=?",
            [(row["id"],) for row in selected],
        )
        conn.commit()

    article_ids = [row["id"] for row in selected]
    changed_urls = localized_urls("/") + localized_urls("/blog/")
    for row in selected:
        # Only notify the locale actually stored for this article.
        article_locale = row.get("language") or "en"
        changed_urls.extend(
            localized_urls(f"/blog/{row['slug']}/", locales=(article_locale,))
        )
    changed_urls = list(dict.fromkeys(changed_urls))

    snapshot_uploaded = False
    # Capture rollback state before any export or R2 upload can fail.
    with get_db() as conn:
        meta = MetaRepository(conn)
        pending_indexnow_before = _read_json_list(meta.get_value(PENDING_KEY))
        pending_article_ids_before = _read_json_list(meta.get_value(PENDING_ARTICLES_KEY))
    try:
        blog_snapshot = export_blog_snapshot()
        font_snapshot = export_snapshot()
        _upload_blog_snapshot(blog_snapshot)
        snapshot_uploaded = True
        artifact_hash = snapshot_hash(font_snapshot, blog_snapshot)
        deployment_id = new_deployment_id()
        upload_to_r2(
            data=deployment_manifest(
                deployment_id=deployment_id,
                artifact_hash=artifact_hash,
                source=source,
            ).encode("utf-8"),
            key="build-artifacts/deployment.json",
            content_type="application/json",
            cache_control="no-cache",
        )
        with get_db() as conn:
            decision = trigger_deployment(
                conn,
                artifact_hash=artifact_hash,
                source=source,
                indexnow_urls=changed_urls,
                pending_article_ids=article_ids,
                deployment_id=deployment_id,
                automatic=automatic,
            )
        if not decision.triggered:
            _restore_approved_articles(
                article_ids,
                pending_indexnow_before,
                pending_article_ids_before,
                restore_snapshot=True,
            )
            return {
                "published_count": 0,
                "pending_confirmation_count": 0,
                "reason": decision.reason,
                "rejected": rejected,
                "slugs": [],
                "indexnow_url_count": 0,
            }
    except Exception:
        _restore_approved_articles(
            article_ids,
            pending_indexnow_before,
            pending_article_ids_before,
            restore_snapshot=snapshot_uploaded,
        )
        raise

    return {
        "published_count": 0,
        "pending_confirmation_count": len(selected),
        "deployed": True,
        "reason": decision.reason,
        "rejected": rejected,
        "slugs": [row["slug"] for row in selected],
        "titles": [row["title"] for row in selected],
        "ids": article_ids,
        "indexnow_url_count": len(changed_urls),
    }


def publish_next_approved_article() -> dict:
    """Backward-compatible scheduled publisher: one article, one automatic deployment."""
    result = publish_approved_articles(
        limit=1,
        automatic=True,
        source="scheduled_article",
    )
    if not result.get("published_count") and not result.get("pending_confirmation_count"):
        return {
            "published": False,
            "reason": result["reason"],
            "rejected": result["rejected"],
        }
    return {
        "published": True,
        "deployed": result.get("deployed", False),
        "pending_confirmation": bool(result.get("pending_confirmation_count")),
        "reason": result["reason"],
        "id": result["ids"][0],
        "slug": result["slugs"][0],
        "title": result["titles"][0],
    }
