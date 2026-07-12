import time
import urllib.request
import requests

from app.routers.snapshot import export_blog_snapshot, export_snapshot
from app.ingestion.storage_archive import upload_to_r2
from app.core.config import config

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
    from app.repositories.meta_repo import MetaRepository
    meta = MetaRepository(conn)
    return {
        "in_progress": meta.get_value("build_in_progress") == "true",
        "triggered_at": meta.get_value("last_build_triggered_at"),
        "successful_at": meta.get_value("last_successful_build_at"),
        "last_error": meta.get_value("last_build_error"),
    }


def run_daily_batch(force: bool = False):
    from app.db.database import get_db
    try:
        with get_db() as conn:
            from app.repositories.meta_repo import MetaRepository
            from app.repositories.font_repo import FontRepository
            m_repo = MetaRepository(conn)
            f_repo = FontRepository(conn)
            
            last_s_val_str = m_repo.get_value('last_successful_build_at')
            last_t_val_str = m_repo.get_value('last_build_triggered_at')
            
            last_s_val = float(last_s_val_str) if last_s_val_str else 0.0
            last_t_val = float(last_t_val_str) if last_t_val_str else 0.0
            
            # Guard: don't activate a new batch if the last one never confirmed success
            build_is_recent = last_t_val > 0 and (time.time() - last_t_val) < 21600
            if not force and build_is_recent and (last_s_val == 0.0 or last_s_val < last_t_val):
                alert_curator(
                    "BATCH HALTED: last triggered build has not reported success. "
                    "Check Cloudflare Pages before the next batch activates."
                )
                return {"triggered": False, "reason": "previous build is still waiting"}

            if force:
                m_repo.set_value('build_in_progress', 'false')
                m_repo.set_value('last_build_error', '')

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

            # Trigger the Cloudflare build after the snapshot is safely uploaded.
            if config.CF_PAGES_DEPLOY_HOOK_URL:
                triggered_at = time.time()
                m_repo.set_value('last_build_triggered_at', str(triggered_at))
                m_repo.set_value('build_in_progress', 'true')
                conn.commit()
                req = urllib.request.Request(config.CF_PAGES_DEPLOY_HOOK_URL, method="POST")
                urllib.request.urlopen(req, timeout=15)
            conn.commit()
            return {"triggered": bool(config.CF_PAGES_DEPLOY_HOOK_URL)}

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
