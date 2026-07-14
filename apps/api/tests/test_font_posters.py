import io
import unittest

from PIL import Image

from app.ingestion.media_processor import build_scene_prompt, compose_font_poster


class FontPosterTests(unittest.TestCase):
    def test_scene_prompt_requests_photography_without_ai_text(self):
        prompt = build_scene_prompt("Script", ["Wedding Invitations", "Editorial Design"], "miama-nueva")
        self.assertIn("photograph", prompt.lower())
        self.assertIn("Wedding Invitations", prompt)
        self.assertIn("no typography", prompt.lower())

    def test_scene_direction_varies_by_font(self):
        prompts = {
            build_scene_prompt("Sans Serif", ["Editorial Design"], f"family-{index}")
            for index in range(12)
        }
        self.assertGreaterEqual(len(prompts), 6)

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


if __name__ == "__main__":
    unittest.main()
