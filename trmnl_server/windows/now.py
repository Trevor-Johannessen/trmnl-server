"""Windows for the Now screen -- the default, the one that is up most of the time."""
from datetime import datetime

from ..layout import Window, esc


def weather_icon(condition):
    """Return a legible monochrome symbol for an AccuWeather phrase."""
    text = " ".join(str(condition or "").lower().split())
    if any(word in text for word in ("thunder", "storm")):
        return "⛈"
    if any(word in text for word in ("snow", "sleet", "flurr", "ice")):
        return "❄"
    if any(word in text for word in ("rain", "shower", "drizzle")):
        return "☂"
    if "partly" in text and any(word in text for word in ("sun", "cloud")):
        return "⛅"
    if any(word in text for word in ("cloud", "overcast")):
        return "☁"
    if any(word in text for word in ("fog", "haze", "mist")):
        return "≋"
    if any(word in text for word in ("sun", "clear")):
        return "☀"
    return "☁"


class Date(Window):
    """Just the day and date. The time is not shown, so the screen only changes
    when the date does."""

    def __init__(self, now=None):
        self.now = now or datetime.now()

    def render(self):
        return (
            '<div class="w now-clock-panel"><div class="stack">'
            '<div class="now-date-line"><span class="now-day">'
            f'{esc(self.now.strftime("%A"))}</span>'
            f'<span class="now-date">{esc(self.now.strftime("%-d %B"))}</span></div>'
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
        icon = weather_icon(data.get("text") or data.get("outlook"))
        return (
            '<div class="w now-weather-panel">'
            f'<div class="caps">{esc(data.get("location") or "Weather")} {stale}</div>'
            '<div class="now-weather-line">'
            f'<span class="weather-icon" aria-hidden="true">{icon}</span>'
            f'<span class="now-weather-temp">{esc(data.get("temp") or "—")}</span>'
            f'<span class="now-weather-text clip">{esc(data.get("text") or "")}</span>'
            '</div>'
            f'<div class="now-weather-details">{"".join(rows)}</div>'
            '</div>'
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
            return ('<div class="w tight now-calendar-panel"><div class="caps">Calendar</div>'
                    '<div class="empty">Nothing scheduled</div></div>')
        rows = []
        for index, event in enumerate(events[:2]):
            start = datetime.fromisoformat(event["start"])
            event_class = "now-event-primary" if index == 0 else "now-event-secondary"
            rows.append(
                f'<div class="now-event {event_class}">'
                f'<div class="now-event-when">{esc(self._when(start, event["all_day"]))}</div>'
                f'<div class="now-event-title clip">{esc(event["summary"])}</div></div>')
        return ('<div class="w tight now-calendar-panel"><div class="caps">Calendar</div>'
                '<div class="now-events">' + "".join(rows) + "</div></div>")
