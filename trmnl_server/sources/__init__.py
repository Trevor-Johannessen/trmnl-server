"""Data adapters, one per upstream service.

Every adapter has a timeout and holds its last good answer. A service that goes
down degrades the screen that uses it -- it never stalls the render, and it
never takes the panel down with it. The device is waiting on this call; a
source that hangs would turn into a missed poll.
"""
import asyncio
import logging
import time
from dataclasses import dataclass, field

log = logging.getLogger(__name__)


@dataclass
class Reading:
    ok: bool = False
    data: dict = field(default_factory=dict)
    stale: bool = False
    age_s: float = 0.0
    error: str | None = None

    def get(self, key, default=None):
        return self.data.get(key, default)


class Source:
    name = "source"
    ttl_s = 25.0          # serve the cached answer for this long before refetching
    stale_after_s = 900.0 # beyond this a last-good answer is not worth showing
    timeout_s = None      # None: use config.source_timeout_s

    def __init__(self, config, metrics=None):
        self.config = config
        self.metrics = metrics
        self._value: dict | None = None
        self._at: float = 0.0
        self._lock = asyncio.Lock()

    async def fetch(self) -> dict:
        raise NotImplementedError

    async def get(self) -> Reading:
        async with self._lock:
            now = time.time()
            if self._value is not None and now - self._at < self.ttl_s:
                return Reading(ok=True, data=self._value, age_s=now - self._at)
            try:
                timeout = self.timeout_s or self.config.source_timeout_s
                value = await asyncio.wait_for(self.fetch(), timeout)
                self._value, self._at = value, time.time()
                return Reading(ok=True, data=value, age_s=0.0)
            except Exception as exc:
                reason = "timeout" if isinstance(exc, asyncio.TimeoutError) else type(exc).__name__
                log.warning("Source %s failed: %s", self.name, reason)
                if self.metrics is not None:
                    self.metrics.event("source.timeout" if reason == "timeout" else "source.error",
                                       level="warn", message=reason, source=self.name)
                age = time.time() - self._at
                if self._value is not None and age < self.stale_after_s:
                    return Reading(ok=True, data=self._value, stale=True, age_s=age, error=reason)
                return Reading(ok=False, error=reason)
