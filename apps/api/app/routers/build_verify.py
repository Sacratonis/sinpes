from fastapi import APIRouter, Depends
from app.core.security import verify_build_secret
from app.db.database import get_db_connection
from app.services.deployment_manager import confirm_deployment_success

router = APIRouter()

@router.post("/build-success")
def confirm_build_success(_ = Depends(verify_build_secret)):
    conn = get_db_connection()
    try:
        return confirm_deployment_success(conn)
    finally:
        conn.close()
