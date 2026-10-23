import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class SubscriptionTemplateTest(unittest.TestCase):
    def test_sub_template_keeps_3xui_placeholders(self):
        template = (
            ROOT / "sub_templates" / "skrepnet" / "index.html"
        ).read_text(encoding="utf-8")
        for token in (
            "{{ if not .isOnline }}",
            "{{ .used }}",
            "{{ .remained }}",
            "{{ .total }}",
            "{{ .expire }}",
            "{{ .totalByte }}",
            "{{ .usedByte }}",
        ):
            self.assertIn(token, template)

    def test_subscription_pages_share_brand_and_style(self):
        invite = (ROOT / "web" / "templates" / "invite.html").read_text(
            encoding="utf-8"
        )
        sub = (ROOT / "sub_templates" / "skrepnet" / "index.html").read_text(
            encoding="utf-8"
        )
        for text in (invite, sub):
            self.assertIn("brand-logo", text)
            self.assertIn("main-bg-dot", text)
            self.assertIn("--button-color", text)

    def test_guest_page_explains_bot_renewal(self):
        invite = (ROOT / "web" / "templates" / "invite.html").read_text(
            encoding="utf-8"
        )
        self.assertIn("https://t.me/{{ bot_username }}", invite)
        self.assertIn("Гостевая подписка на 3 дня", invite)
        self.assertIn("Перейти в бота", invite)


if __name__ == "__main__":
    unittest.main()
