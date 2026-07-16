import unittest

from app.services.writer_bot import approval_block_message, is_owner_private_chat


class WriterBotAuthorizationTests(unittest.TestCase):
    def test_batch_publish_owner_check_requires_matching_private_chat(self):
        self.assertTrue(is_owner_private_chat(123, 123, True, "123"))
        self.assertFalse(is_owner_private_chat(999, 999, True, "123"))
        self.assertFalse(is_owner_private_chat(123, -1004316645029, False, "123"))
        self.assertFalse(is_owner_private_chat(123, 123, True, None))

    def test_approval_failure_message_preserves_deterministic_reason(self):
        message = approval_block_message(ValueError("Font links must exactly match referenced_font_slugs"))
        self.assertIn("deterministic validation", message)
        self.assertIn("Font links must exactly match referenced_font_slugs", message)


if __name__ == "__main__":
    unittest.main()
