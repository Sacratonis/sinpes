import unittest

from app.ingestion.font_converter import normalize_display_name
from app.ingestion.bot_listener import get_family_root


class FontNameTests(unittest.TestCase):
    def test_removes_technical_glyph_grid_suffix(self):
        self.assertEqual(normalize_display_name("BUSE letters 16х8", "buse"), "BUSE")

    def test_removes_style_suffix(self):
        self.assertEqual(normalize_display_name("Example Sans Regular", "example-sans"), "Example Sans")

    def test_uses_slug_for_untitled_font(self):
        self.assertEqual(normalize_display_name("Untitled", "clean-family"), "Clean Family")

    def test_preserves_professional_brand_casing(self):
        self.assertEqual(normalize_display_name("Miama Nueva", "miama-nueva"), "Miama Nueva")

    def test_inter_styles_share_one_family_root(self):
        self.assertEqual(get_family_root("Inter-Black.otf"), "Inter")
        self.assertEqual(get_family_root("Inter-LightItalic.otf"), "Inter")

    def test_contrast_styles_share_one_family_root(self):
        self.assertEqual(get_family_root("Thunder-BlackHC.ttf"), "Thunder")
        self.assertEqual(get_family_root("Thunder-LightLCItalic.ttf"), "Thunder")
        self.assertEqual(get_family_root("Thunder-HCItalic.ttf"), "Thunder")
        self.assertEqual(get_family_root("Thunder-SemiBoldHC.ttf"), "Thunder")


if __name__ == "__main__":
    unittest.main()
