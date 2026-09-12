"""Current conditions and today's range, via the weather skill's own module.

`accuweather.py` is imported rather than shelled out to because its commands
print prose for an agent to read, not JSON -- but `read_key`, `resolve`, `get`
and `unit` underneath are clean primitives worth reusing rather than
reimplementing. Its failure path is `die()`, which raises SystemExit, so every
call into it is wrapped: SystemExit is a BaseException and would otherwise sail
straight past the adapter's error handling.

The free AccuWeather tier is metered in tens of calls per day, so this is the
one source with an hour-scale TTL. The panel does not need minute-fresh
weather, and a 25-second TTL here would burn the quota before breakfast.
"""
import asyncio
import importlib.util
import json
import logging
import os

from . import Reading, Source

log = logging.getLogger(__name__)


def _load(skills_dir):
    path = os.path.join(skills_dir, "weather", "accuweather.py")
    spec = importlib.util.spec_from_file_location("trmnl_accuweather", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class Weather(Source):
    name = "weather"
    ttl_s = 3600.0          # current conditions: 24 calls a day
    timeout_s = 12.0
    forecast_ttl_s = 21600.0  # today's high/low moves slowly: 4 calls a day
    stale_after_s = 6 * 3600.0

    def __init__(self, config, metrics=None):
        super().__init__(config, metrics)
        self._module = None
        self._key = None
        self._location = None       # (location_key, display name)
        self._forecast = None
        self._forecast_at = 0.0
        self._cache_file = os.path.join(config.data_dir, "weather-location.json")

    async def get(self) -> Reading:
        if not self.config.weather_location:
            return Reading(ok=False, error="no location configured")
        return await super().get()

    # -- blocking work, all of it run in a thread ---------------------------

    def _resolve(self):
        if self._location is not None:
            return self._location
        try:
            with open(self._cache_file) as handle:
                cached = json.load(handle)
            if cached.get("query") == self.config.weather_location:
                self._location = (cached["key"], cached["name"])
                return self._location
        except (OSError, ValueError, KeyError):
            pass
        loc_key, name, _ = self._module.resolve(self.config.weather_location, self._key)
        self._location = (loc_key, name)
        try:
            os.makedirs(self.config.data_dir, exist_ok=True)
            with open(self._cache_file, "w") as handle:
                json.dump({"query": self.config.weather_location,
                           "key": loc_key, "name": name}, handle)
        except OSError:
            pass
        return self._location

    def _read(self):
        import time

        if self._module is None:
            self._module = _load(self.config.skills_dir)
        if self._key is None:
            self._key = self._module.read_key()
        loc_key, name = self._resolve()

        current = self._module.get(f"/currentconditions/v1/{loc_key}", self._key, details="true")
        if not current:
            raise RuntimeError("no current conditions")
        c = current[0]

        if self._forecast is None or time.time() - self._forecast_at > self.forecast_ttl_s:
            daily = self._module.get(f"/forecasts/v1/daily/1day/{loc_key}", self._key)
            days = (daily or {}).get("DailyForecasts") or []
            if days:
                temps = days[0].get("Temperature") or {}
                self._forecast = {
                    "high": self._module.unit(temps.get("Maximum"), False),
                    "low": self._module.unit(temps.get("Minimum"), False),
                    "day": (days[0].get("Day") or {}).get("IconPhrase"),
                }
                self._forecast_at = time.time()

        forecast = self._forecast or {}
        return {
            "location": name,
            "text": c.get("WeatherText"),
            "temp": self._module.unit(c.get("Temperature"), False),
            "feels": self._module.unit(c.get("RealFeelTemperature"), False),
            "high": forecast.get("high"),
            "low": forecast.get("low"),
            "outlook": forecast.get("day"),
        }

    async def fetch(self) -> dict:
        try:
            return await asyncio.to_thread(self._read)
        except SystemExit as exc:            # accuweather.die()
            raise RuntimeError(f"accuweather: {exc}") from None
