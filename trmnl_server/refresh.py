"""How long to tell the device to sleep.

The panel polls once a minute at best -- a hardware limit -- so the only knob
worth having is not spending those polls on nobody. presence-server already
knows whether there is anyone in front of the screen, so it decides:

    present            -> fast, someone can see it
    absent / unknown   -> slow
    absent, overnight  -> slowest

Presence outranks the clock deliberately. Being in the room at midnight is a
reason to keep the screen current; being out of it at noon is not.
"""


def night(hour: int, start: int, end: int) -> bool:
    """The window wraps midnight, so 23->6 is 23,0,1,...,5."""
    if start == end:
        return False
    if start < end:
        return start <= hour < end
    return hour >= start or hour < end


def refresh_rate(config, presence, now) -> int:
    state = presence.get("state") if (presence and presence.ok) else None
    if state == "present":
        return config.refresh_present_s
    if night(now.hour, config.night_start_hour, config.night_end_hour):
        return config.refresh_night_s
    if state == "absent":
        return config.refresh_absent_s
    return config.refresh_unknown_s
