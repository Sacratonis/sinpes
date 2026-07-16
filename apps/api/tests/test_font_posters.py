import io
import unittest

from PIL import Image

from app.ingestion.media_processor import (
    build_scene_prompt,
    compose_font_poster,
    find_duplicate_hero,
    hash_distance,
    perceptual_image_hash,
    process_hero_image,
)


class FontPosterTests(unittest.TestCase):
    def test_scene_prompt_requests_photography_without_ai_text(self):
        prompt = build_scene_prompt("Script", ["Wedding Invitations", "Editorial Design"], "miama-nueva")
        self.assertIn("photograph", prompt.lower())
        self.assertIn("Wedding Invitations", prompt)
        self.assertIn("no typography", prompt.lower())
        self.assertIn("no numbers", prompt.lower())
        self.assertIn("no digits", prompt.lower())
        self.assertIn("no visible human faces", prompt.lower())
        self.assertIn("faces", prompt.lower())

    def test_scene_direction_varies_by_font(self):
        prompts = {
            build_scene_prompt("Sans Serif", ["Editorial Design"], f"family-{index}")
            for index in range(12)
        }
        self.assertGreaterEqual(len(prompts), 6)

    def test_retry_changes_scene_direction(self):
        first = build_scene_prompt("Sans Serif", ["Editorial Design"], "family", 0)
        second = build_scene_prompt("Sans Serif", ["Editorial Design"], "family", 1)
        self.assertNotEqual(first, second)

    def test_poster_has_fixed_wide_dimensions(self):
        source = Image.new("RGB", (900, 900), (120, 150, 170))
        source_bytes = io.BytesIO()
        source.save(source_bytes, "JPEG")

        result = compose_font_poster(source_bytes.getvalue(), "Example Font", "")
        poster = Image.open(io.BytesIO(result))

        self.assertEqual(poster.size, (1600, 700))
        self.assertEqual(poster.mode, "RGB")

    def test_font_name_is_not_baked_into_hero(self):
        source = Image.new("RGB", (900, 900), (120, 150, 170))
        source_bytes = io.BytesIO()
        source.save(source_bytes, "JPEG")

        first = compose_font_poster(source_bytes.getvalue(), "First Name", "missing-font.otf")
        second = compose_font_poster(source_bytes.getvalue(), "Different Name", "another-font.otf")

        self.assertEqual(first, second)

    def test_perceptual_hash_ignores_small_color_change(self):
        first = Image.new("RGB", (400, 200), "white")
        second = Image.new("RGB", (800, 400), (245, 245, 245))
        for image in (first, second):
            for x in range(image.width // 2):
                for y in range(image.height):
                    image.putpixel((x, y), (20, 20, 20))
        encoded = []
        for image in (first, second):
            buffer = io.BytesIO()
            image.save(buffer, "JPEG")
            encoded.append(buffer.getvalue())
        self.assertLessEqual(
            hash_distance(perceptual_image_hash(encoded[0]), perceptual_image_hash(encoded[1])),
            50,
        )

    def test_duplicate_detector_returns_matching_url(self):
        image = Image.new("RGB", (400, 200), "navy")
        buffer = io.BytesIO()
        image.save(buffer, "JPEG")
        data = buffer.getvalue()

        class Response:
            content = data
            def raise_for_status(self):
                return None

        from unittest.mock import patch
        with patch("app.ingestion.media_processor.requests.get", return_value=Response()):
            self.assertEqual(
                find_duplicate_hero(data, ["https://example.invalid/hero.webp"]),
                "https://example.invalid/hero.webp",
            )

    def test_generation_timeout_uses_next_attempt(self):
        source = Image.new("RGB", (900, 900), (120, 150, 170))
        source_bytes = io.BytesIO()
        source.save(source_bytes, "JPEG")

        from requests.exceptions import Timeout
        from unittest.mock import patch
        with (
            patch(
                "app.ingestion.media_processor.generate_ai_image_bytes",
                side_effect=[Timeout("temporary"), source_bytes.getvalue()],
            ),
            patch("app.ingestion.media_processor.find_duplicate_hero", return_value=None),
        ):
            result = process_hero_image(
                slug="example",
                display_name="Example",
                category="Sans Serif",
                use_cases=["UI Design"],
                keyword_phrases={"en": "Example font"},
                upload_callback=lambda **_kwargs: "https://example.invalid/example.webp",
                max_generation_attempts=2,
            )
        self.assertEqual(result, "https://example.invalid/example.webp")


if __name__ == "__main__":
    unittest.main()
