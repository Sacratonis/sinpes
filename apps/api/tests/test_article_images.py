import io
import unittest
from unittest.mock import patch

from PIL import Image

from app.services.article_image_service import compose_article_image, finalize_article_image, select_featured_fonts


class ArticleImageTests(unittest.TestCase):
    def test_five_plus_fonts_follow_first_body_appearance(self):
        fonts = [{"slug": slug} for slug in ("a", "b", "c", "d", "e")]
        body = '<a href="/font/e/">E</a><a href="/font/c/">C</a><a href="/font/a/">A</a><a href="/font/d/">D</a>'
        self.assertEqual([f["slug"] for f in select_featured_fonts(body, fonts)], ["e", "c", "a", "d"])

    @patch("app.services.article_image_service._download_image")
    def test_three_font_composite_is_1200_by_630(self, download):
        download.return_value = Image.new("RGB", (800, 400), "red")
        data = compose_article_image([
            {"slug": "a", "seo_image_url": "a"},
            {"slug": "b", "seo_image_url": "b"},
            {"slug": "c", "seo_image_url": "c"},
        ])
        self.assertEqual(Image.open(io.BytesIO(data)).size, (1200, 630))

    @patch("app.services.article_image_service.upload_to_r2")
    def test_final_image_contains_xmp_and_article_path(self, upload):
        captured = {}
        def save(**kwargs):
            captured.update(kwargs)
            return "https://example.test/article.webp"
        upload.side_effect = save
        raw = io.BytesIO()
        Image.new("RGB", (500, 500), "blue").save(raw, "JPEG")
        url = finalize_article_image(
            raw.getvalue(), "sample-article", "Sample Article", "ui typography",
            ["font pairing"], "Two typography examples",
        )
        image = Image.open(io.BytesIO(captured["data"]))
        xmp = image.info.get("xmp", b"")
        self.assertEqual(url, "https://example.test/article.webp")
        self.assertEqual(image.size, (1200, 630))
        self.assertIn("articles/sample-article/", captured["key"])
        self.assertIn(b"ui typography", xmp)
        self.assertIn(b"dc:rights", xmp)


if __name__ == "__main__":
    unittest.main()
