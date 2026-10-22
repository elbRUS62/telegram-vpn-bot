import unittest

from web_app import app


MINIAPP_ENDPOINTS = (
    "/api/miniapp/main",
    "/api/miniapp/subscription",
    "/api/miniapp/diagnostics",
    "/api/miniapp/renew",
    "/api/miniapp/referral",
    "/api/miniapp/donate",
    "/api/miniapp/profile",
    "/api/miniapp/devices",
    "/api/miniapp/connect",
    "/api/miniapp/connect/<platform>",
    "/api/miniapp/invoice",
    "/api/miniapp/create_invite_link",
    "/api/miniapp/accept_terms",
)


class MiniAppApiRoutesTest(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()

    def test_miniapp_routes_are_registered(self):
        rules = {rule.rule for rule in app.url_map.iter_rules()}
        missing = [path for path in MINIAPP_ENDPOINTS if path not in rules]
        self.assertEqual(missing, [], f"Не зарегистрированы маршруты: {missing}")

    def test_connect_platforms_available_without_auth(self):
        response = self.client.post("/api/miniapp/connect", json={})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json.get("platforms", [])), 6)

    def test_protected_miniapp_routes_require_auth(self):
        protected = (
            "/api/miniapp/main",
            "/api/miniapp/subscription",
            "/api/miniapp/diagnostics",
            "/api/miniapp/referral",
            "/api/miniapp/donate",
            "/api/miniapp/profile",
            "/api/miniapp/devices",
            "/api/miniapp/create_invite_link",
            "/api/miniapp/accept_terms",
        )
        for path in protected:
            with self.subTest(path=path):
                response = self.client.post(path, json={})
                self.assertEqual(response.status_code, 401)


if __name__ == "__main__":
    unittest.main()
