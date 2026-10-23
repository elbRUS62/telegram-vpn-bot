import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class MiniAppAssetsTest(unittest.TestCase):
    def test_static_assets_exist(self):
        self.assertTrue((ROOT / "web" / "static" / "miniapp.css").is_file())
        self.assertTrue((ROOT / "web" / "static" / "miniapp.js").is_file())

    def test_template_uses_external_assets(self):
        template = (ROOT / "web" / "templates" / "miniapp.html").read_text(encoding="utf-8")
        self.assertIn("/static/miniapp.css", template)
        self.assertIn("/static/miniapp.js", template)
        self.assertNotIn("<style>", template)

    def test_app_improvements_are_present(self):
        js = (ROOT / "web" / "static" / "miniapp.js").read_text(encoding="utf-8")
        css = (ROOT / "web" / "static" / "miniapp.css").read_text(encoding="utf-8")
        html = (ROOT / "web" / "templates" / "miniapp.html").read_text(encoding="utf-8")
        for token in (
            "skeletonHtml",
            "initPullToRefresh",
            "loadServerStatus",
            "downloadAdminCsv",
            "admin-bulk-bar",
            "ticket-quick-replies",
            "loadAdminErrors",
        ):
            self.assertIn(token, js)
        for token in ("skeleton-line", "onboarding-card", "server-status-card", "admin-error-log"):
            self.assertIn(token, css)
        self.assertIn("pull-indicator", html)

    def test_guest_subscription_quick_action(self):
        script = (ROOT / "web" / "static" / "miniapp.js").read_text(
            encoding="utf-8"
        )
        self.assertIn("label: 'Гостевая подписка'", script)
        self.assertIn("meta: 'Работает без Telegram'", script)

    def test_brand_assets_exist(self):
        static = ROOT / "web" / "static"
        for name in (
            "favicon.ico",
            "favicon.svg",
            "apple-touch-icon.png",
            "icon-192.png",
            "icon-512.png",
            "site.webmanifest",
        ):
            self.assertTrue((static / name).is_file(), name)

    def test_templates_reference_brand_icons(self):
        templates = ROOT / "web" / "templates"
        for name in ("docs.html", "error.html", "invite.html", "miniapp.html"):
            text = (templates / name).read_text(encoding="utf-8")
            self.assertIn("/static/favicon.ico", text, name)
            self.assertIn("/static/apple-touch-icon.png", text, name)


if __name__ == "__main__":
    unittest.main()
