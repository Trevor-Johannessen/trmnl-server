"""homelab-health, for the House screen.

This is the one source that never runs in the request path. `health.py` SSHes
four machines and takes tens of seconds; the device is waiting on the poll. So
a background task refreshes it on a timer and `get()` only ever reads the
cached answer.

It runs *on sys1*, over ssh, rather than locally on deploy1. The script's
config marks whichever host it was written for as local (`ssh: null`), so a
local run on deploy1 would check deploy1 twice and sys1 not at all. Running it
where the cron already runs it means one config, no drift, and results
identical to the hourly mail.
"""
import asyncio
import json
import logging
import shlex
import time

from . import Reading, Source

log = logging.getLogger(__name__)

# Severity ordering as health.py emits it.
RANK = {"CRIT": 0, "WARN": 1, "OK": 2}


class Health(Source):
    name = "health"

    def __init__(self, config, metrics=None):
        super().__init__(config, metrics)
        self.command = shlex.split(config.health_command)
        self._task: asyncio.Task | None = None

    async def get(self) -> Reading:
        """Cache only. Never blocks on the subprocess."""
        if self._value is None:
            return Reading(ok=False, error="no result yet")
        age = time.time() - self._at
        return Reading(ok=True, data=self._value, age_s=age,
                       stale=age > self.config.health_interval_s * 2)

    async def fetch(self) -> dict:
        proc = await asyncio.create_subprocess_exec(
            *self.command, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        try:
            out, err = await asyncio.wait_for(proc.communicate(), timeout=120)
        except asyncio.TimeoutError:
            proc.kill()
            raise
        # A non-OK lab is a non-zero exit for some checks; the JSON is what matters.
        if not out.strip():
            raise RuntimeError((err or b"").decode()[:200] or "no output")
        report = json.loads(out)
        findings = report.get("findings") or []
        problems = [f for f in findings if (f.get("severity") or "OK").upper() != "OK"]
        problems.sort(key=lambda f: RANK.get((f.get("severity") or "").upper(), 9))
        return {
            "status": (report.get("status") or "OK").upper(),
            "checked_at": report.get("checked_at"),
            "findings": problems,
            "crit": sum(1 for f in problems if (f.get("severity") or "").upper() == "CRIT"),
            "warn": sum(1 for f in problems if (f.get("severity") or "").upper() == "WARN"),
        }

    async def refresh(self):
        try:
            self._value = await self.fetch()
            self._at = time.time()
        except Exception as exc:
            log.warning("health refresh failed: %s", type(exc).__name__)
            if self.metrics is not None:
                self.metrics.event("source.error", level="warn",
                                   message=type(exc).__name__, source=self.name)

    async def loop(self):
        while True:
            await self.refresh()
            await asyncio.sleep(self.config.health_interval_s)

    def start(self):
        self._task = asyncio.create_task(self.loop())
        return self._task

    async def stop(self):
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
