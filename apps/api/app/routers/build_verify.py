import time
from fastapi import APIRouter, Depends
from app.core.security import verify_build_secret
from app.db.database import get_db_connection

router = APIRouter()

@router.post("/build-success")
def confirm_build_success(_ = Depends(verify_build_secret)):
    conn = get_db_connection()
    from app.repositories.meta_repo import MetaRepository
    repo = MetaRepository(conn)
    repo.set_value('last_successful_build_at', str(time.time()))
    repo.set_value('build_in_progress', 'false')
    conn.commit()
    conn.close()
    return {"status": "ok"}
