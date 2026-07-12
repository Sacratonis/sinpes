from fastapi import APIRouter, Depends
from app.db.database import get_db_connection
from app.core.security import verify_build_secret

router = APIRouter(prefix="/font")

@router.delete("/{slug}/remove", dependencies=[Depends(verify_build_secret)])
def remove_font(slug: str, confirm: bool = False):
    if not confirm:
        return {"status": "pending", "message": "Requires confirmation parameter"}
        
    conn = get_db_connection()
    from app.repositories.font_repo import FontRepository
    repo = FontRepository(conn)
    # Soft delete: sets status away from 'active' so it drops from the snapshot
    repo.soft_delete_font(slug)
    conn.commit()
    conn.close()
    
    # R2 files are retained
    return {"status": "soft_deleted", "message": f"{slug} removed from live site"}
