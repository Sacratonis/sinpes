import time
from fastapi import APIRouter, Depends, Request
from app.core.security import verify_build_secret, verify_webhook_ip
from app.db.database import get_db_connection

router = APIRouter()
COOLDOWN_SECONDS = 90

@router.post("/sync")
def trigger_manual_sync(
    request: Request,
    _ = Depends(verify_build_secret),
    client_ip: str = Depends(verify_webhook_ip)
):
    conn = get_db_connection()
    from app.repositories.meta_repo import MetaRepository
    repo = MetaRepository(conn)
    last_val = repo.get_value('last_build_triggered_at')
    
    if last_val and (time.time() - float(last_val) < COOLDOWN_SECONDS):
        conn.close()
        return {"status": "ignored", "reason": "cooldown active"}

    repo.set_value('last_build_triggered_at', str(time.time()))
    conn.commit()
    conn.close()
    
    # In production, this fires a Telegram alert to the curator
    return {"status": "sync_queued"}