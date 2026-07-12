from fastapi import APIRouter, Depends, HTTPException
import urllib.request
from app.db.database import get_db
from app.core.security import verify_build_secret
from app.core.config import config
import time

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

        # Set lock and trigger build
        m_repo.set_value('build_in_progress', 'true')
        m_repo.set_value('last_build_triggered_at', str(time.time()))
        conn.commit()

    from app.routers.snapshot import export_blog_snapshot
    from app.ingestion.storage_archive import upload_to_r2
    blog_json = export_blog_snapshot()
    upload_to_r2(
        data=blog_json.encode('utf-8'),
        key="build-artifacts/blog-registry.snapshot.json",
        content_type="application/json",
        cache_control="no-cache"
    )

    if config.CF_PAGES_DEPLOY_HOOK_URL:
        req = urllib.request.Request(config.CF_PAGES_DEPLOY_HOOK_URL, method="POST")
        urllib.request.urlopen(req)

    return {"status": "published_and_building"}
