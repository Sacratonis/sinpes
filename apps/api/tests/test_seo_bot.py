from datetime import datetime, timezone
import unittest

from app.services.seo_bot import seconds_until_weekly_report


class SeoBotScheduleTests(unittest.TestCase):
    def test_weekly_report_uses_next_configured_utc_slot(self):
        now = datetime(2026, 7, 16, 12, 30, tzinfo=timezone.utc)  # Thursday

        delay = seconds_until_weekly_report(now, weekday_utc=0, hour_utc=9)

        self.assertEqual(delay, 3 * 24 * 60 * 60 + 20 * 60 * 60 + 30 * 60)

    def test_weekly_report_moves_to_next_week_after_slot_passes(self):
        now = datetime(2026, 7, 13, 10, 0, tzinfo=timezone.utc)  # Monday

        delay = seconds_until_weekly_report(now, weekday_utc=0, hour_utc=9)

        self.assertEqual(delay, 6 * 24 * 60 * 60 + 23 * 60 * 60)


if __name__ == "__main__":
    unittest.main()
