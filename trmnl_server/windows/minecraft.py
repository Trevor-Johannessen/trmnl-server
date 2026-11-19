"""Windows for the dedicated Minecraft screen."""
from ..layout import Window, esc

MAX_PLAYERS = 6


class Players(Window):
    def __init__(self, reading):
        self.reading = reading

    def render(self):
        if not self.reading.ok:
            return '<div class="w"><div class="empty">Minecraft unavailable</div></div>'

        data = self.reading.data or {}
        names = [name for name in (data.get("online") or []) if name]
        if not names:
            count = data.get("count") or 0
            message = f"{count} player online" if count == 1 else f"{count} players online"
            return f'<div class="w"><div class="empty">{esc(message)}</div></div>'

        rows = []
        for index, name in enumerate(names[:MAX_PLAYERS], start=1):
            rows.append(
                '<li>'
                f'<span class="badge">{index}</span>'
                f'<span class="md clip">{esc(name)}</span>'
                '</li>')
        more = len(names) - MAX_PLAYERS
        extra = f'<div class="xs" style="margin-top:6px">+{more} more</div>' if more > 0 else ""
        return (
            '<div class="w tight"><div class="caps">Online now</div>'
            f'<ul class="items">{"".join(rows)}</ul>{extra}</div>')


class Stats(Window):
    def __init__(self, reading):
        self.reading = reading

    def render(self):
        data = self.reading.data or {}
        online = data.get("online") or []
        count = data.get("count") or len(online)
        today = data.get("today") or 0
        return (
            '<div class="w"><div class="stack">'
            '<div class="caps">Players online</div>'
            f'<div class="xl">{esc(count)}</div>'
            '<div class="md">right now</div>'
            '<div class="grow"></div>'
            '<div class="caps">Seen today</div>'
            f'<div class="lg">{esc(today)}</div>'
            '<div class="sm">players</div>'
            '</div></div>')
