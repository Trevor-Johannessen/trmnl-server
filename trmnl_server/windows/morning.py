"""Windows for the Morning screen -- the scheduled weather shown in the mornings."""
from datetime import datetime

from ..layout import Window, esc
from .now import weather_icon


def _date_line(now):
    return ('<div class="now-date-line">'
            f'<span class="now-day">{esc(now.strftime("%A"))}</span>'
            f'<span class="now-date">{esc(now.strftime("%-d %B"))}</span></div>')


def _values(*pairs):
    """Big labels with big numbers beside them, e.g. High 14° Low 8°."""
    cells = "".join(f'<span class="md">{esc(label)}</span>'
                    f'<span class="lg">{esc(value)}</span>'
                    for label, value in pairs)
    return f'<div class="row" style="margin-top:10px">{cells}</div>'


class Forecast(Window):
    """Weekdays: the date, the temperature now, with today's high and low."""

    def __init__(self, now, reading):
        self.now = now
        self.reading = reading

    def render(self):
        if not self.reading.ok:
            return (f'<div class="w"><div class="stack">{_date_line(self.now)}'
                    '<div class="empty">—</div></div></div>')
        data = self.reading.data or {}
        icon = weather_icon(data.get("text"))
        return (
            '<div class="w" style="display:flex;justify-content:space-between;align-items:center">'
            '<div class="stack">'
            f'{_date_line(self.now)}'
            f'<div class="now-time"><span class="now-time-main">{esc(data.get("temp") or "—")}</span></div>'
            f'{_values(("High", data.get("high") or "—"), ("Low", data.get("low") or "—"))}'
            f'<div class="sm clip">{esc(data.get("text") or "")}</div>'
            '</div>'
            f'<div class="weather-icon" style="font-size:220px;margin-right:24px">{icon}</div>'
            "</div>"
        )


class DateHigh(Window):
    """Weekends: the date and today's high."""

    def __init__(self, now, reading):
        self.now = now
        self.reading = reading

    def render(self):
        high = "—"
        if self.reading.ok:
            high = (self.reading.data or {}).get("high") or "—"
        return (
            '<div class="w"><div class="stack">'
            f'{_date_line(self.now)}'
            f'{_values(("High", high))}'
            "</div></div>"
        )


class Events(Window):
    """Upcoming calendar events, the same rows as the Now screen but more of them."""

    def __init__(self, now, reading, limit=3):
        self.now = now
        self.reading = reading
        self.limit = limit

    def render(self):
        from .now import NextEvent

        events = (self.reading.data or {}).get("events") or [] if self.reading.ok else []
        if not events:
            return ('<div class="w tight"><div class="caps">Coming up</div>'
                    '<div class="empty">Nothing scheduled</div></div>')
        when = NextEvent(self.reading, self.now)._when
        rows = []
        for index, event in enumerate(events[:self.limit]):
            start = datetime.fromisoformat(event["start"])
            event_class = "now-event-primary" if index == 0 else "now-event-secondary"
            rows.append(
                f'<div class="now-event {event_class}">'
                f'<div class="now-event-when">{esc(when(start, event["all_day"]))}</div>'
                f'<div class="now-event-title clip">{esc(event["summary"])}</div></div>')
        return ('<div class="w tight"><div class="caps">Coming up</div>'
                '<div class="now-events">' + "".join(rows) + "</div></div>")
