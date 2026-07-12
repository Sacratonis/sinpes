import json
from fastapi import APIRouter, Depends
from app.db.database import get_db_connection
from app.core.security import verify_build_secret
from app.repositories.font_repo import FontRepository

router = APIRouter(prefix="/snapshot")

PAGE_SIZE = 2000

def export_snapshot() -> str:
    """
    Paginated export that joins font_registry with localized font_translations.
    Returns a stringified JSON payload.
    """
    conn = get_db_connection()
    repo = FontRepository(conn)
    entries = []
    last_rowid = 0

    while True:
        batch = repo.get_snapshot_batch(last_rowid, PAGE_SIZE)
        if not batch:
            break

        for font in batch:
            entry = font.model_dump(exclude={'rowid', 'status', 'vault_status', 'file_hash', 'embedded_family_name'})
            
            # Ensure JSON arrays are correctly parsed back into Python lists
            entry['variants'] = json.loads(entry['variants'] or '[]')
            entry['weights'] = json.loads(entry['weights']) if entry['weights'] else None
            
            translations = repo.get_translations_for_slugs([font.slug])
            
            entry['translations'] = {
                t.locale: {
                    'description': t.description,
                    'seo_image_url': t.seo_image_url
                } for t in translations
            }
            entries.append(entry)

        last_rowid = batch[-1].rowid

    conn.close()
    
    # ensure_ascii=False keeps special localized characters intact
    # separators=(',', ':') minimizes the JSON payload size
    return json.dumps(entries, ensure_ascii=False, separators=(',', ':'))

def export_blog_snapshot() -> str:
    """
    Exports published articles grouped by slug for the frontend blog.ts contract.
    """
    conn = get_db_connection()
    try:
        from app.repositories.blog_repo import BlogRepository
        b_repo = BlogRepository(conn)
        rows = b_repo.get_published_articles()
        
        grouped = {}
        for row in rows:
            slug = row['slug']
            if not slug: continue
            
            lang = row['language']
            if slug not in grouped:
                grouped[slug] = {
                    'slug': slug,
                    'date': row['published_at'] or row['created_at'],
                    'title': {'en': '', 'es': '', 'pt': ''},
                    'excerpt': {'en': '', 'es': '', 'pt': ''},
                    'content': {'en': '', 'es': '', 'pt': ''},
                    'image_url': row['image_url'] or '',
                    'image_alt_text': row['image_alt_text'] or '',
                    'target_keyword': row['target_keyword'] or ''
                }
            
            if lang in grouped[slug]['title']:
                grouped[slug]['title'][lang] = row['title'] or ''
                grouped[slug]['excerpt'][lang] = row['meta_description'] or ''
                grouped[slug]['content'][lang] = row['body_markdown'] or ''
                
        return json.dumps(list(grouped.values()), ensure_ascii=False, separators=(',', ':'))
    finally:
        conn.close()

@router.get("/export")
def trigger_export(_ = Depends(verify_build_secret)):
    """
    Secured endpoint to manually trigger and view the snapshot output without firing a build.
    """
    snapshot_json = export_snapshot()
    # Parsing it back to dict just for the FastAPI JSONResponse to format it, 
    # though in the actual drip-feed service, the raw string is uploaded directly to R2.
    return json.loads(snapshot_json)
