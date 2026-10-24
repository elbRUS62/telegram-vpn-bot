import unittest

from web.routes.api.admin.common import clean_reason


class CleanReasonTest(unittest.TestCase):
    def test_empty_values(self):
        self.assertEqual(clean_reason(None), "")
        self.assertEqual(clean_reason(""), "")
        self.assertEqual(clean_reason("   "), "")

    def test_collapses_whitespace(self):
        self.assertEqual(clean_reason("  Неоплата \n\t счёта  "), "Неоплата счёта")

    def test_truncates_long_text(self):
        self.assertEqual(len(clean_reason("x" * 500)), 200)

    def test_converts_non_string(self):
        self.assertEqual(clean_reason(12345), "12345")


if __name__ == "__main__":
    unittest.main()
