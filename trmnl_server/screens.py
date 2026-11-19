"""Which screen the panel is showing, and why.

A priority stack, not a rotation: every screen says whether it is eligible
right now, and the highest-priority eligible one wins. House outranks
Minecraft, which outranks Listening, which outranks Now.

House is gated on there being something to say. An ungated House would always
win and the other two would never appear -- the ordering is only meaningful
because the top of it is conditional. Now is the floor and is always eligible,
so there is always exactly one answer.
"""
from dataclasses import dataclass, field
from datetime import datetime

from . import schedule
from .config import HEIGHT
from .layout import Zone, esc
from .windows import house as house_windows
from .windows import listening as listening_windows
from .windows import minecraft as minecraft_windows
from .windows import morning as morning_windows
from .windows import now as now_windows

HEAD_PX = 44
BODY_PX = HEIGHT - HEAD_PX


@dataclass
class Context:
    """One snapshot of the world, gathered once per compose."""
    presence: object = None
    spotify: object = None
    health: object = None
    minecraft: object = None
    weather: object = None
    calendar: object = None
    art_uri: str | None = None
    now: datetime = field(default_factory=datetime.now)


def frame(title: str, right: str | None, body: str) -> str:
    right_html = f'<div class="caps">{right}</div>' if right else ""
    return (
        f'<div class="head"><div class="caps">{esc(title)}</div>{right_html}</div>'
        f'<div style="height:{BODY_PX}px">{body}</div>'
    )


class Screen:
    name = "screen"
    priority = 99
    title = "Screen"

    def eligible(self, ctx: Context) -> bool:
        raise NotImplementedError

    def body(self, ctx: Context) -> str:
        raise NotImplementedError


class House(Screen):
    """Something is wrong. Only then."""
    name = "house"
    priority = 1
    title = "House"

    def eligible(self, ctx):
        return bool(ctx.health and ctx.health.ok
                    and ctx.health.get("status", "ok") != "ok"
                    and ctx.health.get("findings"))

    def body(self, ctx):
        findings = ctx.health.get("findings") or []
        crit = ctx.health.get("crit", 0)
        warn = ctx.health.get("warn", 0)
        counts = " ".join(part for part in (
            f"{crit} crit" if crit else "", f"{warn} warn" if warn else "") if part)
        zone = Zone(
            direction="column", percentage=76,
            zone_one=Zone(window=house_windows.Findings(findings)),
            zone_two=Zone(window=house_windows.Minecraft(ctx.minecraft)))
        return frame(self.title, esc(counts), zone.render())


class Minecraft(Screen):
    """Minecraft gets the panel whenever at least one player is online."""
    name = "minecraft"
    priority = 2
    title = "Minecraft"

    def eligible(self, ctx):
        if not (ctx.minecraft and ctx.minecraft.ok):
            return False
        return bool(ctx.minecraft.get("online") or ctx.minecraft.get("count", 0))

    def body(self, ctx):
        data = ctx.minecraft.data or {}
        online = data.get("online") or []
        count = data.get("count") or len(online)
        zone = Zone(
            direction="row", percentage=58,
            zone_one=Zone(window=minecraft_windows.Players(ctx.minecraft)),
            zone_two=Zone(window=minecraft_windows.Stats(ctx.minecraft)))
        right = "{} online".format(count)
        return frame(self.title, esc(right), zone.render())


class Morning(Screen):
    """The scheduled morning weather. Shown only inside its window, so it
    outranks Listening but never the House or a Minecraft game."""
    name = "morning"
    priority = 2.5
    title = "Morning"

    def eligible(self, ctx):
        return schedule.active(ctx.now)

    def body(self, ctx):
        if schedule.weekend(ctx.now):
            window = morning_windows.DateHigh(ctx.now, ctx.weather)
        else:
            window = morning_windows.Forecast(ctx.now, ctx.weather)
        zone = Zone(
            direction="column", percentage=60,
            zone_one=Zone(window=window),
            zone_two=Zone(window=morning_windows.Events(ctx.now, ctx.calendar)))
        return frame(self.title, None, zone.render())


class Listening(Screen):
    """Music is actually moving through the speakers."""
    name = "listening"
    priority = 3
    title = "Listening"

    def eligible(self, ctx):
        return bool(ctx.spotify and ctx.spotify.ok and ctx.spotify.get("playing"))

    def body(self, ctx):
        time = esc(ctx.now.strftime("%-I:%M %p").lower())
        zone = Zone(
            direction="row", percentage=44,
            zone_one=Zone(window=listening_windows.Cover(ctx.art_uri, time)),
            zone_two=Zone(window=listening_windows.Track(ctx.spotify.data)))
        return frame(self.title, None, zone.render())


class Now(Screen):
    """The floor. Always eligible, so selection always has an answer."""
    name = "now"
    priority = 4
    title = "Now"

    def eligible(self, ctx):
        return True

    def body(self, ctx):
        lower = Zone(
            direction="column", percentage=48,
            zone_one=Zone(window=now_windows.Weather(ctx.weather)),
            zone_two=Zone(window=now_windows.NextEvent(ctx.calendar, ctx.now)))
        zone = Zone(
            direction="column", percentage=30,
            zone_one=Zone(window=now_windows.Date(ctx.now)),
            zone_two=lower)
        return frame(self.title, None, zone.render())


SCREENS = [Morning(), Now()]


def select(ctx: Context, screens=None) -> Screen:
    """Highest-priority eligible screen. Never returns None: Now is the floor."""
    for screen in sorted(screens or SCREENS, key=lambda s: s.priority):
        try:
            if screen.eligible(ctx):
                return screen
        except Exception:
            continue
    return Now()
