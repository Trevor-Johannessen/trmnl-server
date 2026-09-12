"""presence-server on deploy1:3344. Drives the Now screen's occupancy line and,
more importantly, the refresh_rate handed back to the device."""
from . import Source
from .http import get_json


class Presence(Source):
    name = "presence"
    ttl_s = 20.0

    async def fetch(self) -> dict:
        data = await get_json(self.config.presence_url)
        return {
            "state": data.get("state"),          # present | absent | unknown
            "since": data.get("since"),
            "last_seen": data.get("last_seen"),
            "duration_s": data.get("duration_s") or 0.0,
            "stream": data.get("stream"),
            # Added by the identity commit; absent on older deployments.
            "count": data.get("count"),
            "occupants": data.get("occupants") or [],
        }
