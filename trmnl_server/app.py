"""The BYOS server.

A TRMNL wakes, calls GET /api/display with its MAC in an `ID` header, is told
an image URL and how long to sleep, downloads the bitmap and goes away again.
That contract is the whole reason this service exists; see
https://github.com/usetrmnl/terminus/blob/main/doc/api.adoc

Nothing slow happens inside a poll. Composition runs on its own loop, so this
handler records what the firmware told us, picks a sleep length and answers out
of memory.
"""
import logging
import os
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import HTMLResponse

from metrics import config_from_env
from metrics_api import actor_args, build_router

from . import __version__
from .compose import Composer
from .config import HEIGHT, WIDTH, Config
from .device import Registry, telemetry
from .layout import document
from .refresh import refresh_rate
from .render import ImageStore, Renderer
from .screens import SCREENS, select
from .sources import http as source_http
from .sources.calendar import Calendar
from .sources.health import Health
from .sources.minecraft import Minecraft
from .sources.presence import Presence
from .sources.spotify import Spotify
from .sources.weather import Weather
from .telemetry import SCHEMA, Recorder

log = logging.getLogger(__name__)

CSS_PATH = os.path.join(os.path.dirname(__file__), "static", "screen.css")


def create_app(*, config=None, start_background=True):
    config = config or Config.from_env()
    metrics_config = config_from_env("trmnl-server")
    metrics_config["data_dir"] = config.data_dir
    metrics = Recorder("trmnl-server", schema=SCHEMA, version=__version__, **metrics_config)

    with open(CSS_PATH) as handle:
        css = handle.read()

    registry = Registry(os.path.join(config.data_dir, "devices.json"))
    renderer = Renderer(invert=config.invert)
    store = ImageStore(os.path.join(config.data_dir, "images"), keep=config.keep_images)
    sources = {
        "presence": Presence(config, metrics),
        "spotify": Spotify(config, metrics),
        "health": Health(config, metrics),
        "minecraft": Minecraft(config, metrics),
        "weather": Weather(config, metrics),
        "calendar": Calendar(config, metrics),
    }
    composer = Composer(config, metrics, renderer, store, sources, css)

    @asynccontextmanager
    async def lifespan(app):
        metrics.service_start()
        if start_background:
            await renderer.start()
            sources["health"].start()
            composer.start()
        try:
            yield
        finally:
            if start_background:
                await composer.stop()
                await sources["health"].stop()
                await renderer.stop()
            await source_http.close()
            metrics.service_stop()
            metrics.close()

    app = FastAPI(title="TRMNL Server", version=__version__, lifespan=lifespan)
    app.state.config = config
    app.state.metrics = metrics
    app.state.composer = composer
    app.state.registry = registry
    app.state.sources = sources
    app.state.store = store
    app.include_router(build_router(metrics))

    @app.middleware("http")
    async def track_api(request: Request, call_next):
        # The device's own routes get their own session kind; this covers the
        # human-facing ones so the dashboard shows who has been poking at it.
        if not request.url.path.startswith("/preview"):
            return await call_next(request)
        with metrics.session("api", **actor_args(request)) as session:
            session.set(path=request.url.path)
            response = await call_next(request)
            session.set(status_code=response.status_code)
            if response.status_code >= 500:
                session.fail(f"HTTP {response.status_code}")
            elif response.status_code >= 400:
                session.reject(f"HTTP {response.status_code}")
            return response

    def image_url(token: str) -> str:
        return f"{config.base_url}/image/{token}.bmp"

    # -- the device -------------------------------------------------------

    @app.get("/api/setup")
    async def setup(request: Request):
        """First contact. The device asks who it is and gets a key back."""
        mac = (request.headers.get("ID") or "").lower()
        if not mac:
            raise HTTPException(status_code=400, detail="Missing ID header")
        device = registry.provision(mac)
        metrics.event("device.provisioned", mac=mac)
        log.info("Provisioned device %s", mac)
        return {
            "status": 200,
            "api_key": device["api_key"],
            "friendly_id": mac.replace(":", "")[-6:].upper(),
            "image_url": image_url(composer.token) if composer.token else "",
            "message": "Welcome to trmnl-server",
        }

    @app.get("/api/display")
    async def display(request: Request):
        info = telemetry(request)
        now = time.time()
        composer.last_poll_at = now

        presence = await sources["presence"].get()
        from datetime import datetime
        sleep_s = refresh_rate(config, presence, datetime.now())

        token = composer.token
        if token is None:
            # Nothing rendered yet -- first poll after a restart. Do it now
            # rather than hand the panel an empty URL.
            token = await composer.compose(force=True)

        cached = (request.headers.get("IMAGE_CACHED")
                  or request.headers.get("Image-Cached") or "")
        with metrics.session("poll", **actor_args(request)) as session:
            session.set(screen=composer.screen_name, refresh_rate=sleep_s,
                        cached=cached or "0", token=token,
                        **{k: v for k, v in info.items()
                           if k in ("percent_charged", "rssi", "wake_time",
                                    "battery_voltage", "fw_version", "update_source")})
        if info["mac"]:
            registry.seen(info["mac"], **{k: v for k, v in info.items() if k != "mac"})
            metrics.gauge("device", info["mac"])
        metrics.gauge("last_poll", now)
        metrics.gauge("refresh_rate", sleep_s)
        if info["percent_charged"] is not None:
            metrics.gauge("battery", info["percent_charged"])
        if info["rssi"] is not None:
            metrics.gauge("rssi", info["rssi"])
        if info["fw_version"]:
            metrics.gauge("fw_version", info["fw_version"])
        metrics.gauge("render_error", composer.last_error or "")

        if info["width"] and (info["width"], info["height"]) != (WIDTH, HEIGHT):
            log.warning("Device reports %sx%s, screens are %sx%s",
                        info["width"], info["height"], WIDTH, HEIGHT)

        return {
            "status": 0,
            "filename": f"{token}.bmp" if token else "",
            "image_url": image_url(token) if token else "",
            "image_url_timeout": 0,
            "refresh_rate": sleep_s,
            "update_firmware": False,
            "firmware_url": None,
            "reset_firmware": False,
            "special_function": "none",
        }

    @app.post("/api/log", status_code=204)
    async def device_log(request: Request):
        try:
            body = await request.json()
        except Exception:
            body = {}
        for entry in (body.get("logs") or [])[:20]:
            metrics.event("device.log",
                          level="error" if entry.get("level") == "error" else "info",
                          message=str(entry.get("message", ""))[:400],
                          source_path=entry.get("source_path"),
                          fw=entry.get("firmware_version"),
                          wake_reason=entry.get("wake_reason"))
        return Response(status_code=204)

    @app.get("/image/{name}")
    async def image(name: str):
        token = name[:-4] if name.endswith(".bmp") else name
        if not token.isalnum():
            raise HTTPException(status_code=404, detail="Not found")
        path = store.path(token)
        if not os.path.exists(path):
            raise HTTPException(status_code=404, detail="Not found")
        with open(path, "rb") as handle:
            data = handle.read()
        # Content-addressed: the bytes for a token never change, so the device
        # and any proxy may hold onto them forever.
        return Response(data, media_type="image/bmp",
                        headers={"Cache-Control": "public, max-age=31536000, immutable"})

    # -- humans -----------------------------------------------------------

    @app.get("/preview", response_class=HTMLResponse)
    async def preview_current():
        ctx = await composer.context()
        screen = select(ctx, SCREENS)
        return HTMLResponse(document(screen.body(ctx), css, title=screen.title))

    @app.get("/preview/{name}", response_class=HTMLResponse)
    async def preview_screen(name: str):
        want = name[:-4] if name.endswith(".png") else name
        screen = next((s for s in SCREENS if s.name == want), None)
        if screen is None:
            raise HTTPException(status_code=404,
                                detail=f"No such screen; try {[s.name for s in SCREENS]}")
        ctx = await composer.context()
        html = document(screen.body(ctx), css, title=screen.title)
        if not name.endswith(".png"):
            return HTMLResponse(html)
        png = await composer.renderer.png(html)
        return Response(png, media_type="image/png",
                        headers={"Cache-Control": "no-store"})

    @app.get("/")
    async def index():
        return {
            "service": "trmnl-server",
            "version": __version__,
            "screen": composer.screen_name,
            "token": composer.token,
            "rendered_at": composer.rendered_at,
            "last_poll_at": composer.last_poll_at,
            "last_error": composer.last_error,
            "devices": sorted(registry.devices),
            "screens": [s.name for s in SCREENS],
        }

    return app
