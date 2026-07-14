import requests

from app.routers.snapshot import export_blog_snapshot, export_snapshot
from app.ingestion.storage_archive import upload_to_r2
from app.core.config import config
from app.services.deployment_manager import (
    get_deployment_status,
    snapshot_hash,
    trigger_deployment,
)

def alert_curator(msg: str):
    """Sends a critical alert to the main Telegram channel."""
    bot_token = config.oracle.telegram_bot_token
    if not bot_token or not config.TELEGRAM_MAIN_CHANNEL_ID:
        print(f"TELEGRAM ALERT (Not Configured): {msg}")
        return
        
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {
        "chat_id": config.TELEGRAM_MAIN_CHANNEL_ID,
        "text": f"⚠️ **SINPES SYSTEM ALERT**\n{msg}",
        "parse_mode": "Markdown"
    }
    try:
        requests.post(url, json=payload, timeout=5)
    except Exception as e:
        print(f"Failed to send Telegram alert: {e}\nOriginal msg: {msg}")

def get_publish_status(conn):
    return get_deployment_status(conn)


def run_daily_batch(force: bool = False, automatic: bool = True):
    from app.db.database import get_db
    try:
        with get_db() as conn:
            from app.repositories.meta_repo import MetaRepository
            from app.repositories.font_repo import FontRepository
            m_repo = MetaRepository(conn)
            f_repo = FontRepository(conn)
            
            # Activate up to 48 fonts in the exact order they were queued
            f_repo.activate_queued_fonts(48)
            conn.commit()

            # Generate and upload the fresh snapshot
            snapshot_json = export_snapshot()
            upload_to_r2(
                data=snapshot_json.encode('utf-8'),
                key="build-artifacts/font-registry.snapshot.json",
                content_type="application/json",
                cache_control="no-cache"
            )
            blog_snapshot_json = export_blog_snapshot()
            upload_to_r2(
                data=blog_snapshot_json.encode('utf-8'),
                key="build-artifacts/blog-registry.snapshot.json",
                content_type="application/json",
                cache_control="no-cache"
            )

            decision = trigger_deployment(
                conn,
                artifact_hash=snapshot_hash(snapshot_json, blog_snapshot_json),
                source="daily_font_batch" if automatic else "telegram_publish",
                force=force,
                automatic=automatic,
            )
            return {
                "triggered": decision.triggered,
                "reason": decision.reason,
                "snapshot_hash": decision.artifact_hash,
            }

    except Exception as e:
        try:
            with get_db() as conn:
                from app.repositories.meta_repo import MetaRepository
                MetaRepository(conn).set_value('last_build_error', str(e))
                MetaRepository(conn).set_value('build_in_progress', 'false')
                conn.commit()
        except Exception:
            pass
        alert_curator(f"Daily batch failed: {e}. No build triggered.")
        raise
