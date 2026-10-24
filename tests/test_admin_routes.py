import unittest

from web_app import app


ADMIN_ENDPOINTS = (
    "/api/miniapp/admin/xui",
    "/api/miniapp/admin/monitor",
    "/api/miniapp/admin/stats",
    "/api/miniapp/admin/sync",
    "/api/miniapp/admin/reconcile",
    "/api/miniapp/admin/reconcile/status",
    "/api/miniapp/admin/users",
    "/api/miniapp/admin/users/export",
    "/api/miniapp/admin/users/bulk",
    "/api/miniapp/admin/user",
    "/api/miniapp/admin/diagnostics",
    "/api/miniapp/admin/errors",
    "/api/miniapp/admin/requests",
    "/api/miniapp/admin/approve",
    "/api/miniapp/admin/reject",
    "/api/miniapp/admin/extend",
    "/api/miniapp/admin/delete",
    "/api/miniapp/admin/block",
    "/api/miniapp/admin/unblock",
    "/api/miniapp/admin/comment",
    "/api/miniapp/admin/broadcast",
    "/api/miniapp/admin/audit",
    "/api/miniapp/admin/tickets",
    "/api/miniapp/admin/tickets/export",
    "/api/miniapp/admin/ticket",
    "/api/miniapp/admin/ticket/reply",
    "/api/miniapp/admin/ticket/close",
    "/api/miniapp/admin/admins",
    "/api/miniapp/admin/admins/add",
    "/api/miniapp/admin/admins/role",
    "/api/miniapp/admin/admins/remove",
)


class AdminRoutesTest(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()

    def test_admin_routes_are_registered(self):
        rules = {rule.rule for rule in app.url_map.iter_rules()}
        missing = [path for path in ADMIN_ENDPOINTS if path not in rules]
        self.assertEqual(missing, [], f"Не зарегистрированы маршруты: {missing}")

    def test_admin_routes_require_auth(self):
        for path in ADMIN_ENDPOINTS:
            with self.subTest(path=path):
                response = self.client.post(path, json={})
                self.assertIn(response.status_code, (401, 403))


if __name__ == "__main__":
    unittest.main()
