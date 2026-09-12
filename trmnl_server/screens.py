"""Which screen the panel is showing, and why.

A priority stack, not a rotation: every screen says whether it is eligible
right now, and the highest-priority eligible one wins. House outranks
Listening outranks Now.

House is gated on there being something to say. An ungated House would always
win and the other two would never appear -- the ordering is only meaningful
because the top of it is conditional. Now is the floor and is always eligible,
so there is always exactly one answer.
"""
from dataclasses import dataclass, field
from datetime import datetime

from .config import HEIGHT
from .layout import Zone, esc
from .windows import house as house_windows
from .windows import listening as listening_windows
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


def frame(title: str, right: str, body: str) -> str:
    return (
        f'<div class="head"><div class="caps">{esc(title)}</div>'
        f'<div class="caps">{right}</div></div>'
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


class Listening(Screen):
    """Music is actually moving through the speakers."""
    name = "listening"
    priority = 2
    title = "Listening"

    def eligible(self, ctx):
        return bool(ctx.spotify and ctx.spotify.ok and ctx.spotify.get("playing"))

    def body(self, ctx):
        zone = Zone(
            direction="row", percentage=44,
            zone_one=Zone(window=listening_windows.Cover(ctx.art_uri)),
            zone_two=Zone(window=listening_windows.Track(ctx.spotify.data)))
        return frame(self.title, esc(ctx.now.strftime("%-I:%M %p").lower()), zone.render())


class Now(Screen):
    """The floor. Always eligible, so selection always has an answer."""
    name = "now"
    priority = 3
    title = "Now"

    def eligible(self, ctx):
        return True

    def _presence_badge(self, ctx):
        if not (ctx.presence and ctx.presence.ok):
            return ""
        state = ctx.presence.get("state")
        if state == "present":
            minutes = int((ctx.presence.get("duration_s") or 0) // 60)
            return f'<span class="badge">in the room {minutes}m</span>'
        if state == "unknown":
            return '<span class="badge hollow">camera down</span>'
        return '<span class="badge hollow">empty</span>'

    def body(self, ctx):
        top = Zone(
            direction="row", percentage=52,
            zone_one=Zone(window=now_windows.Clock(ctx.now)),
            zone_two=Zone(window=now_windows.Weather(ctx.weather)))
        zone = Zone(
            direction="column", percentage=62,
            zone_one=top,
            zone_two=Zone(window=now_windows.NextEvent(ctx.calendar, ctx.now)))
        return frame(self.title, self._presence_badge(ctx), zone.render())


SCREENS = [House(), Listening(), Now()]


def select(ctx: Context, screens=None) -> Screen:
    """Highest-priority eligible screen. Never returns None: Now is the floor."""
    for screen in sorted(screens or SCREENS, key=lambda s: s.priority):
        try:
            if screen.eligible(ctx):
                return screen
        except Exception:
            continue
    return Now()
