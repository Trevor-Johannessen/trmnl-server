"""Gather, choose, render -- on a timer, off the device's request path.

The panel polls once a minute at best, so nothing here needs to happen while it
waits. Keeping composition on its own loop means a slow upstream can never turn
into a missed poll, and `/api/display` is a dictionary lookup.

The HTML is hashed before it is rendered. Chromium only runs when the markup
actually changed, and the bitmap is only stored when the bytes changed, so a
screen that is sitting still costs nothing after the first pass.
"""
import asyncio
import base64
import logging
import time

from .layout import document
from .screens import SCREENS, Context, select

log = logging.getLogger(__name__)


class Composer:
    def __init__(self, config, metrics, renderer, store, sources, css):
        self.config = config
        self.metrics = metrics
        self.renderer = renderer
        self.store = store
        self.sources = sources
        self.css = css

        self.token: str | None = None
        self.screen_name: str | None = None
        self.rendered_at: float = 0.0
        self.last_poll_at: float = 0.0
        self.last_error: str | None = None
        self._html_hash: str | None = None
        self._task: asyncio.Task | None = None

    async def context(self) -> Context:
        presence, spotify, health, minecraft, weather, calendar = await asyncio.gather(
            self.sources["presence"].get(),
            self.sources["spotify"].get(),
            self.sources["health"].get(),
            self.sources["minecraft"].get(),
            self.sources["weather"].get(),
            self.sources["calendar"].get(),
        )
        ctx = Context(presence=presence, spotify=spotify, health=health,
                      minecraft=minecraft, weather=weather, calendar=calendar)
        if spotify.ok and spotify.get("playing") and spotify.get("art"):
            raw = await self.sources["spotify"].art_bytes(spotify.get("art"))
            if raw:
                ctx.art_uri = "data:image/jpeg;base64," + base64.b64encode(raw).decode()
        return ctx

    async def compose(self, force: bool = False) -> str | None:
        ctx = await self.context()
        screen = select(ctx, SCREENS)
        html = document(screen.body(ctx), self.css, title=screen.title)
        digest = self.store.token(html.encode())

        if not force and digest == self._html_hash and self.token and self.store.has(self.token):
            return self.token

        with self.metrics.session("render") as session:
            session.set(screen=screen.name)
            try:
                data, seconds = await self.renderer.render(html)
            except Exception as exc:
                self.last_error = f"{type(exc).__name__}: {exc}"
                log.exception("Render failed")
                session.fail(type(exc).__name__)
                self.metrics.event("render.error", level="error", message=type(exc).__name__)
                return self.token
            token = self.store.put(data)
            session.set(render_s=round(seconds, 3), bytes=len(data), token=token)

        self._html_hash = digest
        self.last_error = None
        self.rendered_at = time.time()
        if screen.name != self.screen_name:
            self.metrics.event("screen.changed", screen=screen.name,
                               previous=self.screen_name)
            self.screen_name = screen.name
        self.metrics.gauge("screen", screen.name)
        self.token = token
        return token

    # -- loop --------------------------------------------------------------

    def idle(self) -> bool:
        """Nobody has polled in a long time: stop rendering for a panel that is
        not listening. The next poll wakes it up again."""
        return (self.last_poll_at > 0
                and time.time() - self.last_poll_at > self.config.idle_after_s)

    async def loop(self):
        while True:
            try:
                if not self.idle():
                    await self.compose()
            except asyncio.CancelledError:
                raise
            except Exception:
                log.exception("Compose loop iteration failed")
            await asyncio.sleep(self.config.compose_interval_s)

    def start(self):
        self._task = asyncio.create_task(self.loop())
        return self._task

    async def stop(self):
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
