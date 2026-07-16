"""Owner-only, read-only Telegram interface for SINPES SEO audits."""

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from telethon import TelegramClient, events

from app.core.config import config
from app.db.database import get_db
from app.seo.auditor import (
    audit_article_cannibalization,
    audit_article_font_links,
    audit_font_images,
    build_read_only_report,
)

logger = logging.getLogger("sinpes.seo_bot")


def seconds_until_weekly_report(
    now: datetime,
    *,
    weekday_utc: int,
    hour_utc: int,
) -> float:
    """Return the delay to the next configured weekly UTC report."""
    current = now.astimezone(timezone.utc)
    days_ahead = (weekday_utc - current.weekday()) % 7
    target = (current + timedelta(days=days_ahead)).replace(
        hour=hour_utc,
        minute=0,
        second=0,
        microsecond=0,
    )
    if target <= current:
        target += timedelta(days=7)
    return (target - current).total_seconds()


def is_authorized_private_chat(sender_id: int | None, chat_id: int | None, is_private: bool, admin_chat_id: int) -> bool:
    """Require the configured owner in the owner's direct bot conversation."""
    return bool(is_private and sender_id == admin_chat_id and chat_id == admin_chat_id)


def _format_audit(report: dict) -> str:
    return (
        "SEO content audit\n"
        f"Pages checked: {report['pages_checked']}\n"
        f"Hard conflicts: {len(report['hard_conflicts'])}\n"
        f"Fuzzy advisories: {len(report['advisories'])}\n"
        "Exact conflicts block in the Writer. Fuzzy overlap remains advisory."
    )


def _format_images(report: dict) -> str:
    return (
        "SEO image audit\n"
        f"Active fonts: {report['active_fonts']}\n"
        f"Expected localized image records: {report['expected_localized_images']}\n"
        f"Missing: {len(report['missing'])}\n"
        f"Insecure URLs: {len(report['insecure'])}\n"
        f"Cross-family duplicate URLs: {len(report['cross_family_duplicates'])}"
    )


def _format_links(report: dict) -> str:
    return (
        "SEO internal-link audit\n"
        f"Articles checked: {report['articles_checked']}\n"
        f"Articles with font links: {report['articles_with_font_links']}\n"
        f"Articles with broken font links: {len(report['broken'])}"
    )


def _format_report(report: dict) -> str:
    return "\n\n".join((
        _format_audit(report["content"]),
        _format_images(report["images"]),
        _format_links(report["links"]),
    ))


def start_bot():
    if not config.seo.enabled:
        raise RuntimeError("SEO bot is disabled; set SEO_BOT_ENABLED=true after tests pass")
    token = config.seo.telegram_bot_token
    admin_chat_id = config.seo.telegram_admin_chat_id
    if not token or not admin_chat_id:
        raise RuntimeError("SEO Telegram token and private admin chat ID must be configured")
    admin_chat_id = int(admin_chat_id)
    client = TelegramClient("sinpes_seo_bot_session", config.TELEGRAM_API_ID, config.TELEGRAM_API_HASH)

    async def authorized(event) -> bool:
        allowed = is_authorized_private_chat(event.sender_id, event.chat_id, event.is_private, admin_chat_id)
        if not allowed:
            await event.reply("Unauthorized.")
        return allowed

    @client.on(events.NewMessage(pattern=r"^/(start|help)$"))
    async def help_command(event):
        if not await authorized(event): return
        await event.reply(
            "SINPES SEO Expert — read only\n\n"
            "/seo_status\n/seo_audit\n/seo_pages\n/seo_images\n/seo_links\n"
            "/seo_opportunities\n/seo_report\n"
            "This bot reports findings. It cannot publish, delete, redirect, deploy, or change R2."
        )

    @client.on(events.NewMessage(pattern=r"^/seo_status$"))
    async def status_command(event):
        if not await authorized(event): return
        await event.reply(
            "SEO bot: ready (read only)\n"
            f"Groq: {'configured' if config.seo.groq_api_key else 'not configured'}\n"
            "Google Search Console: not connected\n"
            f"Bing Webmaster: {'configured' if config.oracle.bing_webmaster_api_key else 'not configured'}"
        )

    @client.on(events.NewMessage(pattern=r"^/(seo_audit|seo_pages)$"))
    async def audit_command(event):
        if not await authorized(event): return
        await event.reply("Running deterministic read-only content audit…")

        def run():
            with get_db() as conn:
                return audit_article_cannibalization(conn)

        report = await asyncio.get_running_loop().run_in_executor(None, run)
        await event.reply(_format_audit(report))

    @client.on(events.NewMessage(pattern=r"^/seo_images$"))
    async def images_command(event):
        if not await authorized(event): return
        with get_db() as conn:
            report = audit_font_images(conn)
        await event.reply(_format_images(report))

    @client.on(events.NewMessage(pattern=r"^/seo_links$"))
    async def links_command(event):
        if not await authorized(event): return
        with get_db() as conn:
            report = audit_article_font_links(conn)
        await event.reply(_format_links(report))

    @client.on(events.NewMessage(pattern=r"^/seo_opportunities$"))
    async def opportunities_command(event):
        if not await authorized(event): return
        from app.oracle.trend_aggregator import fetch_oracle_hitlist, format_oracle_hitlist
        with get_db() as conn:
            results = fetch_oracle_hitlist(conn)
        await event.reply(format_oracle_hitlist(results, heading="SEO opportunities"))

    @client.on(events.NewMessage(pattern=r"^/seo_report$"))
    async def report_command(event):
        if not await authorized(event): return
        await event.reply("Running complete deterministic read-only SEO report…")

        def run():
            with get_db() as conn:
                return build_read_only_report(conn)

        report = await asyncio.get_running_loop().run_in_executor(None, run)
        await event.reply(_format_report(report))

    async def weekly_report_loop():
        while True:
            delay = seconds_until_weekly_report(
                datetime.now(timezone.utc),
                weekday_utc=config.seo.report_weekday_utc,
                hour_utc=config.seo.report_hour_utc,
            )
            await asyncio.sleep(delay)
            try:
                def run():
                    with get_db() as conn:
                        return build_read_only_report(conn)

                report = await asyncio.get_running_loop().run_in_executor(None, run)
                await client.send_message(admin_chat_id, "Weekly SINPES SEO report\n\n" + _format_report(report))
            except Exception:
                logger.exception("Weekly SEO report failed")

    logger.info("Starting SINPES SEO Expert Bot")
    client.start(bot_token=token)
    client.loop.create_task(weekly_report_loop())
    client.run_until_disconnected()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    start_bot()
