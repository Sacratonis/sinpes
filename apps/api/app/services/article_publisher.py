"""Publish one approved editorial article on each scheduled slot."""

from datetime import datetime, timezone

from app.db.database import get_db
from app.ingestion.storage_archive import upload_to_r2
from app.routers.snapshot import export_blog_snapshot, export_snapshot
from app.services.content_integrity import ContentIntegrityError
from app.services.deployment_manager import snapshot_hash, trigger_deployment
from app.services.writer_pipeline import publication_integrity_report


def publish_next_approved_article() -> dict:
    with get_db() as conn:
        build = conn.execute("SELECT value FROM meta WHERE key='build_in_progress'").fetchone()
        if build and build["value"] == "true":
            return {"published": False, "reason": "website build is already running"}
        row = conn.execute(
            "SELECT id,slug,title FROM article_queue WHERE status='approved' ORDER BY created_at LIMIT 1"
        ).fetchone()
        if not row:
            return {"published": False, "reason": "no approved articles"}
        try:
            publication_integrity_report(conn, row["id"])
        except ContentIntegrityError as exc:
            conn.execute(
                "UPDATE article_queue SET status='pending_review', rejection_note=? WHERE id=?",
                (f"Publication integrity check: {exc}", row["id"]),
            )
            conn.commit()
            return {"published": False, "reason": str(exc), "id": row["id"]}
        published_at = datetime.now(timezone.utc).isoformat()
        conn.execute(
            "UPDATE article_queue SET status='published', published_at=? WHERE id=?",
            (published_at, row["id"]),
        )
        conn.commit()

    try:
        snapshot = export_blog_snapshot()
        font_snapshot = export_snapshot()
        upload_to_r2(
            data=snapshot.encode("utf-8"),
            key="build-artifacts/blog-registry.snapshot.json",
            content_type="application/json",
            cache_control="no-cache",
        )
        with get_db() as conn:
            decision = trigger_deployment(
                conn,
                artifact_hash=snapshot_hash(font_snapshot, snapshot),
                source="scheduled_article",
                automatic=True,
            )
        return {
            "published": True,
            "deployed": decision.triggered,
            "reason": decision.reason,
            "id": row["id"],
            "slug": row["slug"],
            "title": row["title"],
        }
    except Exception:
        with get_db() as conn:
            conn.execute("UPDATE article_queue SET status='approved', published_at=NULL WHERE id=?", (row["id"],))
            conn.commit()
        raise
