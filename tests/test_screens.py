"""House > Listening > Now, and the gating that makes that ordering mean
anything. An ungated House would win every time and the rest would never show."""
import unittest

from trmnl_server.screens import SCREENS, Context, House, Listening, Now, select
from trmnl_server.sources import Reading


def ctx(*, health=None, spotify=None, presence=None):
    return Context(
        health=Reading(ok=True, data=health) if health else Reading(ok=False),
        spotify=Reading(ok=True, data=spotify) if spotify else Reading(ok=False),
        presence=Reading(ok=True, data=presence) if presence else Reading(ok=False),
        minecraft=Reading(ok=False), weather=Reading(ok=False), calendar=Reading(ok=False))


PROBLEM = {"status": "crit", "crit": 1, "warn": 0,
           "findings": [{"severity": "crit", "machine": "deploy1",
                         "component": "unit", "message": "failed"}]}
PLAYING = {"playing": True, "title": "T", "artists": "A", "album": "B"}


class Eligibility(unittest.TestCase):
    def test_house_needs_a_problem(self):
        self.assertFalse(House().eligible(ctx(health={"status": "ok", "findings": []})))
        self.assertTrue(House().eligible(ctx(health=PROBLEM)))

    def test_house_ignores_a_non_ok_status_with_no_findings(self):
        self.assertFalse(House().eligible(ctx(health={"status": "warn", "findings": []})))

    def test_house_not_eligible_when_health_is_unavailable(self):
        self.assertFalse(House().eligible(ctx()))

    def test_listening_follows_audio_not_the_player_event(self):
        self.assertTrue(Listening().eligible(ctx(spotify=PLAYING)))
        self.assertFalse(Listening().eligible(ctx(spotify={"playing": False, "title": "T"})))

    def test_now_is_always_eligible(self):
        self.assertTrue(Now().eligible(ctx()))


class Selection(unittest.TestCase):
    def test_house_outranks_listening(self):
        self.assertEqual(select(ctx(health=PROBLEM, spotify=PLAYING)).name, "house")

    def test_listening_outranks_now(self):
        self.assertEqual(select(ctx(spotify=PLAYING)).name, "listening")

    def test_now_is_the_floor(self):
        self.assertEqual(select(ctx()).name, "now")

    def test_quiet_lab_with_music_off_is_now(self):
        self.assertEqual(select(ctx(health={"status": "ok", "findings": []},
                                    spotify={"playing": False})).name, "now")

    def test_a_screen_that_raises_is_skipped_not_fatal(self):
        class Broken(Now):
            name, priority = "broken", 0

            def eligible(self, context):
                raise RuntimeError("boom")

        self.assertEqual(select(ctx(), [Broken(), Now()]).name, "now")

    def test_priorities_are_unique_and_ordered(self):
        priorities = [s.priority for s in SCREENS]
        self.assertEqual(len(priorities), len(set(priorities)))
        self.assertEqual([s.name for s in sorted(SCREENS, key=lambda s: s.priority)],
                         ["house", "listening", "now"])


class Rendering(unittest.TestCase):
    def test_every_screen_renders_with_nothing_available(self):
        """Every source down is the state after a restart, and it must still
        produce a screen rather than a traceback."""
        blank = ctx()
        for screen in SCREENS:
            html = screen.body(blank)
            self.assertIn("head", html)
            self.assertGreater(len(html), 100, screen.name)

    def test_content_is_escaped(self):
        hostile = dict(PROBLEM)
        hostile["findings"] = [{"severity": "crit", "machine": "<script>alert(1)</script>",
                                "component": "x", "message": "y"}]
        html = House().body(ctx(health=hostile))
        self.assertNotIn("<script>", html)
        self.assertIn("&lt;script&gt;", html)
