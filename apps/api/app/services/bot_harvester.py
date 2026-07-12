import os
import logging
import asyncio
from telethon import TelegramClient, events
from app.core.config import config
from app.db.database import get_db_connection
from app.ingestion.channel_listener import queue_incoming_upload
from app.ingestion.bouncer import check_size_and_flag
from app.schemas.ingestion import FontIngestionPayload
from pydantic import ValidationError

logger = logging.getLogger("sinpes.bot")

API_ID = config.TELEGRAM_API_ID
API_HASH = config.TELEGRAM_API_HASH
BOT_TOKEN = config.oracle.telegram_bot_token

def start_bot():
    client = TelegramClient('sinpes_bot_session', int(API_ID), API_HASH)

    @client.on(events.NewMessage(incoming=True))
    async def handle_new_message(event):
        if event.chat_id != config.TELEGRAM_MAIN_CHANNEL_ID:
            return

        if not event.message.media:
            return

        logger.info(f"Received batched upload from curator: {event.sender_id}")
        download_dir = "/tmp/sinpes_uploads"
        os.makedirs(download_dir, exist_ok=True)

        try:
            # 1. Download the primary media (e.g., zip or font file)
            file_path = await event.message.download_media(file=download_dir)
            
            if not file_path:
                await event.reply("Failed to download media.")
                return

            # Read raw bytes for bouncer
            with open(file_path, "rb") as f:
                raw_bytes = f.read()

            # 2. Bouncer check - alert back to Telegram if it's too large
            async def alert_callback(msg: str):
                await event.reply(f"⚠️ {msg}")

            check_size_and_flag(file_path, raw_bytes, lambda x: asyncio.create_task(alert_callback(x)))

            # 3. Parse the JSON caption into the same contract consumed by the queue worker.
            try:
                payload = FontIngestionPayload.from_telegram_caption(
                    event.message.text or "",
                    font_files=[file_path],
                )
            except (ValidationError, ValueError) as exc:
                await event.reply(
                    "❌ Upload rejected: invalid metadata caption.\n\n"
                    f"{exc}\n\nAttach the font again with a valid v1 JSON caption."
                )
                return

            # 4. Queue the upload in the SQLite DB
            with get_db_connection() as conn:
                queue_incoming_upload(
                    db_conn=conn,
                    payload=payload,
                )

            await event.reply("✅ Upload successfully received and queued for processing.")

        except Exception as e:
            logger.error(f"Error processing upload: {e}")
            await event.reply("❌ An error occurred while queuing the upload.")

    logger.info("Starting SINPES Bot Harvester...")
    client.start(bot_token=BOT_TOKEN)
    # This runs the event loop forever
    client.run_until_disconnected()

if __name__ == '__main__':
    # Setup basic logging when run directly
    logging.basicConfig(level=logging.INFO)
    start_bot()
