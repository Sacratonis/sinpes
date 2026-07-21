import json
import os
import traceback
import hashlib
import re
import zipfile
import io
import logging
from datetime import datetime, timezone
from apscheduler.schedulers.background import BackgroundScheduler
from fontTools.ttLib import TTFont

from app.db.database import get_db, get_db_connection
from app.core.config import config
from app.services.drip_feed_scheduler import run_daily_batch
from app.services.db_backup import backup_database

# --- ORCHESTRATOR IMPORTS ---
from app.ingestion.media_processor import HeroImageGenerationError, process_hero_image
from app.ingestion.font_converter import generate_woff2, resolve_display_name
from app.ingestion.storage_archive import delete_r2_objects, upload_to_r2
from app.ingestion.bouncer import check_editorial_quality
from app.ingestion.category_resolver import resolve_category, resolve_expired_pending_categories
from app.services.telegram_notify import send_telegram_alert
from app.schemas.ingestion import FontIngestionPayload

logger = logging.getLogger(__name__)


class DuplicateFontUpload(RuntimeError):
    """An already-saved family should be skipped, not sent to the dead-letter queue."""


class RetryableFontFamilyError(RuntimeError):
    """No partial family was saved; the complete upload can be retried safely."""


def detect_variable_font(font_obj: TTFont) -> bool:
    """Use the OpenType variation table as the only variable-font truth source."""
    return "fvar" in font_obj


def build_font_object_key(slug: str, path: str, weight: int, style: str) -> str:
    """Create a stable R2 key that preserves same-weight subfamilies such as HC/LC."""
    stem = os.path.splitext(os.path.basename(path))[0]
    variant = re.sub(r"[^a-z0-9]+", "-", stem.lower()).strip("-")
    normalized_slug = slug.replace("_", "-")
    if variant.startswith(f"{normalized_slug}-"):
        variant = variant[len(normalized_slug) + 1:]
    variant = variant or hashlib.sha256(stem.encode("utf-8")).hexdigest()[:12]
    return f"fonts/{slug}-{weight}-{style}-{variant}.woff2"


def resolve_variant_weight(font_obj: TTFont, path: str) -> int:
    """Use an explicit subfamily name when a font incorrectly stores Regular/400."""
    weight = 400
    if 'OS/2' in font_obj:
        weight = int(font_obj['OS/2'].usWeightClass or 400)
    if weight != 400:
        return weight

    subfamily = ""
    if "name" in font_obj:
        subfamily = font_obj["name"].getDebugName(17) or font_obj["name"].getDebugName(2) or ""
    source = f"{subfamily} {os.path.splitext(os.path.basename(path))[0]}"
    named_weights = (
        (r"\b(?:extra|ultra)[-_ ]?bold\b", 800),
        (r"\bsemi[-_ ]?bold\b", 600),
        (r"\b(?:extra|ultra)[-_ ]?light\b", 200),
        (r"\bblack\b", 900),
        (r"\bheavy\b", 900),
        (r"\bbold\b", 700),
        (r"\bmedium\b", 500),
        (r"\blight\b", 300),
        (r"\bthin\b", 100),
    )
    for pattern, value in named_weights:
        if re.search(pattern, source, re.IGNORECASE):
            return value
    return weight


def select_primary_variant_url(variants: list[dict]) -> str:
    """Prefer a normal Regular/400 face for previews and legacy consumers."""
    if not variants:
        return ""
    primary = min(
        variants,
        key=lambda item: (
            item.get("style") != "normal",
            abs(int(item.get("weight", 400)) - 400),
            "regular" not in str(item.get("filename", "")).lower(),
        ),
    )
    return str(primary.get("url", ""))

def process_font_upload(next_item: dict):
    """
    The ultimate orchestrator: Processes entire font families, uploads to R2, 
    and saves the metadata to the database for the 3 AM snapshot.
    """
    # 1. Parse the shared, versioned ingestion contract. The parser also supports
    # legacy queue rows whose text_payload points to a JSON metadata file.
    payload = FontIngestionPayload.from_queue(
        text_payload=next_item.get('text_payload', ''),
        fallback_file=next_item.get('file_path', ''),
        image_path=next_item.get('image_path', ''),
    )
    font_paths = payload.font_files
    primary_font_path = font_paths[0]
    
    logger.info(f"ORCHESTRATOR: Triggered for family with {len(font_paths)} weights.")
    
    # 2. Contract fields are already validated before expensive processing begins.
    raw_slug = payload.slug
    slug = re.sub(r'\s*\(\d+\)\s*', '', raw_slug).replace(' ', '_').replace('(', '').replace(')', '').lower()
    
    keyword_phrases = payload.keywords
    flagged_as_new_category = payload.flagged_as_new_category
    raw_category = payload.category
    use_cases = payload.use_cases
    description = payload.description
    locale = payload.locale

    with open(primary_font_path, 'rb') as f:
        file_hash = hashlib.sha256(f.read()).hexdigest()

    # Idempotency gate: repeated Telegram uploads must not consume category,
    # image, or R2 work and must not become misleading failed queue items.
    with get_db() as duplicate_conn:
        from app.repositories.font_repo import FontRepository
        duplicate_repo = FontRepository(duplicate_conn)
        existing_slug = duplicate_repo.find_slug_by_hash(file_hash)
        if existing_slug:
            raise DuplicateFontUpload(
                f"Duplicate upload skipped: this font file is already saved as '{existing_slug}'."
            )
        if duplicate_repo.slug_exists(slug):
            raise DuplicateFontUpload(
                f"Duplicate family skipped: the slug '{slug}' already exists."
            )

    # --- GATE 1: Editorial quality check (Bouncer) ---
    # Runs before any expensive operation. Raises on failure to trigger dead-letter.
    with get_db() as _conn_gate:
        quality_passed = check_editorial_quality(description, send_telegram_alert)
    if not quality_passed:
        raise ValueError(f"ORCHESTRATOR: Editorial quality gate failed for '{slug}' — description too thin or templated. Font not saved.")

    # --- GATE 2: Category resolution (grace-period typo detection) ---
    with get_db() as _conn_cat:
        category = resolve_category(_conn_cat, raw_category, flagged_as_new_category, send_telegram_alert)

    # Preflight the complete family before generating a hero or writing to R2.
    prepared_variants = []
    display_name = slug.replace('_', ' ').title()
    is_demo = False
    is_variable = False
    try:
        for index, path in enumerate(font_paths):
            if not os.path.isfile(path):
                raise FileNotFoundError(f"Missing family member: {path}")
            font_obj = TTFont(path)
            try:
                if index == 0:
                    display_name, is_demo = resolve_display_name(font_obj, slug)
                variant_is_variable = detect_variable_font(font_obj)
                is_variable = is_variable or variant_is_variable
                weight_class = resolve_variant_weight(font_obj, path)
                style = "italic" if "italic" in os.path.basename(path).lower() else "normal"
                prepared_variants.append(
                    {
                        "path": path,
                        "bytes": generate_woff2(font_obj),
                        "weight": weight_class,
                        "style": style,
                        "filename": os.path.basename(path),
                        "is_variable": variant_is_variable,
                    }
                )
            finally:
                font_obj.close()
    except Exception as exc:
        raise RetryableFontFamilyError(f"Family preflight failed for '{slug}': {exc}") from exc

    if len(prepared_variants) != len(font_paths):
        raise RetryableFontFamilyError(
            f"Family preflight produced {len(prepared_variants)}/{len(font_paths)} variants for '{slug}'"
        )

    uploaded_keys: list[str] = []
    database_saved = False

    def tracked_upload(**kwargs):
        key = kwargs["key"]
        url = upload_to_r2(**kwargs)
        uploaded_keys.append(key)
        return url

    try:
        with get_db() as image_conn:
            existing_image_urls = [
                row[0]
                for row in image_conn.execute(
                    "SELECT DISTINCT seo_image_url FROM font_translations WHERE seo_image_url != ''"
                ).fetchall()
            ]
        seo_image_url = process_hero_image(
            slug=slug,
            display_name=display_name,
            category=category,
            use_cases=use_cases,
            keyword_phrases=keyword_phrases,
            upload_callback=tracked_upload,
            font_path=primary_font_path,
            existing_image_urls=existing_image_urls,
        )
        if not seo_image_url:
            raise HeroImageGenerationError(
                f"Hero image generation returned no image for '{slug}'. Font not saved."
            )

        variants_list = []
        for prepared in prepared_variants:
            font_key = build_font_object_key(
                slug, prepared["path"], prepared["weight"], prepared["style"]
            )
            font_url = tracked_upload(
                data=prepared["bytes"],
                key=font_key,
                content_type="font/woff2",
                cache_control="max-age=31536000",
            )
            variants_list.append(
                {
                    "weight": prepared["weight"],
                    "style": prepared["style"],
                    "url": font_url,
                    "filename": prepared["filename"],
                    "is_variable": prepared["is_variable"],
                }
            )

        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
            for path in font_paths:
                zip_file.write(path, os.path.basename(path))
            zip_file.writestr(
                "README.txt",
                f"SINPES Font Archive\n\nFamily: {slug.replace('_', ' ').title()}\n"
                f"Files included: {len(font_paths)}\n\n"
                "Thank you for supporting open-source typography.",
            )
        zip_bytes = zip_buffer.getvalue()
        zip_size_kb = len(zip_bytes) // 1024
        download_zip_url = tracked_upload(
            data=zip_bytes,
            key=f"downloads/{slug}.zip",
            content_type="application/zip",
            cache_control="max-age=31536000",
        )

        with get_db() as conn:
            from app.repositories.font_repo import FontRepository
            from app.schemas.font import FontRegistry, FontTranslation

            f_repo = FontRepository(conn)
            now_iso = datetime.now(timezone.utc).isoformat()
            f_repo.insert_font(
                FontRegistry(
                    slug=slug,
                    display_name=display_name,
                    is_demo=is_demo,
                    is_variable=is_variable,
                    category=category,
                    variants=json.dumps(variants_list),
                    weights=json.dumps(sorted({v["weight"] for v in variants_list})),
                    woff2_url=select_primary_variant_url(variants_list),
                    file_format="zip",
                    file_size_kb=zip_size_kb,
                    use_cases=json.dumps(use_cases) if isinstance(use_cases, list) else str(use_cases),
                    status="queued",
                    file_hash=file_hash,
                    last_updated=now_iso,
                    download_zip_url=download_zip_url,
                    embedded_family_name=None,
                )
            )
            for translation_locale, translation_description in {
                locale: description,
                **payload.translations,
            }.items():
                f_repo.insert_translation(
                    FontTranslation(
                        slug=slug,
                        locale=translation_locale,
                        description=translation_description,
                        seo_image_url=seo_image_url,
                    )
                )
            conn.commit()
            database_saved = True
        logger.info("ORCHESTRATOR: Saved complete family '%s' (%s variants)", slug, len(variants_list))
    except Exception as exc:
        if not database_saved and uploaded_keys:
            try:
                delete_r2_objects(uploaded_keys)
            except Exception as cleanup_exc:
                logger.error("Could not clean R2 objects from failed attempt: %s", cleanup_exc)
        if isinstance(exc, HeroImageGenerationError):
            raise
        raise RetryableFontFamilyError(f"Complete family upload failed for '{slug}': {exc}") from exc

def release_next_from_queue():
    """Process exactly one family; the scheduler calls this continuously."""
    with get_db() as conn:
        from app.repositories.queue_repo import QueueRepository
        q_repo = QueueRepository(conn)
        next_item = q_repo.get_oldest_pending_item()
        if not next_item:
            return False

    item_id = next_item.id
    attempts = next_item.attempts + 1

    try:
        process_font_upload(next_item.model_dump())
        with get_db() as conn:
            from app.repositories.queue_repo import QueueRepository
            q_repo = QueueRepository(conn)
            q_repo.mark_processed(item_id)
            conn.commit()
        logger.info(f"Successfully processed queue item {item_id}")
        return True
    except DuplicateFontUpload as e:
        logger.info("Queue item %s skipped safely: %s", item_id, e)
        with get_db() as conn:
            from app.repositories.queue_repo import QueueRepository
            QueueRepository(conn).mark_processed(item_id)
            conn.commit()
        send_telegram_alert(f"ℹ️ Queue item #{item_id}: {e}")
        return True
    except HeroImageGenerationError as e:
        error_msg = str(e)
        delay_seconds = min(1800 * (2 ** min(attempts - 1, 3)), 21600)
        logger.warning(
            "Hero image unavailable for queue item %s; deferring for %s seconds: %s",
            item_id,
            delay_seconds,
            error_msg,
        )
        with get_db() as conn:
            from app.repositories.queue_repo import QueueRepository
            QueueRepository(conn).defer_item(item_id, error_msg, delay_seconds)
            conn.commit()
        if attempts == 1:
            send_telegram_alert(
                f"⏳ Queue item #{item_id}: hero services are unavailable. "
                f"Automatic retry scheduled in {delay_seconds // 60} minutes."
            )
        return False
    except RetryableFontFamilyError as e:
        error_msg = str(e)
        delay_seconds = min(300 * (2 ** min(attempts - 1, 5)), 21600)
        logger.warning(
            "Complete family processing failed for queue item %s; retrying in %s seconds: %s",
            item_id,
            delay_seconds,
            error_msg,
        )
        with get_db() as conn:
            from app.repositories.queue_repo import QueueRepository

            QueueRepository(conn).defer_item(item_id, error_msg, delay_seconds)
            conn.commit()
        return False
    except Exception as e:
        error_msg = str(e)
        logger.error(f"Failed to process item {item_id} (Attempt {attempts}): {error_msg}")
        traceback.print_exc()
        with get_db() as conn:
            from app.repositories.queue_repo import QueueRepository
            q_repo = QueueRepository(conn)
            q_repo.increment_attempts(item_id, error_msg)
            if attempts >= config.MAX_RETRIES:
                logger.error(f"Item {item_id} exceeded max retries. Marking as failed.")
                q_repo.mark_failed(item_id)
            conn.commit()
        return False

def start_scheduler() -> BackgroundScheduler:
    scheduler = BackgroundScheduler(timezone="UTC")
    scheduler.add_job(
        release_next_from_queue,
        trigger='interval',
        seconds=max(1, config.QUEUE_POLL_SECONDS),
        max_instances=1,
        coalesce=True,
    )
    
    def run_category_resolver():
        # Use context manager here too to prevent leaks!
        with get_db() as conn:
            resolve_expired_pending_categories(conn)

    scheduler.add_job(run_category_resolver, trigger='interval', minutes=1, max_instances=1)
    scheduler.add_job(run_daily_batch, trigger='cron', hour=3, minute=0, max_instances=1, misfire_grace_time=300)
    from app.services.article_publisher import publish_next_approved_article
    scheduler.add_job(
        publish_next_approved_article,
        trigger='cron', day_of_week='mon,wed,fri', hour=9, minute=0,
        max_instances=1, misfire_grace_time=1800,
    )
    scheduler.add_job(backup_database, trigger='cron', hour=2, minute=0, max_instances=1)

    def run_oracle_collection():
        from app.oracle.trend_aggregator import run_oracle
        with get_db() as conn:
            run_oracle(conn)

    def send_oracle_briefing():
        from app.oracle.trend_aggregator import fetch_oracle_hitlist, format_oracle_briefing
        from app.services.telegram_notify import send_telegram_alert
        with get_db() as conn:
            message = format_oracle_briefing(fetch_oracle_hitlist(conn))
        send_telegram_alert(message)

    scheduler.add_job(
        run_oracle_collection, trigger='cron', hour=config.oracle.scrape_start_hour_utc,
        minute=0, max_instances=1, misfire_grace_time=1800,
    )
    scheduler.add_job(
        send_oracle_briefing, trigger='cron', hour=config.oracle.briefing_hour_utc,
        minute=0, max_instances=1, misfire_grace_time=1800,
    )
    
    scheduler.start()
    return scheduler
