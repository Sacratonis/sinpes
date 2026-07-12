import sqlite3
import logging
from contextlib import contextmanager
from app.core.config import config

logger = logging.getLogger(__name__)

def get_db_connection():
    """Returns a connected sqlite3 instance with dict-row factories and required pragmas."""
    conn = sqlite3.connect(config.DATABASE_PATH, timeout=5.0)
    conn.row_factory = sqlite3.Row
    
    # Applied on every connection at startup as per architecture §11.6
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    conn.execute("PRAGMA busy_timeout=5000;")
    conn.execute("PRAGMA foreign_keys=ON;")
    
    return conn

@contextmanager
def get_db():
    """Context manager wrapper to guarantee connection closure and prevent leaks."""
    conn = get_db_connection()
    try:
        yield conn
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

def init_db():
    """Initializes the database schema if it doesn't exist."""
    from app.db.models import create_tables
    conn = get_db_connection()
    try:
        create_tables(conn)
        conn.commit()
    finally:
        conn.close()

def run_migrations():
    """Automatically applies Alembic migrations on app startup."""
    logger.info("Running Alembic database migrations...")
    import alembic.config
    import os
    
    # Path to alembic.ini relative to this file
    alembic_ini_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 
        "alembic.ini"
    )
    
    alembic_args = [
        "-c", alembic_ini_path,
        "upgrade", "head"
    ]
    try:
        alembic.config.main(argv=alembic_args)
        logger.info("Migrations complete.")
    except Exception as e:
        logger.error(f"Failed to run migrations: {e}")
        raise
