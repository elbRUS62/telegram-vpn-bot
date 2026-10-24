import hashlib
import unittest

from xui_client import XUIClient


class FakeXUI(XUIClient):
    def __init__(self, client=None):
        self.panel = {"id": "test"}
        self.existing = client
        self.added = []
        self.updated = []
        self.tg_updates = []

    async def get_client(self, email):
        if self.existing is None:
            raise Exception("not found")
        return dict(self.existing)

    async def add_client(self, email, **kwargs):
        self.added.append((email, kwargs))
        return "new-sub-id"

    async def update_tg_id(self, email, tg_id):
        self.tg_updates.append((email, tg_id))
        return True

    async def _post(self, path, data=None):
        self.updated.append((path, data))
        return {"success": True}


class GetOrCreateClientTest(unittest.IsolatedAsyncioTestCase):
    async def test_reuses_existing_client(self):
        xui = FakeXUI({"subId": "existing-id", "enable": True})
        sub_id = await xui.get_or_create_client("elb62", tg_id=123)
        self.assertEqual(sub_id, "existing-id")
        self.assertEqual(xui.added, [])
        self.assertEqual(xui.tg_updates, [("elb62", 123)])

    async def test_creates_missing_client(self):
        xui = FakeXUI(None)
        sub_id = await xui.get_or_create_client("elb62", comment="test", tg_id=123)
        self.assertEqual(sub_id, "new-sub-id")
        self.assertEqual(len(xui.added), 1)
        self.assertEqual(xui.added[0][0], "elb62")

    async def test_restores_missing_sub_id(self):
        xui = FakeXUI({"subId": "", "enable": True})
        expected = hashlib.sha256("elb62".encode()).hexdigest()[:16]
        sub_id = await xui.get_or_create_client("elb62")
        self.assertEqual(sub_id, expected)
        self.assertTrue(xui.updated)
        self.assertEqual(xui.updated[0][1]["subId"], expected)
        self.assertEqual(xui.added, [])


if __name__ == "__main__":
    unittest.main()
