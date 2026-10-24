import sqlite3
import unittest

from web.routes.api.admin.admins import _user_profile


class UserProfileTest(unittest.TestCase):
    def _row(self):
        connection = sqlite3.connect(":memory:")
        connection.row_factory = sqlite3.Row
        row = connection.execute(
            "SELECT 'elb62' AS username, 'Александр' AS first_name"
        ).fetchone()
        connection.close()
        return row

    def test_sqlite_row(self):
        self.assertEqual(
            _user_profile(self._row()),
            {"username": "elb62", "first_name": "Александр"},
        )

    def test_plain_dict(self):
        self.assertEqual(
            _user_profile({"username": None, "first_name": "Имя"}),
            {"username": "", "first_name": "Имя"},
        )

    def test_missing_user(self):
        self.assertIsNone(_user_profile(None))


if __name__ == "__main__":
    unittest.main()
