"""Windows for the Now screen -- the default, the one that is up most of the time."""
from datetime import datetime

from ..layout import Window, esc


class Clock(Window):
    """Rendered server-side, so this is deploy1's local time. The panel has no
    clock of its own and would have nothing to show otherwise."""

    def __init__(self, now=None):
        self.now = now or datetime.now()

    def render(self):
        return (
            '<div class="w"><div class="stack">'
            f'<div class="xl">{self.now.strftime("%-I:%M")}</div>'
            f'<div class="md">{esc(self.now.strftime("%p").lower())}</div>'
            '<div class="grow"></div>'
            f'<div class="sm">{esc(self.now.strftime("%A"))}</div>'
            f'<div class="md">{esc(self.now.strftime("%-d %B"))}</div>'
            "</div></div>"
        )


class Weather(Window):
    def __init__(self, reading):
        self.reading = reading

    def render(self):
        if not self.reading.ok:
            return ('<div class="w"><div class="caps">Weather</div>'
                    '<div class="empty">—</div></div>')
        data = self.reading.data
        rows = []
        if data.get("high") or data.get("low"):
            rows.append(f'<div class="sm">High {esc(data.get("high") or "—")}'
                        f' &nbsp;·&nbsp; Low {esc(data.get("low") or "—")}</div>')
        if data.get("outlook"):
            rows.append(f'<div class="xs clip">{esc(data["outlook"])}</div>')
        stale = '<span class="badge hollow">stale</span>' if self.reading.stale else ""
        return (
            '<div class="w"><div class="stack">'
            f'<div class="caps">{esc(data.get("location") or "Weather")} {stale}</div>'
            f'<div class="lg">{esc(data.get("temp") or "—")}</div>'
            f'<div class="md clip">{esc(data.get("text") or "")}</div>'
            '<div class="grow"></div>'
            + "".join(rows) +
            "</div></div>"
        )


class NextEvent(Window):
    def __init__(self, reading, now=None):
        self.reading = reading
        self.now = now or datetime.now()

    def _when(self, start, all_day):
        if start.date() == self.now.date():
            return "Today, all day" if all_day else f"Today {start.strftime('%-I:%M %p').lower()}"
        prefix = start.strftime("%a %-d %b")
        return prefix if all_day else f"{prefix}, {start.strftime('%-I:%M %p').lower()}"

    def render(self):
        events = self.reading.data.get("events") or [] if self.reading.ok else []
        if not events:
            return ('<div class="w tight"><div class="caps">Next</div>'
                    '<div class="empty">Nothing scheduled</div></div>')
        rows = []
        for index, event in enumerate(events[:2]):
            start = datetime.fromisoformat(event["start"])
            size = "lg" if index == 0 else "sm"
            rows.append(
                f'<div style="margin-top:{0 if index == 0 else 10}px">'
                f'<div class="xs">{esc(self._when(start, event["all_day"]))}</div>'
                f'<div class="{size} clip">{esc(event["summary"])}</div></div>')
        return ('<div class="w tight"><div class="caps">Next</div>'
                + "".join(rows) + "</div>")
