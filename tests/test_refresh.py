"""The panel sleeps until the next schedule edge, never by presence."""
import unittest
from datetime import datetime

from trmnl_server.config import Config
from trmnl_server.refresh import refresh_rate
from trmnl_server.sources import Reading


class RefreshRate(unittest.TestCase):
    def test_holds_until_next_morning_edge(self):
        now = datetime(2026, 11, 17, 12, 30)  # Tue, after the window closes
        self.assertEqual(refresh_rate(Config(), Reading(ok=False), now),
                         int((datetime(2026, 11, 18) - now).total_seconds()) + 5)

    def test_near_an_edge_polls_at_the_floor(self):
        now = datetime(2026, 11, 17, 4, 59, 30)
        self.assertEqual(refresh_rate(Config(), Reading(ok=False), now), 60)


if __name__ == "__main__":
    unittest.main()
