import unittest
from unittest.mock import AsyncMock, patch

from web_app import app
import web.routes.api.admin.common as admin_common
import web.routes.api.diagnostics as diagnostics_module


class AdminDiagnosticsTest(unittest.TestCase):
    def test_diagnostics_returns_json(self):
        fake = {
            "panel_name": "RU",
            "panel_ok": True,
            "client_found": True,
            "enabled": True,
            "is_online": True,
            "sub_link_ok": True,
            "sub_http_status": 200,
            "checked_at": "12:00",
        }
        with app.test_client() as client:
            with patch.object(admin_common, "validate_init_data", return_value={"id": 1}), \
                 patch.object(admin_common, "is_admin_user", return_value=True), \
                 patch.object(admin_common, "is_superadmin", return_value=True), \
                 patch.object(
                     diagnostics_module,
                     "_collect_diagnostics",
                     new=AsyncMock(return_value=fake),
                 ):
                response = client.post(
                    "/api/miniapp/admin/diagnostics",
                    json={"init_data": "test", "tg_id": 123},
                )
                self.assertEqual(response.status_code, 200)
                self.assertTrue(response.is_json)
                self.assertEqual(response.json["panel_name"], "RU")


if __name__ == "__main__":
    unittest.main()
