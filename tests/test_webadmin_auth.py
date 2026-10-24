import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import web.utils.webadmin_auth as auth


class WebAdminAuthTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = str(Path(self.temp_dir.name) / "test.db")
        connection = sqlite3.connect(self.db_path)
        connection.execute("""
            CREATE TABLE admin_login_tokens (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                token_hash TEXT UNIQUE NOT NULL,
                admin_id INTEGER NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                expires_at TIMESTAMP NOT NULL,
                used_at TIMESTAMP
            )
        """)
        connection.commit()
        connection.close()
        self.patch = patch.object(auth, "DB_PATH", self.db_path)
        self.patch.start()

    def tearDown(self):
        self.patch.stop()
        self.temp_dir.cleanup()

    def test_token_is_one_time(self):
        token = auth.create_login_token(123)
        self.assertEqual(auth.consume_login_token(token), 123)
        self.assertIsNone(auth.consume_login_token(token))

    def test_unknown_token_is_rejected(self):
        self.assertIsNone(auth.consume_login_token("x" * 40))


if __name__ == "__main__":
    unittest.main()
