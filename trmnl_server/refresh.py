"""How long to tell the device to sleep.

The panel is held on each screen until the next edge of the morning schedule
(see schedule.py), rather than polling by presence. The Now screen does not
change minute to minute, so there is no point waking to redraw it.
"""
import math

from . import schedule


NOW_MAX_SLEEP_S = 3600  # the Now screen carries the temperature, so refresh hourly


def refresh_rate(config, presence, now, screen=None) -> int:
    edge = (schedule.next_boundary(now) - now).total_seconds()
    sleep = max(60, math.ceil(edge) + 5)
    if screen == "now":
        sleep = min(sleep, NOW_MAX_SLEEP_S)
    return sleep
