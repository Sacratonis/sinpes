from fastapi import APIRouter, Depends, Header, Query, Request
from app.core.security import verify_build_secret
from app.db.database import get_db_connection
from app.services.deployment_manager import confirm_deployment_success

router = APIRouter()

@router.post("/build-success")
async def confirm_build_success(
    request: Request,
    deployment_id: str | None = Query(default=None),
    x_deployment_id: str | None = Header(default=None),
    _ = Depends(verify_build_secret),
):
    body_deployment_id = None
    if request.headers.get("content-type", "").startswith("application/json"):
        try:
            body = await request.json()
            body_deployment_id = body.get("deployment_id") if isinstance(body, dict) else None
        except Exception:
            body_deployment_id = None
    conn = get_db_connection()
    try:
        return confirm_deployment_success(
            conn,
            deployment_id=deployment_id or x_deployment_id or body_deployment_id,
        )
    finally:
        conn.close()
