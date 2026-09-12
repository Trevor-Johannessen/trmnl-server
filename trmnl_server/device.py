"""Devices that have introduced themselves, and what they told us.

The firmware puts its whole state in the headers of every `/api/display` call
-- battery, signal, firmware version, why it woke up -- so the metrics
dashboard gets real device telemetry without asking for anything.

Header names are read case- and separator-insensitively: the Terminus contract
documents ACCESS_TOKEN and BATTERY_VOLTAGE, some firmware builds send
Access-Token and Battery-Voltage, and HTTP header names are case-insensitive
either way.
"""
import json
import os
import secrets
import time


def header(request, *names):
    for name in names:
        for variant in {name, name.replace("_", "-"), name.replace("-", "_")}:
            value = request.headers.get(variant)
            if value not in (None, ""):
                return value
    return None


def number(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def telemetry(request) -> dict:
    """Everything the firmware volunteered, normalised."""
    return {
        "mac": (header(request, "ID") or "").lower() or None,
        "fw_version": header(request, "FW_VERSION"),
        "model": header(request, "MODEL"),
        "width": number(header(request, "WIDTH")),
        "height": number(header(request, "HEIGHT")),
        "rssi": number(header(request, "RSSI")),
        "battery_voltage": number(header(request, "BATTERY_VOLTAGE")),
        "percent_charged": number(header(request, "PERCENT_CHARGED")),
        "usb_connected": header(request, "USB_CONNECTED"),
        "wake_time": number(header(request, "WAKE_TIME")),
        "update_source": header(request, "UPDATE_SOURCE"),
        "image_cached": header(request, "IMAGE_CACHED"),
        "refresh_rate": number(header(request, "REFRESH_RATE")),
    }


class Registry:
    """One JSON file. There is one panel; this is not a fleet."""

    def __init__(self, path: str):
        self.path = path
        self.devices: dict[str, dict] = {}
        self._load()

    def _load(self):
        try:
            with open(self.path) as handle:
                self.devices = json.load(handle)
        except (OSError, ValueError):
            self.devices = {}

    def _save(self):
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        tmp = f"{self.path}.tmp"
        with open(tmp, "w") as handle:
            json.dump(self.devices, handle, indent=2)
        os.chmod(tmp, 0o600)   # the NFS home ignores umask; the token is a secret
        os.replace(tmp, self.path)

    def get(self, mac: str) -> dict | None:
        return self.devices.get((mac or "").lower())

    def provision(self, mac: str) -> dict:
        mac = (mac or "").lower()
        device = self.devices.get(mac)
        if device is None:
            device = {"api_key": secrets.token_hex(16), "first_seen": time.time()}
            self.devices[mac] = device
            self._save()
        return device

    def seen(self, mac: str, **fields):
        mac = (mac or "").lower()
        device = self.devices.setdefault(mac, {"api_key": secrets.token_hex(16),
                                               "first_seen": time.time()})
        device["last_seen"] = time.time()
        device.update({k: v for k, v in fields.items() if v is not None})
        self._save()
        return device
