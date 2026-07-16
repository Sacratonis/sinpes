from fastapi import APIRouter, Depends, HTTPException
from app.core.security import verify_build_secret

router = APIRouter(prefix="/blog")

@router.post("/{slug}/publish")
def publish_blog_post(slug: str, _ = Depends(verify_build_secret)):
    raise HTTPException(
        status_code=410,
        detail=(
            "Legacy direct blog publishing is disabled. Approve the article through the "
            "Writer bot, then use /publish_articles so full validation runs before deployment."
        ),
    )
