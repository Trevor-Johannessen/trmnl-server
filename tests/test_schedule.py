"""The morning schedule, and the edges the panel holds each screen until."""
import unittest
from datetime import datetime

from trmnl_server import schedule
from trmnl_server.config import Config
from trmnl_server.refresh import refresh_rate
from trmnl_server.sources import Reading

# 2026-11-16 is a Monday.


def at(day_offset, hour, minute=0):
    return datetime(2026, 11, 16 + day_offset, hour, minute)


class Windows(unittest.TestCase):
    def test_monday_window_is_six_to_noon(self):
        self.assertFalse(schedule.active(at(0, 5, 59)))
        self.assertTrue(schedule.active(at(0, 6, 0)))
        self.assertTrue(schedule.active(at(0, 11, 59)))
        self.assertFalse(schedule.active(at(0, 12, 0)))

    def test_tuesday_to_sunday_window_is_five_to_noon(self):
        for offset in range(1, 7):
            self.assertFalse(schedule.active(at(offset, 4, 59)), offset)
            self.assertTrue(schedule.active(at(offset, 5, 0)), offset)
            self.assertFalse(schedule.active(at(offset, 12, 0)), offset)

    def test_weekend_is_date_and_high(self):
        self.assertTrue(schedule.weekend(at(5, 9)))
        self.assertTrue(schedule.weekend(at(6, 9)))
        self.assertFalse(schedule.weekend(at(0, 9)))


class Boundary(unittest.TestCase):
    def test_next_boundary_is_strictly_after_now(self):
        self.assertEqual(schedule.next_boundary(at(1, 4, 0)), at(1, 5, 0))
        self.assertEqual(schedule.next_boundary(at(1, 5, 0)), at(1, 12, 0))
        self.assertEqual(schedule.next_boundary(at(1, 12, 0)), at(2, 0, 0))
        self.assertEqual(schedule.next_boundary(at(1, 23, 30)), at(2, 0, 0))


class RefreshEdge(unittest.TestCase):
    def setUp(self):
        self.config = Config()

    def test_sleep_stops_at_the_next_edge(self):
        rate = refresh_rate(self.config, Reading(ok=False), at(1, 4, 50))
        self.assertEqual(rate, 60 * 10 + 5)

    def test_edge_inside_a_minute_still_polls_at_the_floor(self):
        rate = refresh_rate(self.config, Reading(ok=False), datetime(2026, 11, 17, 4, 59, 30))
        self.assertEqual(rate, 60)


if __name__ == "__main__":
    unittest.main()
