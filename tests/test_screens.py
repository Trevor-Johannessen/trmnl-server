"""House > Minecraft > Listening > Now, and the gating that makes that ordering mean
anything. An ungated House would win every time and the rest would never show."""
import unittest
from datetime import datetime

from trmnl_server.screens import SCREENS, Context, House, Listening, Minecraft, Now, select
from trmnl_server.sources import Reading
from trmnl_server.windows.listening import track_length
from trmnl_server.windows.now import Date, Weather, weather_icon


def ctx(*, health=None, spotify=None, presence=None, minecraft=None):
    return Context(
        health=Reading(ok=True, data=health) if health else Reading(ok=False),
        spotify=Reading(ok=True, data=spotify) if spotify else Reading(ok=False),
        presence=Reading(ok=True, data=presence) if presence else Reading(ok=False),
        minecraft=Reading(ok=True, data=minecraft) if minecraft else Reading(ok=False),
        weather=Reading(ok=False), calendar=Reading(ok=False))


PROBLEM = {"status": "crit", "crit": 1, "warn": 0,
           "findings": [{"severity": "crit", "machine": "deploy1",
                         "component": "unit", "message": "failed"}]}
PLAYING = {"playing": True, "title": "T", "artists": "A", "album": "B",
           "duration_ms": 214000}


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

    def test_minecraft_needs_an_online_player(self):
        self.assertFalse(Minecraft().eligible(ctx(minecraft={"count": 0, "online": []})))
        self.assertTrue(Minecraft().eligible(ctx(minecraft={"count": 1, "online": ["Alex"]})))

    def test_minecraft_is_not_eligible_when_source_is_unavailable(self):
        self.assertFalse(Minecraft().eligible(ctx()))


class Selection(unittest.TestCase):
    def test_morning_outranks_now_inside_its_window(self):
        context = ctx()
        context.now = datetime(2026, 11, 17, 8, 0)
        self.assertEqual(select(context).name, "morning")

    def test_now_outside_the_morning_window(self):
        context = ctx()
        context.now = datetime(2026, 11, 17, 13, 0)
        self.assertEqual(select(context).name, "now")

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
                         ["morning", "now"])


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

    def test_listening_emphasizes_time_and_album(self):
        context = ctx(spotify=PLAYING)
        context.now = datetime(2026, 9, 12, 9, 5)
        html = Listening().body(context)
        self.assertIn('class="listen-time">9:05 am</div>', html)
        self.assertIn('class="album-name clip">B</div>', html)
        self.assertIn('class="track-duration">3:34</span>', html)
        self.assertLess(html.index('class="track-duration"'),
                        html.index('class="album-name clip"'))

    def test_track_length_handles_missing_or_invalid_duration(self):
        self.assertEqual(track_length(214000), "3:34")
        self.assertEqual(track_length(None), "")
        self.assertEqual(track_length("not a duration"), "")

    def test_weather_uses_condition_symbols(self):
        self.assertEqual(weather_icon("Sunny"), "☀")
        self.assertEqual(weather_icon("Mostly cloudy"), "☁")
        self.assertEqual(weather_icon("Rain showers"), "☂")
        self.assertEqual(weather_icon("Snow"), "❄")
        html = Weather(Reading(ok=True, data={"temp": "72°", "text": "Sunny"})).render()
        self.assertIn('class="weather-icon"', html)
        self.assertIn("☀", html)

    def test_now_shows_the_date_without_the_time(self):
        html = Date(datetime(2026, 9, 12, 9, 5)).render()
        self.assertIn('class="now-day">Saturday</span>', html)
        self.assertIn('class="now-date">12 September</span>', html)
        self.assertNotIn("9:05", html)

    def test_now_stacks_content_in_priority_order(self):
        context = ctx()
        context.weather = Reading(ok=True, data={"temp": "72°", "text": "Sunny"})
        html = Now().body(context)
        self.assertLess(html.index('now-clock-panel'), html.index('now-weather-panel'))
        self.assertLess(html.index('now-weather-panel'), html.index('now-calendar-panel'))
