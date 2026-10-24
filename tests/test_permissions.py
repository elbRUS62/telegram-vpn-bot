import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import permissions


class PermissionsTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = str(Path(self.temp_dir.name) / "test.db")
        connection = sqlite3.connect(self.db_path)
        connection.execute(
            "CREATE TABLE users (telegram_id INTEGER PRIMARY KEY, username TEXT, first_name TEXT)"
        )
        connection.commit()
        connection.close()

        self.patches = [
            patch.object(permissions, "DB_PATH", self.db_path),
            patch.object(permissions, "ADMIN_IDS", [1, 2]),
            patch.object(permissions, "SUPERADMIN_IDS", [1]),
        ]
        for item in self.patches:
            item.start()
        permissions._SCHEMA_READY = False
        permissions.seed_admins()

    def tearDown(self):
        for item in reversed(self.patches):
            item.stop()
        permissions._SCHEMA_READY = False
        self.temp_dir.cleanup()

    def test_seed_and_roles(self):
        self.assertTrue(permissions.is_superadmin(1))
        self.assertTrue(permissions.is_admin_user(1))
        self.assertFalse(permissions.is_superadmin(2))
        self.assertTrue(permissions.is_admin_user(2))
        self.assertFalse(permissions.is_admin_user(3))

    def test_add_promote_and_remove(self):
        permissions.save_admin(3, username="new", first_name="New")
        self.assertTrue(permissions.is_admin_user(3))
        self.assertEqual(permissions.get_admin_role(3), "admin")

        permissions.set_admin_role(3, "superadmin")
        self.assertTrue(permissions.is_superadmin(3))

        permissions.deactivate_admin(3)
        self.assertFalse(permissions.is_admin_user(3))

    def test_environment_superadmin_cannot_be_removed(self):
        with self.assertRaises(ValueError):
            permissions.deactivate_admin(1)
        with self.assertRaises(ValueError):
            permissions.set_admin_role(1, "admin")

    def test_admin_error_exposes_only_safe_code(self):
        with self.assertRaises(permissions.AdminActionError) as ctx:
            permissions.deactivate_admin(1)
        self.assertEqual(ctx.exception.code, "env_superadmin_remove")
        self.assertIn(ctx.exception.code, permissions.ADMIN_ERROR_MESSAGES)

    def test_cannot_remove_last_superadmin(self):
        permissions.deactivate_admin(2)
        with self.assertRaises(ValueError):
            permissions.deactivate_admin(1)

    def test_list_admins(self):
        admins = permissions.list_admins()
        self.assertEqual(len(admins), 2)
        self.assertEqual(admins[0]["role"], "superadmin")
        self.assertEqual(admins[1]["role"], "admin")


if __name__ == "__main__":
    unittest.main()
