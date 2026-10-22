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


if __name__ == "__main__":
    unittest.main()
