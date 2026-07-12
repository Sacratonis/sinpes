# DELETED — 2026-07-11
#
# This file has been decommissioned. Its logic was superseded by
# app/ingestion/media_processor.py (process_hero_image / finalize_seo_image).
#
# The original implementation was hardcoded to config.CF_API_TOKEN which no
# longer exists in config.py, so calling it would have thrown AttributeError.
# The dual-export (WebP + JPG) it provided is intentionally not replicated here —
# JPG generation only belongs in the Writer Bot / Medium distribution pipeline,
# not the font ingestion pipeline.
#
# Safe to remove this file entirely from the repository.
