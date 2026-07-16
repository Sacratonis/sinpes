from fastapi import APIRouter, Depends, HTTPException
from app.db.database import get_db
from app.core.security import verify_build_secret
from app.services.deployment_manager import snapshot_hash, trigger_deployment
from app.services.indexnow import localized_urls

router = APIRouter(prefix="/blog")

@router.post("/{slug}/publish")
def publish_blog_post(slug: str, _ = Depends(verify_build_secret)):
    from app.repositories.blog_repo import BlogRepository
    from app.repositories.meta_repo import MetaRepository

    with get_db() as conn:
        b_repo = BlogRepository(conn)
        m_repo = MetaRepository(conn)
        
        # Check if post exists
        if not b_repo.check_post_exists(slug):
            raise HTTPException(status_code=404, detail="Blog post not found")

        # Update status
        b_repo.publish_post(slug)
        
        # Check lock
        in_progress = m_repo.get_value('build_in_progress')
        if in_progress == 'true':
            conn.commit()
            return {"status": "published_locally", "message": "Saved, but a build is currently running. Deploy will happen in next batch."}

        conn.commit()

    from app.routers.snapshot import export_blog_snapshot, export_snapshot
    from app.ingestion.storage_archive import upload_to_r2
    blog_json = export_blog_snapshot()
    font_json = export_snapshot()
    upload_to_r2(
        data=blog_json.encode('utf-8'),
        key="build-artifacts/blog-registry.snapshot.json",
        content_type="application/json",
        cache_control="no-cache"
    )

    with get_db() as conn:
        decision = trigger_deployment(
            conn,
            artifact_hash=snapshot_hash(font_json, blog_json),
            source="blog_admin",
            indexnow_urls=(
                localized_urls("/")
                + localized_urls("/blog/")
                + localized_urls(f"/blog/{slug}/")
            ),
            automatic=False,
        )

    return {
        "status": "published_and_building" if decision.triggered else "published_locally",
        "reason": decision.reason,
    }
