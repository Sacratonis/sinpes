import unittest
from unittest.mock import MagicMock

from app.services.queue_manager import (
    build_font_object_key,
    resolve_variant_weight,
    select_primary_variant_url,
)


class FontObjectKeyTests(unittest.TestCase):
    def test_same_weight_contrast_variants_have_distinct_keys(self):
        hc = build_font_object_key("thunder", "/tmp/Thunder-BoldHC.ttf", 700, "normal")
        lc = build_font_object_key("thunder", "/tmp/Thunder-BoldLC.ttf", 700, "normal")

        self.assertNotEqual(hc, lc)
        self.assertEqual(hc, "fonts/thunder-700-normal-boldhc.woff2")
        self.assertEqual(lc, "fonts/thunder-700-normal-boldlc.woff2")

    def test_explicit_bold_subfamily_repairs_incorrect_regular_weight(self):
        font = MagicMock()
        font.__contains__.side_effect = lambda key: key in {"OS/2", "name"}
        font.__getitem__.side_effect = lambda key: {
            "OS/2": MagicMock(usWeightClass=400),
            "name": MagicMock(
                getDebugName=lambda name_id: "Bold" if name_id == 17 else None
            ),
        }[key]

        self.assertEqual(resolve_variant_weight(font, "/tmp/Example-Bold.ttf"), 700)

    def test_regular_face_is_selected_for_legacy_preview_url(self):
        variants = [
            {"weight": 900, "style": "normal", "url": "black", "filename": "Family-Black.ttf"},
            {"weight": 400, "style": "italic", "url": "italic", "filename": "Family-Italic.ttf"},
            {"weight": 400, "style": "normal", "url": "regular", "filename": "Family-Regular.ttf"},
        ]

        self.assertEqual(select_primary_variant_url(variants), "regular")


if __name__ == "__main__":
    unittest.main()
