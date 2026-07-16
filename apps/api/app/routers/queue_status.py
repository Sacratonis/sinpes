from fastapi import APIRouter, Depends
from datetime import datetime, timezone
from app.db.database import get_db
from app.core.security import verify_build_secret

router = APIRouter(tags=["Monitoring"])

@router.get("/queue/status", dependencies=[Depends(verify_build_secret)])
def queue_status():
    """
    Deep observability into the ingestion pipeline. 
    Protected by x-build-secret header to prevent information disclosure.
    """
    with get_db() as conn:
        from app.repositories.queue_repo import QueueRepository
        from app.repositories.meta_repo import MetaRepository
        
        q_repo = QueueRepository(conn)
        m_repo = MetaRepository(conn)
        
        overview = q_repo.get_pipeline_overview()
        pending = overview.pending_ingestion
        failed = overview.failed_ingestion
        
        # 1. Last Scheduler Tick
        last_run_val = m_repo.get_value('last_queue_release_at')
        last_run = "Never"
        if last_run_val:
            last_run = datetime.fromtimestamp(float(last_run_val), tz=timezone.utc).isoformat()

        # 2. 🌟 NEW: Oldest Pending Item Age (Staleness Check) 🌟
        oldest = q_repo.get_oldest_pending_item()
        
        oldest_age_minutes = None
        if oldest and oldest.received_at:
            try:
                # Parse the ISO timestamp from the DB
                received_dt = datetime.fromisoformat(oldest.received_at)
                # Ensure timezone awareness for accurate math
                if received_dt.tzinfo is None:
                    received_dt = received_dt.replace(tzinfo=timezone.utc)
                    
                oldest_age_minutes = round((datetime.now(timezone.utc) - received_dt).total_seconds() / 60, 2)
            except ValueError:
                oldest_age_minutes = "Invalid Date Format"

        return {
            "queue_health": "healthy" if pending < 100 else "backlogged",
            "pending_items": pending,
            "dead_letter_items": failed,
            "live_fonts": overview.live_fonts,
            "ready_to_publish": overview.ready_to_publish,
            "oldest_pending_age_minutes": oldest_age_minutes,
            "last_scheduler_tick": last_run
        }
