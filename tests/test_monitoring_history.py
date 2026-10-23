import unittest

import monitoring


class MonitoringHistoryTest(unittest.TestCase):
    def test_downsample_keeps_edges(self):
        rows = [{"ts": index, "value": index} for index in range(100)]
        sampled = monitoring._downsample_history(rows, 10)
        self.assertEqual(len(sampled), 10)
        self.assertEqual(sampled[0]["ts"], 0)
        self.assertEqual(sampled[-1]["ts"], 99)

    def test_downsample_keeps_short_history(self):
        rows = [{"ts": index} for index in range(5)]
        self.assertEqual(monitoring._downsample_history(rows, 288), rows)


if __name__ == "__main__":
    unittest.main()
