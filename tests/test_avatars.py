import unittest

from web.utils.avatars import get_avatar_data_url


class AvatarTest(unittest.TestCase):
    def test_zero_id_has_no_avatar(self):
        self.assertEqual(get_avatar_data_url(0), "")

    def test_missing_avatar_returns_empty(self):
        self.assertEqual(get_avatar_data_url(999999999999), "")


if __name__ == "__main__":
    unittest.main()
