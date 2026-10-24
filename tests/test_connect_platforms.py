import unittest

from web.routes.api.connect import PLATFORMS_INFO


class ConnectPlatformsTest(unittest.TestCase):
    def test_required_fields(self):
        for key, info in PLATFORMS_INFO.items():
            with self.subTest(platform=key):
                self.assertTrue(info.get('title'))
                self.assertTrue(info.get('app'))
                self.assertTrue(info.get('app_url', '').startswith('https://'))
                self.assertGreaterEqual(len(info.get('steps') or []), 3)
                self.assertGreaterEqual(len(info.get('troubleshooting') or []), 3)

    def test_happ_links(self):
        self.assertIn('play.google.com', PLATFORMS_INFO['android']['app_url'])
        self.assertIn('apps.apple.com', PLATFORMS_INFO['ios']['app_url'])
        self.assertIn('happ.su', PLATFORMS_INFO['windows']['app_url'])

    def test_troubleshooting_mentions_server_choice(self):
        for key, info in PLATFORMS_INFO.items():
            with self.subTest(platform=key):
                text = ' '.join(info.get('troubleshooting') or [])
                self.assertIn('сервер', text.lower())


if __name__ == '__main__':
    unittest.main()
