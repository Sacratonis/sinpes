# SINPES Foundry

SINPES is a static typography site backed by an automated font-ingestion and publishing service.

## Main services

- `apps/web`: Astro static website deployed to Cloudflare Pages.
- `apps/api`: FastAPI API, SQLite database, scheduler, and R2 integration.
- `app.ingestion.bot_listener`: Telegram album listener.

## Font workflow

1. Send one Telegram album containing one font family and one JSON metadata file.
2. The listener groups the TTF/OTF files and validates the JSON.
3. The validated family is stored in `upload_queue`.
4. The scheduler converts fonts to WOFF2, generates a preview through the Cloudflare Worker, uploads assets to R2, and marks the family `queued`.
5. The daily drip job activates queued fonts, uploads font and blog snapshots, and triggers Cloudflare Pages.
6. Cloudflare calls `/build-success` after a successful deployment.

The metadata format is documented in `apps/api/INGESTION_CONTRACT.md`.

## Local setup

### API

Copy `apps/api/.env.example` to `apps/api/.env` and fill in the required values. Use a workspace-local `DATABASE_PATH` during development.

From `apps/api`, install `requirements.txt`, run Alembic migrations, and start FastAPI with Uvicorn.

Run backend tests with Python unittest discovery in the `tests` directory.

### Web

From `apps/web`, install packages and run the Astro development server.

Cloudflare builds require:

- `SNAPSHOT_PRESIGNED_URL`: font registry snapshot URL.
- `BLOG_SNAPSHOT_PRESIGNED_URL`: blog registry snapshot URL.

Without the font snapshot URL, local builds use one mock font. Without the blog snapshot URL, blog routes are empty.

## Production processes

Install and enable both service units from `apps/api/systemd`:

- `sinpes-api.service`
- `sinpes-telethon.service`

Update `User`, `WorkingDirectory`, and executable paths in the service files to match the server. The current production server uses `/root/sinpes`; the checked-in examples use `/opt/sinpes` and the `sinpes` user.

Never run two Telegram listeners with the same bot session at the same time.

## Verification

CI runs backend unit tests and builds the complete Astro site with Pagefind.
