"""
Thread-safe, synchronous Telegram notification helper for use in
APScheduler background thread jobs (no event loop, no Telethon event object).
"""
import logging
import requests
from app.core.config import config

logger = logging.getLogger(__name__)


def send_telegram_alert(message: str) -> None:
    """
    Posts a message to TELEGRAM_MAIN_CHANNEL_ID via the Bot API sendMessage endpoint.

    Uses the Oracle bot token since the Oracle bot is the one listening in the
    main ingestion channel. Synchronous requests.post — safe to call from
    APScheduler worker threads without any asyncio involvement.

    Failures are logged but never raise — alerts are informational,
    they must not interrupt the pipeline that triggered them.
    """
    token = config.oracle.telegram_bot_token
    try:
        admins_response = requests.get(
            f"https://api.telegram.org/bot{token}/getChatAdministrators",
            params={"chat_id": config.TELEGRAM_MAIN_CHANNEL_ID},
            timeout=10,
        )
        admins_response.raise_for_status()
        admins = admins_response.json().get("result", [])
        delivered = 0
        for entry in admins:
            user = entry.get("user", {})
            if user.get("is_bot"):
                continue
            response = requests.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                json={"chat_id": user["id"], "text": message},
                timeout=10,
            )
            if response.ok:
                delivered += 1
        if delivered == 0:
            logger.warning("TELEGRAM NOTIFY: no channel administrator could receive a private alert")
    except Exception as e:
        logger.error(f"TELEGRAM NOTIFY: Failed to send alert — {e}. Original message: {message}")
