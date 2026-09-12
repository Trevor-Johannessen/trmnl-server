"""Windows for the Listening screen.

No progress bar. The panel refreshes once a minute at best, so a bar would be
wrong the instant it was drawn -- the original version of this file computed one
per minute of track length and it could never have been right.
"""
from ..layout import Window, esc


class Cover(Window):
    """Album art as a data: URI. The renderer's Chromium has no reason to be
    allowed out to the internet, so the bytes are fetched server-side."""

    def __init__(self, data_uri=None):
        self.data_uri = data_uri

    def render(self):
        if not self.data_uri:
            return '<div class="w"><div class="empty">♪</div></div>'
        return ('<div class="w" style="display:flex;align-items:center;justify-content:center">'
                f'<img class="art" src="{self.data_uri}" width="300" height="300"></div>')


class Track(Window):
    def __init__(self, data):
        self.data = data

    def render(self):
        title = self.data.get("title") or "Unknown track"
        artists = self.data.get("artists") or ""
        album = self.data.get("album") or ""
        return (
            '<div class="w"><div class="stack">'
            '<div class="caps">Now playing</div>'
            f'<div class="lg clip2" style="margin-top:8px">{esc(title)}</div>'
            f'<div class="md clip" style="margin-top:10px">{esc(artists)}</div>'
            '<div class="grow"></div>'
            f'<div class="sm clip">{esc(album)}</div>'
            "</div></div>"
        )
