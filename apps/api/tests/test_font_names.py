import unittest

from app.ingestion.font_converter import normalize_display_name
from app.ingestion.bot_listener import get_family_root


class FontNameTests(unittest.TestCase):
    def test_removes_technical_glyph_grid_suffix(self):
        self.assertEqual(normalize_display_name("BUSE letters 16х8", "buse"), "BUSE")

    def test_removes_style_suffix(self):
        self.assertEqual(normalize_display_name("Example Sans Regular", "example-sans"), "Example Sans")

    def test_removes_concatenated_foundry_credit_and_style(self):
        self.assertEqual(
            normalize_display_name("VandalizmByAlbumArtArchive-Regular", "vandalizm"),
            "Vandalizm",
        )

    def test_removes_spaced_foundry_credit(self):
        self.assertEqual(
            normalize_display_name("Vandalizm By Album Art Archive", "vandalizm"),
            "Vandalizm",
        )

    def test_preserves_name_with_by_as_part_of_title(self):
        self.assertEqual(normalize_display_name("Stand By Me", "stand-by-me"), "Stand By Me")

    def test_removes_personal_use_label_without_rejecting_family(self):
        self.assertEqual(
            normalize_display_name("Bright Melody Personal Use Only", "bright-melody"),
            "Bright Melody",
        )
        self.assertEqual(
            normalize_display_name("Gigxa Free Personal Use", "gigxa"),
            "Gigxa",
        )

    def test_removes_trial_and_demo_labels(self):
        self.assertEqual(normalize_display_name("KTF Rublena Trial", "ktf-rublena"), "KTF Rublena")
        self.assertEqual(normalize_display_name("Example Demo", "example"), "Example")

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
