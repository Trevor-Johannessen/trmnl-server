"""Windows for the Now screen -- the default, the one that is up most of the time."""
from datetime import datetime

from ..layout import Window, esc


_SUN = ('<circle cx="12" cy="12" r="4.5"/><path d="M12 2v2.5M12 19.5V22M2 12h2.5M19.5 12H22'
        'M4.9 4.9l1.8 1.8M17.3 17.3l1.8 1.8M4.9 19.1l1.8-1.8M17.3 6.7l1.8-1.8"/>')
_CLOUD = '<path d="M7 18h10.5a4 4 0 0 0 0-8 6 6 0 0 0-11.6 1.6A3.4 3.4 0 0 0 7 18z"/>'
_GLYPHS = {
    "storm": _CLOUD + '<path d="M12.5 13l-2 4h3l-2 4"/>',
    "snow": _CLOUD + '<path d="M8 21v.01M12 21v.01M16 21v.01"/>',
    "rain": _CLOUD + '<path d="M8 20l-1 2M12 20l-1 2M16 20l-1 2"/>',
    "partly": '<g transform="translate(-3 -3)">' + _SUN + '</g>' + _CLOUD,
    "cloud": _CLOUD,
    "fog": '<path d="M3 9h18M5 13h14M3 17h18"/>',
    "sun": _SUN,
}


def weather_icon(condition):
    """Return an inline SVG symbol for an AccuWeather phrase. Glyphs such as
    U+2600 are not in any font on the panel, so they would draw blank."""
    text = " ".join(str(condition or "").lower().split())
    if any(word in text for word in ("thunder", "storm")):
        kind = "storm"
    elif any(word in text for word in ("snow", "sleet", "flurr", "ice")):
        kind = "snow"
    elif any(word in text for word in ("rain", "shower", "drizzle")):
        kind = "rain"
    elif "partly" in text and any(word in text for word in ("sun", "cloud")):
        kind = "partly"
    elif any(word in text for word in ("cloud", "overcast")):
        kind = "cloud"
    elif any(word in text for word in ("fog", "haze", "mist")):
        kind = "fog"
    elif any(word in text for word in ("sun", "clear")):
        kind = "sun"
    else:
        kind = "cloud"
    return ('<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" '
            'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'
            + _GLYPHS[kind] + "</svg>")


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
            f'<span class="weather-icon" style="font-size:64px" aria-hidden="true">{icon}</span>'
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
