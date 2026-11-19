"""How long to tell the device to sleep.

The panel is held on each screen until the next edge of the morning schedule
(see schedule.py), rather than polling by presence. The Now screen does not
change minute to minute, so there is no point waking to redraw it.
"""
import math

from . import schedule


def refresh_rate(config, presence, now) -> int:
    edge = (schedule.next_boundary(now) - now).total_seconds()
    return max(60, math.ceil(edge) + 5)
