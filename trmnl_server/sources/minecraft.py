"""minecraft-led-server on minecraft2:3343 -- who is online, for the House screen."""
import asyncio

from . import Source
from .http import get_json


class Minecraft(Source):
    name = "minecraft"
    ttl_s = 45.0

    async def fetch(self) -> dict:
        players, today = await asyncio.gather(
            get_json(f"{self.config.minecraft_url}/v1/players"),
            get_json(f"{self.config.minecraft_url}/v1/today"),
            return_exceptions=True,
        )
        online = []
        count = 0
        if isinstance(players, dict):
            count = players.get("count") or 0
            online = [p if isinstance(p, str) else p.get("name")
                      for p in players.get("online") or []]
        seen_today = 0
        if isinstance(today, dict):
            seen_today = today.get("count") or 0
        return {"count": count, "online": [n for n in online if n], "today": seen_today}
