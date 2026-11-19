"""Environment-backed configuration. Every knob is an env var so the unit file
is the single place the deployment is described."""
import os
from dataclasses import dataclass, field

# The panel. Fixed by the hardware; nothing here is configurable in practice,
# but the firmware sends WIDTH/HEIGHT on every poll so a mismatch is visible.
WIDTH = 800
HEIGHT = 480


def _int(name, default):
    try:
        return int(os.environ.get(name, default))
    except ValueError:
        return default


@dataclass
class Config:
    data_dir: str = "/var/lib/trmnl-server"
    base_url: str = "http://deploy1.sflabs.local:8015"

    presence_url: str = "http://127.0.0.1:3344/api/presence"
    spotify_url: str = "http://pi1.sflabs.local:3339/v1/status"
    spotify_credentials: str = "~/.credentials/spotify.json"
    minecraft_url: str = "http://minecraft2.sflabs.local:3343"
    health_command: str = ""
    health_interval_s: int = 300
    weather_location: str = ""
    skills_dir: str = "~/.claude/skills"
    invert: bool = False

    source_timeout_s: float = 2.0
    compose_interval_s: int = 30
    idle_after_s: int = 1800
    keep_images: int = 10

    # refresh_rate returned to the device, by presence state. The panel polls
    # at most once a minute, so fast polls are only worth spending when
    # somebody is actually in front of it.
    refresh_present_s: int = 60
    refresh_absent_s: int = 900
    refresh_unknown_s: int = 300
    refresh_night_s: int = 1800
    night_start_hour: int = 23
    night_end_hour: int = 6

    # How long after the last sighting the room still counts as occupied. A
    # fifteen-minute sleep starting the moment somebody steps out is how the
    # panel comes to be stale exactly when they walk back in.
    presence_grace_s: int = 1800

    devices: dict = field(default_factory=dict)

    @classmethod
    def from_env(cls):
        env = os.environ.get
        return cls(
            data_dir=env("TRMNL_SERVER_DATA_DIR", "/var/lib/trmnl-server"),
            base_url=env("TRMNL_SERVER_BASE_URL", "http://deploy1.sflabs.local:8015").rstrip("/"),
            presence_url=env("TRMNL_SERVER_PRESENCE_URL", "http://127.0.0.1:3344/api/presence"),
            spotify_url=env("TRMNL_SERVER_SPOTIFY_URL", "http://pi1.sflabs.local:3339/v1/status"),
            spotify_credentials=os.path.expanduser(
                env("TRMNL_SERVER_SPOTIFY_CREDENTIALS", "~/.credentials/spotify.json")),
            minecraft_url=env("TRMNL_SERVER_MINECRAFT_URL",
                              "http://minecraft2.sflabs.local:3343").rstrip("/"),
            health_command=env("TRMNL_SERVER_HEALTH_COMMAND", "") or (
                "ssh -o BatchMode=yes -o ConnectTimeout=10 sys1 /usr/bin/python3 "
                + os.path.expanduser(env("TRMNL_SERVER_SKILLS_DIR", "~/.claude/skills"))
                + "/homelab-health/health.py --json"),
            health_interval_s=_int("TRMNL_SERVER_HEALTH_INTERVAL_S", 300),
            weather_location=env("TRMNL_SERVER_WEATHER_LOCATION", ""),
            skills_dir=os.path.expanduser(env("TRMNL_SERVER_SKILLS_DIR", "~/.claude/skills")),
            invert=env("TRMNL_SERVER_INVERT", "0") not in ("0", "", "false", "no"),
            source_timeout_s=float(env("TRMNL_SERVER_SOURCE_TIMEOUT_S", "2.0")),
            compose_interval_s=_int("TRMNL_SERVER_COMPOSE_INTERVAL_S", 30),
            idle_after_s=_int("TRMNL_SERVER_IDLE_AFTER_S", 1800),
            keep_images=_int("TRMNL_SERVER_KEEP_IMAGES", 10),
            refresh_present_s=_int("TRMNL_SERVER_REFRESH_PRESENT_S", 60),
            refresh_absent_s=_int("TRMNL_SERVER_REFRESH_ABSENT_S", 900),
            refresh_unknown_s=_int("TRMNL_SERVER_REFRESH_UNKNOWN_S", 300),
            refresh_night_s=_int("TRMNL_SERVER_REFRESH_NIGHT_S", 1800),
            night_start_hour=_int("TRMNL_SERVER_NIGHT_START_HOUR", 23),
            night_end_hour=_int("TRMNL_SERVER_NIGHT_END_HOUR", 6),
            presence_grace_s=_int("TRMNL_SERVER_PRESENCE_GRACE_S", 1800),
        )
