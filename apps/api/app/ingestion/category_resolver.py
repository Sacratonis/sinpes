import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Callable

def get_category_slug(name: str) -> str:
    return name.strip().lower().replace(" ", "-")

def create_category(db_conn: sqlite3.Connection, name: str) -> str:
    from app.repositories.category_repo import CategoryRepository
    slug = get_category_slug(name)
    repo = CategoryRepository(db_conn)
    repo.create_category(slug, name.strip())
    db_conn.commit()
    return slug

def resolve_category(db_conn: sqlite3.Connection, name: str, flagged_as_new: bool, alert_callback: Callable[[str], None]) -> str:
    from app.repositories.category_repo import CategoryRepository
    slug = get_category_slug(name)
    repo = CategoryRepository(db_conn)

    declined = db_conn.execute(
        "SELECT value FROM meta WHERE key = ?",
        (f"declined_category:{slug}",),
    ).fetchone()
    if declined:
        raise ValueError(f"Category '{name}' was declined. Correct the JSON and upload again.")
    
    if repo.check_category_exists(slug):
        return slug  # known category, instant

    if flagged_as_new:
        return create_category(db_conn, name)  # explicitly flagged, instant

    existing_pending = repo.get_unresolved_pending_category_by_name(name)
    if existing_pending:
        return slug

    # Unflagged and unmatched: require an explicit administrator decision.
    expires_at = (datetime.now(timezone.utc) + timedelta(days=3650)).isoformat()
    repo.add_pending_category(name, expires_at)
    db_conn.commit()
    pending = repo.get_unresolved_pending_category_by_name(name)
    
    alert_callback(
        f"New category '{name}' needs approval. "
        f"Send /category_confirm {pending.id} or /category_decline {pending.id} in this bot chat."
    )
    return slug

def resolve_expired_pending_categories(db_conn: sqlite3.Connection):
    """Kept for scheduler compatibility. Categories now require manual approval."""
    return None
