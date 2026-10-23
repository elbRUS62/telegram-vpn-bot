import time
import unittest
from unittest.mock import AsyncMock, patch

from config import XUI_PANELS
from web_app import app
import web.routes.health as health_module


class HealthTest(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()
        self.panel_id = XUI_PANELS[0]["id"] if XUI_PANELS else "panel"

    def test_health_ok(self):
        now = int(time.time())

        async def fake_state(key, default=None):
            if key == "bot:heartbeat":
                return str(now)
            if key.endswith(":last_check"):
                return str(now)
            if key.endswith(":last_ok"):
                return "1"
            return default

        with patch.object(
            health_module,
            "get_state_value",
            new=AsyncMock(side_effect=fake_state),
        ):
            response = self.client.get("/health")
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json["status"], "ok")
            self.assertTrue(response.json["db"]["ok"])
            self.assertTrue(response.json["bot"]["ok"])
            self.assertTrue(all(panel["ok"] for panel in response.json["panels"]))

    def test_health_degraded_without_heartbeat(self):
        async def fake_state(key, default=None):
            if key.endswith(":last_check"):
                return str(int(time.time()))
            if key.endswith(":last_ok"):
                return "1"
            return default

        with patch.object(
            health_module,
            "get_state_value",
            new=AsyncMock(side_effect=fake_state),
        ):
            response = self.client.get("/health")
            self.assertEqual(response.status_code, 503)
            self.assertEqual(response.json["status"], "degraded")
            self.assertFalse(response.json["bot"]["ok"])


if __name__ == "__main__":
    unittest.main()
