import unittest
from datetime import datetime, timedelta

from config import SUBSCRIPTION_DAYS, WEB_SUBSCRIPTION_DAYS
from web.utils.subscription_days import days_left_from_expiry, plan_days_for_source


class PlanDaysTest(unittest.TestCase):
    def test_web_guest_uses_short_plan(self):
        self.assertEqual(plan_days_for_source("web"), WEB_SUBSCRIPTION_DAYS)

    def test_telegram_user_uses_default_plan(self):
        self.assertEqual(plan_days_for_source("tg"), SUBSCRIPTION_DAYS)
        self.assertEqual(plan_days_for_source(None), SUBSCRIPTION_DAYS)

    def test_days_are_rounded_up(self):
        now = datetime(2026, 10, 24, 12, 0, 0)
        self.assertEqual(days_left_from_expiry(now + timedelta(days=3), now), 3)
        self.assertEqual(days_left_from_expiry(now + timedelta(days=2, hours=12), now), 3)
        self.assertEqual(days_left_from_expiry(now + timedelta(hours=1), now), 1)

    def test_expired_is_negative(self):
        now = datetime(2026, 10, 24, 12, 0, 0)
        self.assertEqual(days_left_from_expiry(now - timedelta(hours=1), now), -1)

    def test_parses_db_timestamp(self):
        now = datetime(2026, 10, 24, 12, 0, 0)
        value = (now + timedelta(days=3)).strftime("%Y-%m-%d %H:%M:%S.%f")
        self.assertEqual(days_left_from_expiry(value, now), 3)

    def test_empty_and_invalid(self):
        self.assertIsNone(days_left_from_expiry(None))
        self.assertIsNone(days_left_from_expiry(""))
        self.assertIsNone(days_left_from_expiry("not-a-date"))


if __name__ == "__main__":
    unittest.main()
