"""The BYOS contract the firmware depends on.

A TRMNL calls /api/display with its MAC in an `ID` header and expects
image_url, filename and refresh_rate back. Getting any of those wrong is a
blank panel, so the shape is pinned here.
"""
import tempfile
import unittest
from unittest.mock import AsyncMock

from fastapi.testclient import TestClient

from trmnl_server.app import create_app
from trmnl_server.config import Config

MAC = "AA:BB:CC:11:22:33"


class Api(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        config = Config(data_dir=self.dir.name, base_url="http://trmnl.test:8015",
                        presence_url="http://127.0.0.1:9/api/presence",
                        source_timeout_s=0.05)
        self.app = create_app(config=config, start_background=False)
        self.client = TestClient(self.app)
        self.client.__enter__()
        self.addCleanup(self.client.__exit__, None, None, None)
        # Stand in for a render; the browser is not started in tests.
        self.token = self.app.state.store.put(b"BM-not-really-a-bitmap")
        self.app.state.composer.token = self.token
        self.app.state.composer.screen_name = "now"

    # -- /api/setup --------------------------------------------------------

    def test_setup_provisions_and_is_idempotent(self):
        first = self.client.get("/api/setup", headers={"ID": MAC}).json()
        second = self.client.get("/api/setup", headers={"ID": MAC}).json()
        self.assertEqual(first["status"], 200)
        self.assertTrue(first["api_key"])
        self.assertEqual(first["api_key"], second["api_key"])

    def test_setup_without_an_id_is_rejected(self):
        self.assertEqual(self.client.get("/api/setup").status_code, 400)

    # -- /api/screen -------------------------------------------------------

    def test_current_screen_returns_the_selected_bitmap(self):
        compose = AsyncMock(return_value=self.token)
        self.app.state.composer.compose = compose

        response = self.client.get("/api/screen")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["content-type"], "image/bmp")
        self.assertEqual(response.headers["cache-control"], "no-store")
        self.assertEqual(response.headers["x-trmnl-screen"], "now")
        self.assertEqual(response.headers["x-trmnl-filename"], f"{self.token}.bmp")
        self.assertEqual(response.content, b"BM-not-really-a-bitmap")
        compose.assert_awaited_once_with()

    def test_current_screen_reports_when_nothing_is_rendered(self):
        self.app.state.composer.compose = AsyncMock(return_value=None)
        response = self.client.get("/api/screen")
        self.assertEqual(response.status_code, 503)

    def test_current_screen_json_returns_the_selected_image_url(self):
        compose = AsyncMock(return_value=self.token)
        self.app.state.composer.compose = compose

        response = self.client.get("/api/screen.json")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {
            "screen": "now",
            "filename": f"{self.token}.bmp",
            "image_url": f"http://trmnl.test:8015/image/{self.token}.bmp",
        })
        compose.assert_awaited_once_with()

    # -- /api/display ------------------------------------------------------

    def test_display_returns_the_firmware_contract(self):
        body = self.client.get("/api/display", headers={"ID": MAC}).json()
        for field in ("filename", "image_url", "refresh_rate", "update_firmware",
                      "reset_firmware", "special_function", "status"):
            self.assertIn(field, body)
        self.assertEqual(body["filename"], f"{self.token}.bmp")
        self.assertEqual(body["image_url"], f"http://trmnl.test:8015/image/{self.token}.bmp")
        self.assertIsInstance(body["refresh_rate"], int)
        self.assertGreaterEqual(body["refresh_rate"], 60)

    def test_filename_is_stable_while_the_image_is(self):
        one = self.client.get("/api/display", headers={"ID": MAC}).json()["filename"]
        two = self.client.get("/api/display", headers={"ID": MAC}).json()["filename"]
        self.assertEqual(one, two)

    def test_filename_tracks_the_image(self):
        before = self.client.get("/api/display", headers={"ID": MAC}).json()["filename"]
        self.app.state.composer.token = self.app.state.store.put(b"a different bitmap")
        after = self.client.get("/api/display", headers={"ID": MAC}).json()["filename"]
        self.assertNotEqual(before, after)

    def test_display_works_without_any_headers(self):
        """Bring-up: whatever the panel is currently configured to send, the
        first request must not 500."""
        self.assertEqual(self.client.get("/api/display").status_code, 200)

    def test_display_records_device_telemetry(self):
        self.client.get("/api/display", headers={
            "ID": MAC, "FW-VERSION": "1.4.8", "RSSI": "-61",
            "PERCENT-CHARGED": "83.5", "BATTERY_VOLTAGE": "4.01",
            "WIDTH": "800", "HEIGHT": "480"})
        device = self.app.state.registry.get(MAC)
        self.assertEqual(device["fw_version"], "1.4.8")
        self.assertEqual(device["rssi"], -61.0)
        self.assertEqual(device["percent_charged"], 83.5)

    def test_header_separators_are_interchangeable(self):
        """The contract documents ACCESS_TOKEN/FW_VERSION; some builds send
        hyphens. HTTP header names are case-insensitive either way."""
        self.client.get("/api/display", headers={"ID": MAC, "Fw-Version": "9.9.9"})
        self.assertEqual(self.app.state.registry.get(MAC)["fw_version"], "9.9.9")

    def test_poll_marks_the_composer_awake(self):
        self.assertEqual(self.app.state.composer.last_poll_at, 0.0)
        self.client.get("/api/display", headers={"ID": MAC})
        self.assertGreater(self.app.state.composer.last_poll_at, 0.0)

    # -- images ------------------------------------------------------------

    def test_image_is_served_and_cacheable_forever(self):
        response = self.client.get(f"/image/{self.token}.bmp")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["content-type"], "image/bmp")
        self.assertIn("immutable", response.headers["cache-control"])

    def test_unknown_image_is_404(self):
        self.assertEqual(self.client.get("/image/0123456789abcdef.bmp").status_code, 404)

    def test_image_path_cannot_escape_the_store(self):
        for name in ("../../etc/passwd", "..%2f..%2fetc%2fpasswd", "a/b.bmp"):
            self.assertIn(self.client.get(f"/image/{name}").status_code, (404, 400))

    # -- logs and humans ---------------------------------------------------

    def test_device_logs_are_accepted(self):
        response = self.client.post("/api/log", json={"logs": [
            {"message": "wifi weak", "level": "error", "firmware_version": "1.4.8"}]})
        self.assertEqual(response.status_code, 204)

    def test_malformed_log_body_is_not_an_error(self):
        self.assertEqual(self.client.post("/api/log", content=b"not json").status_code, 204)

    def test_unknown_preview_screen_lists_the_real_ones(self):
        response = self.client.get("/preview/nope")
        self.assertEqual(response.status_code, 404)
        self.assertIn("now", response.json()["detail"])

    def test_healthz_and_index(self):
        self.assertEqual(self.client.get("/healthz").status_code, 200)
        body = self.client.get("/").json()
        self.assertEqual(body["service"], "trmnl-server")
        self.assertEqual(body["screens"], ["morning", "now"])
