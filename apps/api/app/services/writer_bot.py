import os
import logging
import uuid
import datetime
from telethon import TelegramClient, events, Button
from app.core.config import config
from app.db.database import get_db_connection

logger = logging.getLogger("sinpes.writer_bot")

API_ID = getattr(config, 'TELEGRAM_API_ID', os.getenv("TELEGRAM_API_ID", "0"))
API_HASH = getattr(config, 'TELEGRAM_API_HASH', os.getenv("TELEGRAM_API_HASH", ""))
BOT_TOKEN = getattr(config, 'TELEGRAM_WRITER_BOT_TOKEN', os.getenv("TELEGRAM_WRITER_BOT_TOKEN", ""))
CHANNEL_ID = getattr(config, 'TELEGRAM_WRITER_REVIEW_CHANNEL_ID', os.getenv("TELEGRAM_WRITER_REVIEW_CHANNEL_ID", ""))

def get_pending_articles(conn):
    cursor = conn.cursor()
    cursor.execute("SELECT id, title FROM article_queue WHERE status = 'pending_review'")
    return cursor.fetchall()

def update_article_status(conn, article_id, status, note=None):
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE article_queue SET status = ?, rejection_note = ? WHERE id = ?",
        (status, note, article_id)
    )
    conn.commit()

def start_bot():
    if not API_ID or API_ID == "0" or not API_HASH or not BOT_TOKEN:
        logger.warning("Telegram Writer Bot credentials not configured. Bot will not start.")
        return

    client = TelegramClient('sinpes_writer_bot_session', int(API_ID), API_HASH)

    @client.on(events.NewMessage(pattern='/pending'))
    async def cmd_pending(event):
        with get_db_connection() as conn:
            pending = get_pending_articles(conn)
            
        if not pending:
            await event.reply("No pending articles for review.")
            return
            
        msg = "📝 **Pending Articles:**\n\n"
        for row in pending:
            msg += f"• `{row[0]}` - {row[1] or 'Untitled'}\n"
        
        msg += "\nUse `/review {id}` to review an article."
        await event.reply(msg)

    @client.on(events.NewMessage(pattern=r'/review\s+(.+)'))
    async def cmd_review(event):
        article_id = event.pattern_match.group(1).strip()
        
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT title, meta_description, validity_reasoning, body_markdown, image_url FROM article_queue WHERE id = ?", (article_id,))
            row = cursor.fetchone()
            
        if not row:
            await event.reply(f"Article with ID `{article_id}` not found.")
            return
            
        title, meta, reasoning, body, image_url = row
        
        # Truncate body for preview
        body_preview = body[:300] + "..." if body and len(body) > 300 else body
        
        msg = f"**Title:** {title}\n"
        msg += f"**Meta:** {meta}\n"
        msg += f"**Reasoning:** {reasoning}\n\n"
        msg += f"**Preview:**\n{body_preview}\n\n"
        msg += f"**Image:** {image_url or 'None yet'}"
        
        buttons = [
            [
                Button.inline("✅ Approve", data=f"approve_{article_id}"),
                Button.inline("✏️ Edit", data=f"edit_{article_id}"),
                Button.inline("❌ Reject", data=f"reject_{article_id}")
            ]
        ]
        
        await event.reply(msg, buttons=buttons)

    @client.on(events.CallbackQuery(pattern=b'approve_(.*)'))
    async def cb_approve(event):
        article_id = event.data.decode('utf-8').split('_', 1)[1]
        with get_db_connection() as conn:
            update_article_status(conn, article_id, 'approved')
        await event.edit(f"✅ Article `{article_id}` approved and ready for drip-feed publishing.")

    @client.on(events.CallbackQuery(pattern=b'reject_(.*)'))
    async def cb_reject(event):
        article_id = event.data.decode('utf-8').split('_', 1)[1]
        # MVP: Simple reject string
        with get_db_connection() as conn:
            update_article_status(conn, article_id, 'rejected', "Rejected via Telegram Bot inline button.")
        await event.edit(f"❌ Article `{article_id}` rejected.")

    @client.on(events.CallbackQuery(pattern=b'edit_(.*)'))
    async def cb_edit(event):
        article_id = event.data.decode('utf-8').split('_', 1)[1]
        await event.answer("Editing via Telegram UI will be built in the next iteration. For now, please review on the database.", alert=True)

    @client.on(events.NewMessage(pattern=r'/post_article\s+(.+)'))
    async def cmd_post_article(event):
        raw_text = event.pattern_match.group(1).strip()
        if not raw_text:
            await event.reply("Usage: `/post_article {markdown body}`")
            return
            
        article_id = str(uuid.uuid4())
        now = datetime.datetime.utcnow().isoformat()
        
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO article_queue (
                    id, source_topic, language, validity, status, body_markdown, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (article_id, 'manual', 'en', 'valid', 'pending_review', raw_text, now))
            conn.commit()
            
        await event.reply(f"✅ Manual article queued for review (Stage 3 bypass) with ID: `{article_id}`")

    logger.info("Starting SINPES Writer Bot...")
    client.start(bot_token=BOT_TOKEN)
    client.run_until_disconnected()

if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    start_bot()
