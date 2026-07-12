import time
import json
import os
import traceback
import hashlib
import re
import zipfile
import io
import logging
from datetime import datetime, timedelta, timezone
from apscheduler.schedulers.background import BackgroundScheduler
from fontTools.ttLib import TTFont

from app.db.database import get_db, get_db_connection
from app.core.config import config
from app.services.drip_feed_scheduler import run_daily_batch
from app.services.db_backup import backup_database

# --- ORCHESTRATOR IMPORTS ---
from app.ingestion.media_processor import process_hero_image
from app.ingestion.font_converter import generate_woff2, resolve_display_name
from app.ingestion.storage_archive import upload_to_r2
from app.ingestion.bouncer import check_editorial_quality
from app.ingestion.category_resolver import resolve_category, resolve_expired_pending_categories
from app.services.telegram_notify import send_telegram_alert
from app.schemas.ingestion import FontIngestionPayload

logger = logging.getLogger(__name__)

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

    # --- GATE 1: Editorial quality check (Bouncer) ---
    # Runs before any expensive operation. Raises on failure to trigger dead-letter.
    with get_db() as _conn_gate:
        quality_passed = check_editorial_quality(description, send_telegram_alert)
    if not quality_passed:
        raise ValueError(f"ORCHESTRATOR: Editorial quality gate failed for '{slug}' — description too thin or templated. Font not saved.")

    # --- GATE 2: Category resolution (grace-period typo detection) ---
    with get_db() as _conn_cat:
        category = resolve_category(_conn_cat, raw_category, flagged_as_new_category, send_telegram_alert)

    with open(primary_font_path, 'rb') as f:
        file_hash = hashlib.sha256(f.read()).hexdigest()

    seo_image_url = None
    variants_list = []
    is_demo = False  # Default; overridden by resolve_display_name if font loads cleanly

    def r2_upload_callback(**kwargs):
        try:
            return upload_to_r2(**kwargs)
        except Exception as e:
            logger.error(f"ORCHESTRATOR: R2 Upload failed: {e}")
            raise e

    # 🌟 FIX 5: Load primary font ONCE for metadata (Saves massive I/O) 🌟
    display_name = slug.replace('_', ' ').title()
    primary_font_obj = None
    if primary_font_path and os.path.exists(primary_font_path):
        try:
            primary_font_obj = TTFont(primary_font_path)
            display_name, is_demo = resolve_display_name(primary_font_obj)
        except Exception as e:
            logger.warning(f"ORCHESTRATOR: Could not extract display name from primary font: {e}")

    try:
        seo_image_url = process_hero_image(
            slug=slug, 
            display_name=display_name, 
            category=category, 
            use_cases=use_cases, 
            keyword_phrases=keyword_phrases, 
            upload_callback=r2_upload_callback
        ) 
        logger.info(f"ORCHESTRATOR: Hero image processed! URL: {seo_image_url}")
    except Exception as e:
        logger.error(f"ORCHESTRATOR: Error processing image: {e}")
        traceback.print_exc()

    if not seo_image_url:
        raise RuntimeError(f"ORCHESTRATOR: Hero image generation failed for '{slug}' — both CF Worker and Pollinations returned nothing. Font not saved.")

    # 3. Loop through ALL font weights
    for path in font_paths:
        if not os.path.exists(path):
            continue
            
        try:
            # Reuse primary font object if it's the same file, otherwise load it
            if path == primary_font_path and primary_font_obj:
                font_obj = primary_font_obj
            else:
                font_obj = TTFont(path)
                
            woff2_bytes = generate_woff2(font_obj)
            
            weight_class = 400 
            style = "normal"
            
            if 'OS/2' in font_obj:
                weight_class = font_obj['OS/2'].usWeightClass
                
            if 'italic' in os.path.basename(path).lower():
                style = "italic"

            font_key = f"fonts/{slug}-{weight_class}-{style}.woff2"
            font_url = upload_to_r2(
                data=woff2_bytes, 
                key=font_key, 
                content_type="font/woff2", 
                cache_control="max-age=31536000"
            )
            
            logger.info(f"ORCHESTRATOR: Uploaded weight {weight_class} ({style}) -> {font_url}")
            
            variants_list.append({
                "weight": weight_class,
                "style": style,
                "url": font_url,
                "filename": os.path.basename(path)
            })
            
            # Close font object if we loaded a secondary weight
            if path != primary_font_path:
                font_obj.close()
                
        except Exception as e:
            logger.error(f"ORCHESTRATOR: Error processing weight {path}: {e}")
            traceback.print_exc()

    if primary_font_obj:
        primary_font_obj.close()

    # 🌟 FIX 4: zip_size_kb defaults to None instead of 0 🌟
    download_zip_url = None
    zip_size_kb = None 
    try:
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
            for path in font_paths:
                if os.path.exists(path):
                    zip_file.write(path, os.path.basename(path))
            
            readme_text = f"SINPES Font Archive\n\nFamily: {slug.replace('_', ' ').title()}\nFiles included: {len(font_paths)}\n\nThank you for supporting open-source typography."
            zip_file.writestr("README.txt", readme_text)

        zip_bytes = zip_buffer.getvalue()
        zip_size_kb = len(zip_bytes) // 1024 
        zip_key = f"downloads/{slug}.zip"
        download_zip_url = upload_to_r2(
            data=zip_bytes, key=zip_key, content_type="application/zip", cache_control="max-age=31536000"
        )
        logger.info(f"ORCHESTRATOR: Master ZIP uploaded -> {download_zip_url} ({zip_size_kb} KB)")
    except Exception as e:
        logger.error(f"ORCHESTRATOR: Failed to create/upload ZIP: {e}")
        traceback.print_exc()

    if not download_zip_url:
        raise RuntimeError(f"ORCHESTRATOR: ZIP upload failed for '{slug}' — font would go live with a broken download link. Font not saved.")

    # 4. SAVE TO DATABASE (🌟 FIX 2: Context Manager prevents leaks 🌟)
    if variants_list:
        try:
            with get_db() as conn:
                from app.repositories.font_repo import FontRepository
                from app.schemas.font import FontRegistry, FontTranslation
                
                f_repo = FontRepository(conn)
                now_iso = datetime.now(timezone.utc).isoformat()
                
                use_cases_str = json.dumps(use_cases) if isinstance(use_cases, list) else str(use_cases)
                variants_str = json.dumps(variants_list) 
                weights_str = json.dumps(list(set([v['weight'] for v in variants_list]))) 

                f_repo.insert_font(FontRegistry(
                    slug=slug, display_name=display_name, is_demo=is_demo, category=category,
                    variants=variants_str, weights=weights_str, woff2_url=variants_list[0]['url'],
                    file_format='zip', file_size_kb=zip_size_kb or 0, use_cases=use_cases_str,
                    status='queued', file_hash=file_hash, last_updated=now_iso,
                    download_zip_url=download_zip_url, embedded_family_name=None
                ))
                
                descriptions = {locale: description, **payload.translations}
                for translation_locale, translation_description in descriptions.items():
                    f_repo.insert_translation(FontTranslation(
                        slug=slug,
                        locale=translation_locale,
                        description=translation_description,
                        seo_image_url=seo_image_url,
                    ))
                
                conn.commit()
                logger.info(f"ORCHESTRATOR: Saved family '{slug}' ({len(variants_list)} weights) to database!")
                
        except Exception as e:
            logger.error(f"ORCHESTRATOR: Database insert failed: {e}")
            traceback.print_exc()
            raise # Re-raise so the queue manager catches it and retries!

def release_next_from_queue():
    """🌟 FIX 1: Infinite Retry Loop & Dead Letter Queue Logic 🌟"""
    with get_db() as conn:
        from app.repositories.meta_repo import MetaRepository
        from app.repositories.queue_repo import QueueRepository
        m_repo = MetaRepository(conn)
        q_repo = QueueRepository(conn)
        
        last_release_ts_str = m_repo.get_value('last_queue_release_at')
        last_release_ts = float(last_release_ts_str) if last_release_ts_str else 0.0
        last_release = datetime.fromtimestamp(last_release_ts)
        
        interval = timedelta(minutes=config.QUEUE_INTERVAL_MINUTES)
        
        if datetime.now() - last_release < interval:
            return 

        next_item = q_repo.get_oldest_pending_item()
        if not next_item:
            return 

        item_id = next_item.id
        attempts = next_item.attempts + 1

        try:
            # Pass as dict to avoid sqlite3.Row issues in nested functions
            process_font_upload(next_item.model_dump()) 
            
            # Success!
            q_repo.mark_processed(item_id)
            logger.info(f"Successfully processed queue item {item_id}")
            
        except Exception as e:
            error_msg = str(e)
            logger.error(f"Failed to process item {item_id} (Attempt {attempts}): {error_msg}")
            traceback.print_exc()
            
            # Dead Letter Logic
            if attempts >= config.MAX_RETRIES:
                logger.error(f"Item {item_id} exceeded max retries. Marking as failed.")
                q_repo.mark_failed(item_id)
            
            q_repo.increment_attempts(item_id, error_msg)

        # Always update timestamp so a failure doesn't lock the queue
        m_repo.set_value('last_queue_release_at', str(time.time()))
        conn.commit()

def start_scheduler() -> BackgroundScheduler:
    scheduler = BackgroundScheduler(timezone="UTC")
    scheduler.add_job(release_next_from_queue, trigger='interval', minutes=1, max_instances=1)
    
    def run_category_resolver():
        # Use context manager here too to prevent leaks!
        with get_db() as conn:
            resolve_expired_pending_categories(conn)

    scheduler.add_job(run_category_resolver, trigger='interval', minutes=1, max_instances=1)
    scheduler.add_job(run_daily_batch, trigger='cron', hour=3, minute=0, max_instances=1, misfire_grace_time=300)
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
