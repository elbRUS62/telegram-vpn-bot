"""Проверка отправки уведомлений Telegram с HTML-разметкой."""

import unittest
from unittest.mock import patch

from web.utils import telegram


class FakeResponse:
    status_code = 200
    text = ""


class TelegramNotifyTest(unittest.TestCase):
    @patch.object(telegram, "BOT_TOKEN", "test-token")
    @patch.object(telegram.httpx, "post", return_value=FakeResponse())
    def test_html_parse_mode_is_forwarded(self, post):
        self.assertTrue(telegram._send(1, "<b>Тест</b>", "HTML"))
        payload = post.call_args.kwargs["json"]
        self.assertEqual(payload["parse_mode"], "HTML")

    @patch.object(telegram, "BOT_TOKEN", "test-token")
    @patch.object(telegram.httpx, "post", return_value=FakeResponse())
    def test_plain_text_has_no_parse_mode(self, post):
        self.assertTrue(telegram._send(1, "Тест"))
        payload = post.call_args.kwargs["json"]
        self.assertNotIn("parse_mode", payload)


if __name__ == "__main__":
    unittest.main()
