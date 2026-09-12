"""The next thing on the calendar, via the calendar skill's own module.

`icloud_calendar.py` re-execs itself under Monika's venv when `caldav` is
missing -- `os.execv`, which would replace this server process rather than
raise. So the guard variable is set before the module is loaded, turning that
path into a plain SystemExit, and `caldav` is checked for first so it normally
never triggers at all. Both SystemExit and the import are caught here; a
calendar that cannot be reached just drops the line from the Now screen.
"""
import asyncio
import importlib.util
import logging
import os
from datetime import datetime, timedelta

from . import Reading, Source

log = logging.getLogger(__name__)

LOOKAHEAD_DAYS = 14


def _load(skills_dir):
    # A real import, not find_spec: caldav can be present but unimportable (it
    # imports requests without declaring it), and the module below turns an
    # ImportError into a process-replacing os.execv.
    try:
        import caldav  # noqa: F401
    except Exception as exc:
        raise RuntimeError(f"caldav is not usable in this venv: {exc}") from None
    os.environ["MONIKA_CALENDAR_REEXEC"] = "1"   # never let it os.execv us
    path = os.path.join(skills_dir, "calendar", "icloud_calendar.py")
    spec = importlib.util.spec_from_file_location("trmnl_icloud_calendar", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class Calendar(Source):
    name = "calendar"
    ttl_s = 600.0
    timeout_s = 20.0
    stale_after_s = 6 * 3600.0

    def __init__(self, config, metrics=None):
        super().__init__(config, metrics)
        self._module = None

    def _read(self):
        if self._module is None:
            self._module = _load(self.config.skills_dir)
        now = datetime.now(self._module.local_tz())
        events = self._module.search_events(now, now + timedelta(days=LOOKAHEAD_DAYS), None)
        upcoming = [e for e in events if e.get("start") is not None and e["end"] and e["end"] > now]
        return {"events": [
            {"summary": e["summary"], "start": e["start"].isoformat(),
             "all_day": e["all_day"], "location": e["location"]}
            for e in upcoming[:3]]}

    async def fetch(self) -> dict:
        try:
            return await asyncio.to_thread(self._read)
        except SystemExit as exc:            # icloud_calendar.die()
            raise RuntimeError(f"calendar: {exc}") from None
