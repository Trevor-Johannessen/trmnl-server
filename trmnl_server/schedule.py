"""The morning schedule, and the edges the panel holds each screen until.

Each day has a morning window. The panel wakes at the start of it so the
morning screen is up in time, and the window closes at noon. Weekdays show the
weather. Weekends show the date and today's high.

    Mon        6:00 -> 12:00
    Tue-Fri    5:00 -> 12:00
    Sat, Sun   5:00 -> 12:00   (assumed; not specified)

Outside the window the Now screen is shown, and it is held until the next edge:
the next morning window opening, or midnight, which changes the date.
`next_boundary` is what refresh.py sleeps to, so nothing polls in between.
"""
from datetime import date, datetime, time, timedelta

# weekday() -> ((start h, m), (end h, m)). Monday is 0.
PLAN = {
    0: ((6, 0), (12, 0)),
    1: ((5, 0), (12, 0)),
    2: ((5, 0), (12, 0)),
    3: ((5, 0), (12, 0)),
    4: ((5, 0), (12, 0)),
    5: ((5, 0), (12, 0)),
    6: ((5, 0), (12, 0)),
}


def window(day: date) -> tuple[datetime, datetime]:
    (sh, sm), (eh, em) = PLAN[day.weekday()]
    return datetime.combine(day, time(sh, sm)), datetime.combine(day, time(eh, em))


def active(now: datetime) -> bool:
    start, end = window(now.date())
    return start <= now < end


def weekend(now: datetime) -> bool:
    return now.weekday() >= 5


def next_boundary(now: datetime) -> datetime:
    """The next morning edge or midnight, strictly after `now`."""
    points = []
    for offset in (0, 1):
        points.extend(window(now.date() + timedelta(days=offset)))
    points.append(datetime.combine(now.date() + timedelta(days=1), time(0)))
    return min(point for point in points if point > now)
