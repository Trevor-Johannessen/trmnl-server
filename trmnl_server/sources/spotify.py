"""spotify-server on pi1:3339.

`audio.playing` is what gates the Listening screen -- it reflects PCM actually
moving, which is the honest answer to "is music on", where player.paused only
reflects the last event librespot bothered to send.

Track names and album art come from the Spotify Web API, the same path
music-visualizer already uses, keyed by track id and cached because the art for
a given track never changes.
"""
import asyncio
import base64
import json
import time

from . import Source
from .http import client, get_json

TOKEN_URL = "https://accounts.spotify.com/api/token"
TRACK_URL = "https://api.spotify.com/v1/tracks/{}"


class Spotify(Source):
    name = "spotify"
    ttl_s = 15.0
    timeout_s = 6.0

    def __init__(self, config, metrics=None):
        super().__init__(config, metrics)
        self._tracks: dict[str, dict] = {}
        self._art: dict[str, bytes] = {}
        self._token: tuple[str, float] | None = None

    async def fetch(self) -> dict:
        status = await get_json(self.config.spotify_url)
        audio = status.get("audio") or {}
        player = status.get("player") or {}
        track_id = player.get("track_id")
        out = {
            "playing": bool(audio.get("playing")),
            "track_id": track_id,
            "title": (status.get("telemetry") or {}).get("title"),
            "artists": None,
            "album": None,
            "art": None,
            "duration_ms": player.get("duration_ms"),
        }
        if track_id:
            meta = await self._track(track_id)
            if meta:
                out.update(meta)
        return out

    # -- Spotify Web API ---------------------------------------------------

    def _credentials(self):
        """The house convention: one file per service under ~/.credentials, the
        same file spotify-server and music-visualizer read. The service runs as
        tjohannessen (as monika does) precisely so this resolves."""
        with open(self.config.spotify_credentials) as handle:
            creds = json.load(handle)
        return creds["SPOTIFY_CLIENT_ID"], creds["SPOTIFY_CLIENT_SECRET"]

    async def _access_token(self) -> str | None:
        if self._token and self._token[1] > time.time() + 30:
            return self._token[0]
        try:
            client_id, secret = await asyncio.to_thread(self._credentials)
        except (OSError, KeyError, ValueError):
            return None
        basic = base64.b64encode(f"{client_id}:{secret}".encode()).decode()
        response = await client().post(
            TOKEN_URL, data={"grant_type": "client_credentials"},
            headers={"Authorization": f"Basic {basic}"})
        response.raise_for_status()
        body = response.json()
        self._token = (body["access_token"], time.time() + body.get("expires_in", 3600))
        return self._token[0]

    async def _track(self, track_id: str) -> dict | None:
        if track_id in self._tracks:
            return self._tracks[track_id]
        token = await self._access_token()
        if not token:
            return None
        response = await client().get(TRACK_URL.format(track_id),
                                      headers={"Authorization": f"Bearer {token}"})
        if response.status_code != 200:
            return None
        track = response.json()
        images = (track.get("album") or {}).get("images") or []
        meta = {
            "title": track.get("name"),
            "artists": ", ".join(a["name"] for a in track.get("artists") or []),
            "album": (track.get("album") or {}).get("name"),
            "art": images[0]["url"] if images else None,
            "duration_ms": track.get("duration_ms"),
        }
        if len(self._tracks) > 256:
            self._tracks.clear()
        self._tracks[track_id] = meta
        return meta

    async def art_bytes(self, url: str) -> bytes | None:
        """Fetched server-side and inlined as a data: URI. Chromium in the
        renderer has no reason to be allowed out to the internet."""
        if url in self._art:
            return self._art[url]
        try:
            response = await client().get(url)
            response.raise_for_status()
        except Exception:
            return None
        if len(self._art) > 32:
            self._art.clear()
        self._art[url] = response.content
        return response.content
