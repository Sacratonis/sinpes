# Telegram Font Ingestion Contract (v1)

Send one Telegram album containing:

- One or more `.ttf` or `.otf` font files from the same family.
- One JSON metadata file.

Do not upload an image. The queue processor generates the preview through the Cloudflare Worker and uploads it to R2.

The JSON metadata file must contain:

- `version`: `1`
- `slug`: letters, numbers, hyphens, or underscores
- `locale`: `en`, `es`, or `pt`
- `category`: the font category
- `description`: at least 250 original characters
- `use_cases`: at least one value
- `keywords`: must include `en`
- `flagged_as_new_category`: `true` or `false`

The Telegram listener downloads and groups the font files. It adds their local paths to the validated payload and stores the complete payload as JSON in `upload_queue.text_payload`.

The queue processor validates the same payload before converting fonts, generating the Cloudflare preview, uploading assets to R2, and saving the registry record.

Old queue rows that contain raw JSON or a path to a JSON file remain supported.
