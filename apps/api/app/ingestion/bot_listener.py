"""Telegram album listener for font-family ingestion."""

import asyncio
import logging
import os
import re
from collections import defaultdict

from pydantic import ValidationError
from telethon import TelegramClient, events

from app.core.config import config
from app.db.database import get_db
from app.ingestion.channel_listener import queue_incoming_upload
from app.schemas.ingestion import FontIngestionPayload


logger = logging.getLogger("sinpes.telegram_listener")
DOWNLOAD_DIR = os.getenv("TELEGRAM_DOWNLOAD_DIR", "/tmp/sinpes_uploads")


def get_family_root(filename: str) -> str:
    name = os.path.splitext(filename)[0]
    previous = None
    while previous != name:
        previous = name
        name = re.sub(
            r"[-_ ]?(Bold|Italic|Light|Thin|ExtraBold|ExtraLight|Black|Medium|Regular|Roman|Oblique|Condensed|Extended|Ultra|Mono|SemiBold|Book|Demi|Heavy|W[0-9]+)\b",
            "",
            name,
            flags=re.IGNORECASE,
        )
    return name.strip("- _")


def _document_filename(message) -> str:
    for attribute in message.document.attributes:
        filename = getattr(attribute, "file_name", None)
        if filename:
            return filename
    return "unknown_file"


def create_client() -> TelegramClient:
    return TelegramClient(
        "sinpes_bot_session",
        int(config.TELEGRAM_API_ID),
        config.TELEGRAM_API_HASH,
    )


def register_handlers(client: TelegramClient) -> None:
    async def require_channel_admin(event) -> bool:
        try:
            permissions = await client.get_permissions(
                config.TELEGRAM_MAIN_CHANNEL_ID,
                event.sender_id,
            )
            allowed = bool(permissions.is_admin or permissions.is_creator)
        except Exception:
            allowed = False
        if not allowed:
            await event.reply("This bot is limited to SINPES channel administrators.")
        return allowed

    @client.on(events.NewMessage(func=lambda event: event.is_private, pattern=r"^/start$"))
    async def handle_start(event):
        if not await require_channel_admin(event):
            return
        await event.reply(
            "SINPES bot is ready. Send one album with one font family and one JSON file. "
            "Use /help to see every command."
        )

    @client.on(events.NewMessage(func=lambda event: event.is_private, pattern=r"^/help$"))
    async def handle_help(event):
        if not await require_channel_admin(event):
            return
        await event.reply(
            "/stats\n/queue\n/queue_failed\n/retry <id>\n/search <text>\n"
            "/categories_pending\n/category_confirm <id>\n/category_decline <id>\n"
            "/publish\n/publish_status\n/publish_force\n/unpublish <slug>\n"
            "/erase <slug>\n/erase_confirm <slug>\n/hitlist\n"
            "/oracle_status\n/oracle_run"
        )

    @client.on(events.Album(chats=config.TELEGRAM_MAIN_CHANNEL_ID))
    async def handle_album(event):
        groups = defaultdict(lambda: {"fonts": [], "metadata": ""})
        pending_metadata = ""

        for message in event.messages:
            if not message.document:
                continue

            filename = _document_filename(message)
            path = await client.download_media(message, file=DOWNLOAD_DIR)
            if not path:
                continue

            lower_path = path.lower()
            if lower_path.endswith(".json"):
                pending_metadata = path
                continue
            if not lower_path.endswith((".otf", ".ttf")):
                continue

            family = get_family_root(filename)
            groups[family]["fonts"].append(path)

        if not groups:
            await event.reply("❌ Upload rejected: no TTF or OTF font files found.")
            return
        if not pending_metadata:
            await event.reply("❌ Upload rejected: the album needs one JSON metadata file.")
            return
        if len(groups) > 1:
            await event.reply("❌ Upload rejected: send only one font family per album.")
            return

        family, data = next(iter(groups.items()))
        try:
            payload = FontIngestionPayload.from_metadata_file(
                pending_metadata,
                data["fonts"],
            )
        except (ValidationError, ValueError) as exc:
            await event.reply(f"❌ Upload rejected: invalid metadata.\n\n{exc}")
            return

        try:
            with get_db() as connection:
                queue_incoming_upload(connection, payload)
            await event.reply(
                f"✅ {family} queued with {len(payload.font_files)} font file(s)."
            )
        except Exception as exc:
            logger.exception("Could not queue Telegram album")
            await event.reply(f"❌ Could not queue upload: {exc}")

    @client.on(events.NewMessage(func=lambda event: event.is_private, pattern=r"^/queue$"))
    async def handle_queue(event):
        if not await require_channel_admin(event):
            return
        with get_db() as connection:
            from app.repositories.queue_repo import QueueRepository

            stats = QueueRepository(connection).get_stats()
        await event.reply(
            f"Queue: {stats.pending_items} pending, {stats.dead_letter_items} failed."
        )

    @client.on(events.NewMessage(func=lambda event: event.is_private, pattern=r"^/queue_failed$"))
    async def handle_queue_failed(event):
        if not await require_channel_admin(event):
            return
        with get_db() as connection:
            from app.repositories.queue_repo import QueueRepository
            rows = QueueRepository(connection).get_failed_items()
        if not rows:
            await event.reply("No failed queue items.")
            return
        await event.reply("\n".join(
            f"#{row['id']} — {row['last_error'] or 'Unknown error'}" for row in rows
        ))

    @client.on(events.NewMessage(func=lambda event: event.is_private, pattern=r"^/retry\s+(\d+)$"))
    async def handle_retry(event):
        if not await require_channel_admin(event):
            return
        item_id = int(event.pattern_match.group(1))
        with get_db() as connection:
            from app.repositories.queue_repo import QueueRepository
            changed = QueueRepository(connection).retry_item(item_id)
            connection.commit()
        await event.reply(
            f"✅ Queue item #{item_id} is ready to retry." if changed
            else f"Queue item #{item_id} is not failed or does not exist."
        )

    @client.on(events.NewMessage(func=lambda event: event.is_private, pattern=r"^/stats$"))
    async def handle_stats(event):
        if not await require_channel_admin(event):
            return
        with get_db() as connection:
            total = connection.execute("SELECT COUNT(*) FROM font_registry").fetchone()[0]
            active = connection.execute(
                "SELECT COUNT(*) FROM font_registry WHERE status = 'active'"
            ).fetchone()[0]
            vault = connection.execute(
                "SELECT COUNT(*) FROM font_registry WHERE status = 'vault'"
            ).fetchone()[0]
        await event.reply(f"Fonts: {total} total, {active} live, {vault} in vault.")

    @client.on(events.NewMessage(func=lambda event: event.is_private, pattern=r"^/search\s+(.+)$"))
    async def handle_search(event):
        if not await require_channel_admin(event):
            return
        query = event.pattern_match.group(1).strip()
        with get_db() as connection:
            rows = connection.execute(
                "SELECT slug, display_name, status FROM font_registry "
                "WHERE slug LIKE ? OR display_name LIKE ? LIMIT 20",
                (f"%{query}%", f"%{query}%"),
            ).fetchall()
        if not rows:
            await event.reply(f"No fonts found for {query}.")
            return
        await event.reply(
            "\n".join(f"{row['display_name']} — {row['status']}" for row in rows)
        )

    @client.on(events.NewMessage(func=lambda event: event.is_private, pattern=r"^/categories_pending$"))
    async def handle_categories_pending(event):
        if not await require_channel_admin(event):
            return
        from app.repositories.category_repo import CategoryRepository
        with get_db() as connection:
            rows = CategoryRepository(connection).get_unresolved_pending_categories()
        if not rows:
            await event.reply("No categories are waiting for approval.")
            return
        await event.reply("\n".join(f"#{row.id} — {row.name}" for row in rows))

    @client.on(events.NewMessage(func=lambda event: event.is_private, pattern=r"^/category_confirm\s+(\d+)$"))
    async def handle_category_add(event):
        if not await require_channel_admin(event):
            return
        from app.ingestion.category_resolver import create_category

        from app.repositories.category_repo import CategoryRepository
        category_id = int(event.pattern_match.group(1))
        with get_db() as connection:
            repo = CategoryRepository(connection)
            pending = repo.get_unresolved_pending_category(category_id)
            if not pending:
                await event.reply(f"Pending category #{category_id} does not exist or is already resolved.")
                return
            category_name = pending.name
            slug = create_category(connection, category_name)
            connection.execute(
                "DELETE FROM meta WHERE key = ?",
                (f"declined_category:{slug}",),
            )
            repo.resolve_pending_category(category_id)
            connection.commit()
        await event.reply(f"✅ Category #{category_id} confirmed: {category_name} ({slug}).")

    @client.on(events.NewMessage(func=lambda event: event.is_private, pattern=r"^/category_decline\s+(\d+)$"))
    async def handle_category_decline(event):
        if not await require_channel_admin(event):
            return
        from app.ingestion.category_resolver import get_category_slug

        from app.repositories.category_repo import CategoryRepository
        category_id = int(event.pattern_match.group(1))
        with get_db() as connection:
            repo = CategoryRepository(connection)
            pending = repo.get_unresolved_pending_category(category_id)
            if not pending:
                await event.reply(f"Pending category #{category_id} does not exist or is already resolved.")
                return
            category_name = pending.name
            slug = get_category_slug(category_name)
            repo.resolve_pending_category(category_id)
            connection.execute(
                "INSERT INTO meta(key, value) VALUES(?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (f"declined_category:{slug}", category_name),
            )
            connection.execute(
                "UPDATE font_registry SET status = 'removed' "
                "WHERE category = ? AND status IN ('vault', 'queued')",
                (slug,),
            )
            connection.commit()
        await event.reply(
            f"❌ Category #{category_id} declined: {category_name}. Correct the JSON before uploading again."
        )

    @client.on(events.NewMessage(func=lambda event: event.is_private, pattern=r"^/hitlist$"))
    async def handle_hitlist(event):
        if not await require_channel_admin(event):
            return
        from app.oracle.trend_aggregator import fetch_oracle_hitlist

        with get_db() as connection:
            results = fetch_oracle_hitlist(connection)
        if not results:
            await event.reply("No stored SEO opportunities. Run /oracle_run, then check /oracle_status.")
            return
        lines = [
            f"{index}. {item['name']} — {item.get('source', 'Unknown')}\n"
            f"   {item.get('keywords', {}).get('en', '')}"
            for index, item in enumerate(results[:20], start=1)
        ]
        await event.reply("\n".join(lines))

    @client.on(events.NewMessage(func=lambda event: event.is_private, pattern=r"^/oracle_status$"))
    async def handle_oracle_status(event):
        if not await require_channel_admin(event):
            return
        from app.oracle.trend_aggregator import get_oracle_status
        with get_db() as connection:
            status = get_oracle_status(connection)
        if status["status"] == "never_run":
            await event.reply("Oracle has never completed a run. Use /oracle_run.")
            return
        source_lines = []
        for source, data in status.get("sources", {}).items():
            line = f"{source}: {data['status']} ({data.get('count', 0)} keywords)"
            if data.get("error"):
                line += f" — {data['error']}"
            source_lines.append(line)
        await event.reply(
            f"Oracle last run: {status.get('finished_at')}\n"
            f"SEO opportunities: {status.get('keyword_count', 0)}\n" + "\n".join(source_lines)
        )

    @client.on(events.NewMessage(func=lambda event: event.is_private, pattern=r"^/oracle_run$"))
    async def handle_oracle_run(event):
        if not await require_channel_admin(event):
            return
        from app.oracle.trend_aggregator import run_oracle
        await event.reply("Oracle search started. This can take about one minute.")

        def execute():
            with get_db() as connection:
                return run_oracle(connection)

        try:
            result = await asyncio.get_running_loop().run_in_executor(None, execute)
            await event.reply(
                f"✅ Oracle finished with {result['keyword_count']} SEO opportunities. "
                "Use /hitlist to view them or /oracle_status for source details."
            )
        except Exception as exc:
            logger.exception("Oracle manual run failed")
            await event.reply(f"❌ Oracle failed: {exc}")

    async def publish(event, force=False):
        from app.services.drip_feed_scheduler import run_daily_batch
        await event.reply("Publishing started.")
        try:
            result = await asyncio.get_running_loop().run_in_executor(None, run_daily_batch, force)
            if result.get("triggered"):
                await event.reply("✅ Snapshot uploaded and Cloudflare deployment triggered. Use /publish_status to check it.")
            else:
                await event.reply(f"⚠️ Publish not started: {result.get('reason', 'unknown reason')}.")
        except Exception as exc:
            logger.exception("Manual publish failed")
            await event.reply(f"❌ Publishing failed: {exc}")

    @client.on(events.NewMessage(func=lambda event: event.is_private, pattern=r"^/publish$"))
    async def handle_publish(event):
        if not await require_channel_admin(event):
            return
        await publish(event)

    @client.on(events.NewMessage(func=lambda event: event.is_private, pattern=r"^/publish_force$"))
    async def handle_publish_force(event):
        if not await require_channel_admin(event):
            return
        await publish(event, force=True)

    @client.on(events.NewMessage(func=lambda event: event.is_private, pattern=r"^/publish_status$"))
    async def handle_publish_status(event):
        if not await require_channel_admin(event):
            return
        from app.services.drip_feed_scheduler import get_publish_status
        with get_db() as connection:
            status = get_publish_status(connection)
        state = "waiting for deployment confirmation" if status["in_progress"] else "idle"
        await event.reply(
            f"Publish: {state}.\nTriggered: {status['triggered_at'] or 'never'}\n"
            f"Confirmed: {status['successful_at'] or 'never'}\n"
            f"Error: {status['last_error'] or 'none'}"
        )

    @client.on(events.NewMessage(func=lambda event: event.is_private, pattern=r"^/unpublish\s+([a-z0-9-]+)$"))
    async def handle_unpublish(event):
        if not await require_channel_admin(event):
            return
        slug = event.pattern_match.group(1)
        with get_db() as connection:
            cursor = connection.execute(
                "UPDATE font_registry SET status = 'removed' WHERE slug = ?", (slug,)
            )
            connection.commit()
        await event.reply(
            f"✅ {slug} unpublished. Run /publish to update the website." if cursor.rowcount
            else f"Font '{slug}' was not found."
        )

    @client.on(events.NewMessage(func=lambda event: event.is_private, pattern=r"^/erase\s+([a-z0-9-]+)$"))
    async def handle_erase(event):
        if not await require_channel_admin(event):
            return
        from app.services.admin_actions import prepare_erase
        slug = event.pattern_match.group(1)
        with get_db() as connection:
            font, keys = prepare_erase(connection, slug)
        if not font:
            await event.reply(f"Font '{slug}' was not found.")
            return
        await event.reply(
            f"⚠️ Erase {font['display_name']} ({slug}) from the database and {len(keys)} R2 files? "
            f"Send /erase_confirm {slug} within 5 minutes. Backups are kept."
        )

    @client.on(events.NewMessage(func=lambda event: event.is_private, pattern=r"^/erase_confirm\s+([a-z0-9-]+)$"))
    async def handle_erase_confirm(event):
        if not await require_channel_admin(event):
            return
        from app.services.admin_actions import confirm_erase
        slug = event.pattern_match.group(1)
        try:
            with get_db() as connection:
                deleted = confirm_erase(connection, slug)
            await event.reply(
                f"✅ {slug} erased from the database and {deleted} R2 files. Run /publish to update the website."
            )
        except ValueError as exc:
            await event.reply(f"❌ {exc}")


def start_listener() -> None:
    os.makedirs(DOWNLOAD_DIR, exist_ok=True)
    logging.basicConfig(level=logging.INFO)
    client = create_client()
    register_handlers(client)
    logger.info("Starting SINPES Telegram album listener")
    client.start(bot_token=config.oracle.telegram_bot_token)
    client.run_until_disconnected()


if __name__ == "__main__":
    start_listener()
