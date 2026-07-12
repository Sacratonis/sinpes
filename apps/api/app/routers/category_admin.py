from fastapi import APIRouter, Depends
from app.db.database import get_db_connection
from app.ingestion.category_resolver import get_category_slug
from app.core.security import verify_build_secret

router = APIRouter(prefix="/category")

@router.delete("/{name}", dependencies=[Depends(verify_build_secret)])
def delete_category(name: str):
    conn = get_db_connection()
    from app.repositories.category_repo import CategoryRepository
    repo = CategoryRepository(conn)
    slug = get_category_slug(name)
    
    fonts_using_it = repo.get_fonts_using_category(slug)

    if fonts_using_it:
        font_list = ", ".join(fonts_using_it)
        conn.close()
        return {
            "status": "blocked",
            "message": f"Cannot delete '{name}' — still used by: {font_list}. Reassign these first."
        }

    repo.delete_category(slug)
    conn.commit()
    conn.close()
    return {"status": "deleted"}

@router.put("/{old_name}", dependencies=[Depends(verify_build_secret)])
def rename_category(old_name: str, new_name: str):
    conn = get_db_connection()
    from app.repositories.category_repo import CategoryRepository
    repo = CategoryRepository(conn)
    slug = get_category_slug(old_name)
    
    # Updates the visible label only; slug remains unchanged
    repo.update_category_name(slug, new_name.strip())
    conn.commit()
    conn.close()
    return {"status": "renamed"}
