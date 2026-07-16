import unittest

from fastapi import HTTPException

from app.routers.blog_admin import publish_blog_post


class LegacyBlogAdminTests(unittest.TestCase):
    def test_legacy_direct_publish_route_is_disabled(self):
        with self.assertRaises(HTTPException) as raised:
            publish_blog_post("unsafe-bypass", _=True)
        self.assertEqual(raised.exception.status_code, 410)
        self.assertIn("Writer bot", raised.exception.detail)


if __name__ == "__main__":
    unittest.main()
