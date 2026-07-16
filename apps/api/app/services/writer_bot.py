import asyncio
import io
import json
import logging

from telethon import Button, TelegramClient, events

from app.core.config import config
from app.db.database import get_db
from app.services.article_image_service import finalize_article_image
from app.services.content_integrity import ContentIntegrityError
from app.services.writer_pipeline import (
    InsufficientDepth,
    WriterValidationFailure,
    edit_stored_article,
    generate_article,
    publication_integrity_report,
    queue_manual_article,
)

logger = logging.getLogger("sinpes.writer_bot")


def approval_block_message(exc: Exception) -> str:
    """Return the exact deterministic reason instead of a generic approval failure."""
    return (
        f"⚠️ Approval blocked by deterministic validation: {exc}\n"
        "Edit the article to resolve this exact issue, then approve it again."
    )


def is_owner_private_chat(sender_id, chat_id, is_private: bool, owner_id) -> bool:
    try:
        return bool(is_private and int(sender_id) == int(owner_id) and int(chat_id) == int(owner_id))
    except (TypeError, ValueError):
        return False


def start_bot():
    token = config.writer.telegram_bot_token
    review_chat_id = config.writer.telegram_review_channel_id
    if not token or not review_chat_id:
        raise RuntimeError("Writer Telegram token and review chat ID must be configured")
    review_chat_id = int(review_chat_id)
    client = TelegramClient("sinpes_writer_bot_session", config.TELEGRAM_API_ID, config.TELEGRAM_API_HASH)

    async def authorized(event) -> bool:
        try:
            permissions = await client.get_permissions(review_chat_id, event.sender_id)
            allowed = bool(permissions.is_admin or permissions.is_creator)
        except Exception:
            logger.exception("Could not verify Writer channel administrator")
            allowed = False
        if not allowed:
            if isinstance(event, events.CallbackQuery.Event):
                await event.answer("This Writer bot is limited to channel administrators.", alert=True)
            else:
                await event.reply("This Writer bot is limited to channel administrators.")
            return False
        return True

    async def owner_authorized(event) -> bool:
        if not await authorized(event):
            return False
        owner_id = config.writer.telegram_admin_chat_id
        allowed = is_owner_private_chat(event.sender_id, event.chat_id, event.is_private, owner_id)
        if not allowed:
            await event.reply("This publishing command is limited to the configured owner in a private chat.")
        return allowed

    @client.on(events.NewMessage(pattern=r"^/(start|help)$"))
    async def help_command(event):
        if not await authorized(event): return
        await event.reply(
            "SINPES Writer\n\n"
            "/draft <topic>\n/draft <en|es|pt> <topic>\n/pending\n/review <id>\n/review_meta <id>\n"
            "/approve <id>\n/reject <id> <reason>\n/edit <id> <title|meta|body> <value>\n"
            "/publish_articles [limit] — owner-only, one deployment\n"
            "/post_article <title> | <meta> | <font1,font2> | <HTML body>\n"
            "Upload a curated image with caption: /article_image <id>"
        )

    @client.on(events.NewMessage(pattern=r"^/pending$"))
    async def pending_command(event):
        if not await authorized(event): return
        with get_db() as conn:
            rows = conn.execute(
                "SELECT id,title,language,status FROM article_queue WHERE status IN ('pending_review','awaiting_image') ORDER BY created_at"
            ).fetchall()
        if not rows:
            await event.reply("No pending articles for review.")
            return
        await event.reply("Pending articles:\n" + "\n".join(f"`{r['id']}` · {r['status']} · {r['language'].upper()} · {r['title']}" for r in rows))

    @client.on(events.NewMessage(pattern=r"^/draft(?:\s+(en|es|pt))?\s+(.+)$"))
    async def draft_command(event):
        if not await authorized(event): return
        language = event.pattern_match.group(1) or "en"
        topic = event.pattern_match.group(2).strip()
        await event.reply("Writer started. Article depth will be validated against its editorial scope.")

        def run():
            with get_db() as conn:
                return generate_article(conn, topic, language)
        try:
            result = await asyncio.get_running_loop().run_in_executor(None, run)
            if result["validity"] == "invalid":
                await event.reply(f"Topic rejected: {result['reasoning']}")
            else:
                await event.reply(f"✅ Draft ready: {result['title']}\nID: `{result['id']}`\nUse `/review {result['id']}`")
        except InsufficientDepth as exc:
            await event.reply(
                f"Topic needs a narrower angle. The {exc.scope} draft reached {exc.word_count} words without enough depth.\n"
                f"Suggested angle: {exc.suggestion}"
            )
        except WriterValidationFailure as exc:
            await event.reply(
                "⚠️ Draft needs human attention after the original attempt and one complete rewrite both failed validation.\n"
                f"Reason: {exc.reason}\nNothing was queued or published."
            )
            document = io.BytesIO(json.dumps(exc.draft, ensure_ascii=False, indent=2).encode("utf-8"))
            document.name = "sinpes-failed-writer-draft.json"
            await client.send_file(
                event.chat_id,
                document,
                caption="Complete failed Writer response for human review",
            )
        except ContentIntegrityError as exc:
            await event.reply(
                f"⚠️ Draft blocked by content integrity: {exc}\n"
                "Use a distinct target keyword or intent. Fuzzy similarity alone never blocks a draft."
            )
        except Exception as exc:
            logger.exception("Writer draft failed")
            await event.reply(f"❌ Draft failed: {exc}")

    async def send_review(event, article_id: str):
        with get_db() as conn:
            row = conn.execute("SELECT * FROM article_queue WHERE id=?", (article_id,)).fetchone()
        if not row:
            await event.reply("Article not found.")
            return
        body = row["body_html"] or row["body_markdown"] or ""
        length_note = " · SHORT—review depth carefully" if (row["word_count"] or 0) < 800 else ""
        message = (
            f"Title: {row['title']}\nMeta: {row['meta_description']}\nLanguage: {row['language']}\n"
            f"Words: {row['word_count']}{length_note}\nReasoning: {row['validity_reasoning']}\n"
            f"Image: {row['image_url'] or 'None'}"
        )
        await event.reply(message, parse_mode=None)

        # Telegram messages are limited to 4096 characters. Send the complete
        # article in readable chunks instead of silently truncating the review.
        chunks = []
        remaining = body
        while remaining:
            if len(remaining) <= 3500:
                chunks.append(remaining)
                break
            split_at = remaining.rfind("\n", 0, 3500)
            if split_at < 1000:
                split_at = remaining.rfind("</p>", 0, 3500)
                split_at = split_at + 4 if split_at >= 1000 else 3500
            chunks.append(remaining[:split_at])
            remaining = remaining[split_at:].lstrip()
        for index, chunk in enumerate(chunks, start=1):
            await event.reply(f"Article {index}/{len(chunks)}\n\n{chunk}", parse_mode=None)

        buttons = [[
            Button.inline("✅ Approve", data=f"approve:{article_id}"),
            Button.inline("❌ Reject", data=f"reject:{article_id}"),
        ]]
        await event.reply(f"Review complete for `{article_id}`.", buttons=buttons)

    @client.on(events.NewMessage(pattern=r"^/review\s+([a-f0-9-]+)$"))
    async def review_command(event):
        if not await authorized(event): return
        await send_review(event, event.pattern_match.group(1))

    @client.on(events.NewMessage(pattern=r"^/review_meta\s+([a-f0-9-]+)$"))
    async def review_meta_command(event):
        if not await authorized(event): return
        article_id = event.pattern_match.group(1)
        with get_db() as conn:
            row = conn.execute("SELECT * FROM article_queue WHERE id=?", (article_id,)).fetchone()
        if not row:
            await event.reply("Article not found.")
            return
        source_data = json.loads(row["source_keyword_data"] or "{}")
        metadata = {
            "id": row["id"], "status": row["status"], "language": row["language"],
            "source_topic": row["source_topic"],
            "source_signal": {key: source_data.get(key) for key in ("name", "source", "region", "metric", "score", "writer_model")},
            "title": row["title"], "slug": row["slug"], "meta_description": row["meta_description"],
            "target_keyword": row["target_keyword"],
            "secondary_keywords": json.loads(row["secondary_keywords"] or "[]"),
            "referenced_font_slugs": json.loads(row["referenced_font_slugs"] or "[]"),
            "font_claims": json.loads(row["font_claims"] or "[]"),
            "image_url": row["image_url"], "image_alt_text": row["image_alt_text"],
            "word_count": row["word_count"], "validity_reasoning": row["validity_reasoning"],
            "content_scope": row["content_scope"],
            "content_integrity": source_data.get("content_integrity", {}),
            "body_html": row["body_html"] or row["body_markdown"] or "",
        }
        serialized = json.dumps(metadata, ensure_ascii=False, indent=2)
        if len(serialized) <= 3500:
            await event.reply(serialized, parse_mode=None)
        else:
            document = io.BytesIO(serialized.encode("utf-8"))
            document.name = f"sinpes-article-{article_id}.json"
            await client.send_file(
                event.chat_id,
                document,
                caption=f"Complete Writer contract for {article_id}",
            )

    def set_status(article_id: str, status: str, note=None) -> bool:
        with get_db() as conn:
            if status == "approved":
                publication_integrity_report(conn, article_id)
            cursor = conn.execute(
                "UPDATE article_queue SET status=?, rejection_note=? WHERE id=? AND status IN ('pending_review','edited','rejected')",
                (status, note, article_id),
            )
            conn.commit()
            return cursor.rowcount == 1

    @client.on(events.NewMessage(pattern=r"^/approve\s+([a-f0-9-]+)$"))
    async def approve_command(event):
        if not await authorized(event): return
        try:
            ok = set_status(event.pattern_match.group(1), "approved")
            await event.reply(
                "✅ Approved for the next editorial publishing slot."
                if ok else
                "⚠️ Approval blocked: only pending-review, edited, or rejected articles can be approved."
            )
        except (ContentIntegrityError, ValueError) as exc:
            await event.reply(approval_block_message(exc))

    @client.on(events.CallbackQuery(pattern=rb"^approve:(.+)$"))
    async def approve_callback(event):
        if not await authorized(event): return
        article_id = event.pattern_match.group(1).decode()
        try:
            ok = set_status(article_id, "approved")
            await event.edit(
                "✅ Approved for the next editorial publishing slot."
                if ok else
                "⚠️ Approval blocked: only pending-review, edited, or rejected articles can be approved."
            )
        except (ContentIntegrityError, ValueError) as exc:
            await event.edit(approval_block_message(exc))

    @client.on(events.NewMessage(pattern=r"^/reject\s+([a-f0-9-]+)\s+(.+)$"))
    async def reject_command(event):
        if not await authorized(event): return
        ok = set_status(event.pattern_match.group(1), "rejected", event.pattern_match.group(2).strip())
        await event.reply("❌ Rejected and reason saved." if ok else "Article cannot be rejected.")

    @client.on(events.CallbackQuery(pattern=rb"^reject:(.+)$"))
    async def reject_callback(event):
        if not await authorized(event): return
        article_id = event.pattern_match.group(1).decode()
        await event.answer(f"Send: /reject {article_id} <reason>", alert=True)

    @client.on(events.NewMessage(pattern=r"(?s)^/edit\s+([a-f0-9-]+)\s+(title|meta|body)\s+(.+)$"))
    async def edit_command(event):
        if not await authorized(event): return
        article_id, field, value = event.pattern_match.groups()
        try:
            with get_db() as conn:
                updated = edit_stored_article(conn, article_id, field, value)
                conn.commit()
            await event.reply("✏️ Saved and fully revalidated. Review and approve it again." if updated else "Article cannot be edited.")
        except Exception as exc:
            await event.reply(f"❌ Edit rejected; the previous article was preserved: {exc}")

    @client.on(events.NewMessage(func=lambda event: event.is_private, pattern=r"^/publish_articles(?:\s+(\d+))?$"))
    async def publish_articles_command(event):
        if not await owner_authorized(event): return
        limit = int(event.pattern_match.group(1) or 9)
        if not 1 <= limit <= 20:
            await event.reply("Limit must be between 1 and 20.")
            return
        await event.reply(f"Publishing up to {limit} approved articles in one website deployment…")

        def run():
            from app.services.article_publisher import publish_approved_articles
            return publish_approved_articles(limit=limit, automatic=False, source="writer_batch")

        try:
            result = await asyncio.get_running_loop().run_in_executor(None, run)
            if not result["published_count"]:
                await event.reply(
                    f"No articles were published. {result['reason']}"
                    + (f"\nReturned to review: {len(result['rejected'])}" if result["rejected"] else "")
                )
                return
            await event.reply(
                f"✅ {result['published_count']} article(s) published in one deployment.\n"
                f"IndexNow URLs queued: {result['indexnow_url_count']}\n"
                f"Slugs: {', '.join(result['slugs'])}"
            )
        except Exception as exc:
            logger.exception("Writer batch publication failed")
            await event.reply(f"❌ Batch publication failed safely: {exc}")

    @client.on(events.NewMessage(pattern=r"(?s)^/post_article\s+(.+)$"))
    async def post_article_command(event):
        if not await authorized(event): return
        parts = [part.strip() for part in event.pattern_match.group(1).split("|", 3)]
        if len(parts) != 4:
            await event.reply("Usage: /post_article <title> | <meta> | <font1,font2> | <HTML body>")
            return
        try:
            with get_db() as conn:
                article_id = queue_manual_article(conn, parts[0], parts[1], parts[2].split(","), parts[3])
            await event.reply(
                f"✅ Manual article validated. ID: `{article_id}`\n"
                f"Now upload one curated image with caption `/article_image {article_id}`."
            )
        except Exception as exc:
            await event.reply(f"❌ Manual article rejected: {exc}")

    @client.on(events.NewMessage(pattern=r"^/article_image\s+([a-f0-9-]+)$"))
    async def article_image_command(event):
        if not await authorized(event): return
        article_id = event.pattern_match.group(1)
        mime = getattr(getattr(event.message, "file", None), "mime_type", "") or ""
        if not event.photo and not mime.startswith("image/"):
            await event.reply("Attach one image and use `/article_image <id>` as its caption.")
            return
        with get_db() as conn:
            row = conn.execute("SELECT * FROM article_queue WHERE id=?", (article_id,)).fetchone()
        if not row or row["status"] != "awaiting_image":
            await event.reply("Article is not waiting for a curated image.")
            return
        try:
            raw = await event.download_media(file=bytes)
            alt = row["image_alt_text"] or f"Editorial typography for {row['title']}"
            url = await asyncio.get_running_loop().run_in_executor(
                None,
                lambda: finalize_article_image(
                    raw, row["slug"], row["title"], row["target_keyword"],
                    json.loads(row["secondary_keywords"] or "[]"), alt,
                ),
            )
            with get_db() as conn:
                conn.execute(
                    "UPDATE article_queue SET image_url=?, image_alt_text=?, status='pending_review' WHERE id=? AND status='awaiting_image'",
                    (url, alt, article_id),
                )
                conn.commit()
            await event.reply(f"✅ Curated image saved. Use `/review {article_id}`.")
        except Exception as exc:
            logger.exception("Manual article image failed")
            await event.reply(f"❌ Image upload failed: {exc}")

    logger.info("Starting SINPES Writer Bot")
    client.start(bot_token=token)
    client.run_until_disconnected()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    start_bot()
