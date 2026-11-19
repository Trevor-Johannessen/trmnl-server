"""Windows for the Listening screen.

No progress bar. The panel refreshes once a minute at best, so a bar would be
wrong the instant it was drawn -- the original version of this file computed one
per minute of track length and it could never have been right.
"""
from ..layout import Window, esc


def track_length(duration_ms):
    """Format Spotify's duration in milliseconds for the panel."""
    try:
        seconds = max(0, round(float(duration_ms) / 1000))
    except (TypeError, ValueError):
        return ""
    return f"{seconds // 60}:{seconds % 60:02d}"


class Cover(Window):
    """Album art as a data: URI. The renderer's Chromium has no reason to be
    allowed out to the internet, so the bytes are fetched server-side."""

    def __init__(self, data_uri=None, time_text=""):
        self.data_uri = data_uri
        self.time_text = time_text

    def render(self):
        if self.data_uri:
            art = f'<img class="art" src="{self.data_uri}" width="320" height="320">'
        else:
            art = '<div class="listening-no-art">♪</div>'
        return ('<div class="w listening-cover">'
                f'<div class="listening-art">{art}</div>'
                f'<div class="listen-time">{self.time_text}</div></div>')


class Track(Window):
    def __init__(self, data):
        self.data = data

    def render(self):
        title = self.data.get("title") or "Unknown track"
        artists = self.data.get("artists") or ""
        album = self.data.get("album") or "Unknown album"
        duration = track_length(self.data.get("duration_ms"))
        footer = (
            f'<div class="track-footer"><span class="track-duration">{duration}</span>'
            '<span class="track-duration-label">track length</span></div>'
            if duration else "")
        return (
            '<div class="w"><div class="stack">'
            '<div class="caps">Now playing</div>'
            f'<div class="lg clip2" style="margin-top:8px">{esc(title)}</div>'
            f'<div class="md clip" style="margin-top:10px">{esc(artists)}</div>'
            f'{footer}'
            '<div class="grow"></div>'
            '<div class="caps">Album</div>'
            f'<div class="album-name clip">{esc(album)}</div>'
            "</div></div>"
        )
