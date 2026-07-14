import json
import tempfile
import unittest
import sqlite3
from pathlib import Path

from pydantic import ValidationError

from app.schemas.ingestion import FontIngestionPayload
from app.ingestion.channel_listener import find_mergeable_family_uploads, queue_incoming_upload


VALID_METADATA = {
    "version": 1,
    "slug": "Example Sans",
    "locale": "en",
    "category": "sans",
    "description": "A" * 250,
    "use_cases": ["web", "editorial"],
    "keywords": {"en": "example sans, open source font"},
    "flagged_as_new_category": False,
}


class FontIngestionPayloadTests(unittest.TestCase):
    def test_use_cases_are_title_cased_and_acronyms_are_preserved(self):
        metadata = {
            **VALID_METADATA,
            "use_cases": ["web design", "ui", "UX research"],
        }
        payload = FontIngestionPayload.from_telegram_caption(
            json.dumps(metadata), ["/tmp/example.ttf"]
        )
        self.assertEqual(payload.use_cases, ["Web Design", "UI", "UX Research"])

    def test_existing_multilingual_metadata_is_converted(self):
        legacy = {
            "display_name": "Miama Nueva",
            "category": "Script",
            "use_cases": ["wedding", "branding"],
            "en": "E" * 250,
            "es": "S" * 250,
            "pt": "P" * 250,
        }

        with tempfile.TemporaryDirectory() as directory:
            metadata_path = Path(directory) / "metadata.json"
            metadata_path.write_text(json.dumps(legacy), encoding="utf-8")
            payload = FontIngestionPayload.from_metadata_file(
                str(metadata_path), ["/tmp/miama.otf"]
            )

        self.assertEqual(payload.slug, "miama-nueva")
        self.assertEqual(set(payload.translations), {"en", "es", "pt"})
        self.assertIn("Miama Nueva", payload.keywords["en"])

    def test_telegram_caption_round_trips_through_upload_queue(self):
        payload = FontIngestionPayload.from_telegram_caption(
            json.dumps(VALID_METADATA),
            ["/tmp/example.ttf"],
        )
        connection = sqlite3.connect(":memory:")
        connection.row_factory = sqlite3.Row
        connection.execute(
            """
            CREATE TABLE upload_queue (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                file_path TEXT NOT NULL,
                text_payload TEXT NOT NULL,
                image_path TEXT NOT NULL,
                received_at TEXT NOT NULL,
                processed BOOLEAN NOT NULL DEFAULT 0,
                attempts INTEGER DEFAULT 0,
                last_error TEXT,
                failed INTEGER DEFAULT 0
            )
            """
        )

        queue_incoming_upload(connection, payload)
        row = dict(connection.execute("SELECT * FROM upload_queue").fetchone())
        worker_payload = FontIngestionPayload.from_queue(
            text_payload=row["text_payload"],
            fallback_file=row["file_path"],
            image_path=row["image_path"],
        )
        connection.close()

        self.assertEqual(worker_payload, payload)
        self.assertEqual(row["file_path"], "/tmp/example.ttf")

    def test_caption_and_queue_use_same_contract(self):
        incoming = FontIngestionPayload.from_telegram_caption(
            json.dumps(VALID_METADATA),
            ["/tmp/example.ttf"],
        )
        queued = FontIngestionPayload.from_queue(
            incoming.model_dump_json(),
            fallback_file="/tmp/ignored.ttf",
        )

        self.assertEqual(queued, incoming)
        self.assertEqual(queued.slug, "example-sans")

    def test_split_telegram_albums_merge_into_one_queue_item(self):
        connection = sqlite3.connect(":memory:")
        connection.row_factory = sqlite3.Row
        connection.execute(
            """CREATE TABLE upload_queue (
                id INTEGER PRIMARY KEY AUTOINCREMENT, file_path TEXT NOT NULL,
                text_payload TEXT NOT NULL, image_path TEXT NOT NULL, received_at TEXT NOT NULL,
                processed BOOLEAN NOT NULL DEFAULT 0, attempts INTEGER DEFAULT 0,
                last_error TEXT, failed INTEGER DEFAULT 0
            )"""
        )
        first_files = [f"/tmp/inter-{index}.otf" for index in range(10)]
        first = FontIngestionPayload.from_telegram_caption(json.dumps({**VALID_METADATA, "slug": "inter"}), first_files)
        queue_incoming_upload(connection, first)
        matches = find_mergeable_family_uploads(connection, "inter")
        all_files = first_files + [f"/tmp/inter-{index}.otf" for index in range(10, 18)]
        combined = first.model_copy(update={"font_files": all_files})
        result = queue_incoming_upload(connection, combined, [row["id"] for row in matches])

        rows = connection.execute("SELECT text_payload FROM upload_queue").fetchall()
        connection.close()
        self.assertTrue(result["merged"])
        self.assertEqual(len(rows), 1)
        self.assertEqual(len(json.loads(rows[0]["text_payload"])["font_files"]), 18)

    def test_invalid_caption_is_rejected_before_queueing(self):
        invalid = {**VALID_METADATA, "description": "Too short"}

        with self.assertRaises(ValidationError):
            FontIngestionPayload.from_telegram_caption(
                json.dumps(invalid),
                ["/tmp/example.ttf"],
            )

    def test_legacy_json_file_gets_transport_defaults(self):
        legacy = dict(VALID_METADATA)
        legacy.pop("version")

        with tempfile.TemporaryDirectory() as directory:
            metadata_path = Path(directory) / "metadata.json"
            metadata_path.write_text(json.dumps(legacy), encoding="utf-8")
            payload = FontIngestionPayload.from_queue(
                str(metadata_path),
                fallback_file="/tmp/legacy.ttf",
                image_path="/tmp/preview.png",
            )

        self.assertEqual(payload.version, 1)
        self.assertEqual(payload.font_files, ["/tmp/legacy.ttf"])
        self.assertEqual(payload.image_path, "/tmp/preview.png")

    def test_album_metadata_file_adds_fonts_and_does_not_require_image(self):
        metadata = dict(VALID_METADATA)

        with tempfile.TemporaryDirectory() as directory:
            metadata_path = Path(directory) / "metadata.json"
            metadata_path.write_text(json.dumps(metadata), encoding="utf-8")
            payload = FontIngestionPayload.from_metadata_file(
                str(metadata_path),
                ["/tmp/example-regular.ttf", "/tmp/example-bold.ttf"],
            )

        self.assertEqual(
            payload.font_files,
            ["/tmp/example-regular.ttf", "/tmp/example-bold.ttf"],
        )
        self.assertIsNone(payload.image_path)

    def test_unknown_fields_are_rejected(self):
        invalid = {**VALID_METADATA, "unexpected": True}

        with self.assertRaises(ValidationError):
            FontIngestionPayload.from_telegram_caption(
                json.dumps(invalid),
                ["/tmp/example.ttf"],
            )


if __name__ == "__main__":
    unittest.main()
