"""The refresh-rate policy is the whole point of wiring presence in, so it gets
a table test rather than a spot check."""
import unittest
from datetime import datetime

from trmnl_server.config import Config
from trmnl_server.refresh import night, refresh_rate
from trmnl_server.sources import Reading


class Night(unittest.TestCase):
    def test_window_wraps_midnight(self):
        for hour in (23, 0, 3, 5):
            self.assertTrue(night(hour, 23, 6), hour)
        for hour in (6, 12, 22):
            self.assertFalse(night(hour, 23, 6), hour)

    def test_window_without_wrap(self):
        self.assertTrue(night(2, 1, 5))
        self.assertFalse(night(5, 1, 5))
        self.assertFalse(night(0, 1, 5))

    def test_empty_window_is_never_night(self):
        self.assertFalse(night(3, 0, 0))


class RefreshRate(unittest.TestCase):
    def setUp(self):
        self.config = Config()

    def rate(self, state, hour):
        reading = Reading(ok=True, data={"state": state}) if state else Reading(ok=False)
        return refresh_rate(self.config, reading, datetime(2026, 9, 12, hour, 0))

    def test_present_is_fast(self):
        self.assertEqual(self.rate("present", 13), self.config.refresh_present_s)

    def test_presence_outranks_the_clock(self):
        """Being in the room at midnight is a reason to keep the screen current."""
        self.assertEqual(self.rate("present", 2), self.config.refresh_present_s)

    def test_absent_is_slow(self):
        self.assertEqual(self.rate("absent", 13), self.config.refresh_absent_s)

    def test_absent_overnight_is_slowest(self):
        self.assertEqual(self.rate("absent", 2), self.config.refresh_night_s)

    def test_camera_down_is_neither(self):
        self.assertEqual(self.rate("unknown", 13), self.config.refresh_unknown_s)

    def test_presence_unavailable_falls_back(self):
        self.assertEqual(self.rate(None, 13), self.config.refresh_unknown_s)
