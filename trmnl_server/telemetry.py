"""Service schema and fail-safe writes; the three dashboard assets stay verbatim."""
import logging
import sqlite3
import uuid
from functools import wraps

from metrics import Metrics, Session

log = logging.getLogger(__name__)

SCHEMA = {
    "title": "TRMNL Server",
    "kinds": {
        "poll": {"label": "Device polls", "columns": [
            {"field": "screen", "label": "Screen", "format": "text"},
            {"field": "refresh_rate", "label": "Sleep", "format": "duration"},
            {"field": "cached", "label": "Cached", "format": "text"},
            {"field": "percent_charged", "label": "Battery", "format": "number"},
            {"field": "rssi", "label": "RSSI", "format": "number"},
            {"field": "wake_time", "label": "Awake", "format": "number"}]},
        "render": {"label": "Renders", "columns": [
            {"field": "screen", "label": "Screen", "format": "text"},
            {"field": "render_s", "label": "Render", "format": "number"},
            {"field": "bytes", "label": "Size", "format": "number"},
            {"field": "token", "label": "Token", "format": "text"}]},
        "api": {"label": "API calls", "columns": [
            {"field": "path", "label": "Path", "format": "text"},
            {"field": "status_code", "label": "Status", "format": "number"}]},
    },
    "totals": [{"field": "bytes", "label": "Bytes rendered", "format": "number"}],
    "status": [
        {"gauge": "screen", "label": "Showing", "format": "text"},
        {"gauge": "last_poll", "label": "Last poll", "format": "time"},
        {"gauge": "refresh_rate", "label": "Sleep", "format": "duration"},
        {"gauge": "battery", "label": "Battery %", "format": "number"},
        {"gauge": "rssi", "label": "RSSI", "format": "number"},
        {"gauge": "fw_version", "label": "Firmware", "format": "text"},
        {"gauge": "device", "label": "Device", "format": "text"},
        {"gauge": "render_error", "label": "Render error", "format": "text"}],
}


def safe_write(method):
    @wraps(method)
    def wrapped(*args, **kwargs):
        try:
            return method(*args, **kwargs)
        except (sqlite3.Error, OSError):
            log.exception("Metrics write failed: %s", method.__name__)
    return wrapped


class Recorder(Metrics):
    event = safe_write(Metrics.event)
    _update_session_fields = safe_write(Metrics._update_session_fields)
    _close_session = safe_write(Metrics._close_session)

    def session(self, kind, **kwargs):
        try:
            return super().session(kind, **kwargs)
        except (sqlite3.Error, OSError):
            log.exception("Could not persist %s session", kind)
            return Session(self, uuid.uuid4().hex[:16], kind)
