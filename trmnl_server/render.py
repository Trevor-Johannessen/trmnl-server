"""HTML -> 800x480 1-bit BMP.

The panel wants a bitmap, not markup, and nothing in this repo ever produced
one. Chromium does the layout (so the Zone tree, flexbox and album art all work
the way they look in a browser) and Pillow does the bit reduction.

A cold Chromium launch is about a second. At one render a minute there is no
reason to pay that twice, so the browser and a single page are held open for
the life of the process and a lock serialises renders through them.
"""
import asyncio
import hashlib
import io
import logging
import os
import time

from PIL import Image, ImageOps

from .config import HEIGHT, WIDTH

log = logging.getLogger(__name__)


class Renderer:
    def __init__(self, *, invert=False):
        self.invert = invert
        self._lock = asyncio.Lock()
        self._playwright = None
        self._browser = None
        self._page = None

    async def start(self):
        from playwright.async_api import async_playwright

        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(
            args=["--disable-lcd-text", "--font-render-hinting=none",
                  "--force-color-profile=srgb", "--disable-dev-shm-usage"])
        self._page = await self._browser.new_page(
            viewport={"width": WIDTH, "height": HEIGHT}, device_scale_factor=1)
        log.info("Chromium ready")

    async def stop(self):
        for closer in (self._page, self._browser):
            if closer is not None:
                try:
                    await closer.close()
                except Exception:
                    log.exception("Error closing Chromium")
        if self._playwright is not None:
            await self._playwright.stop()
        self._playwright = self._browser = self._page = None

    async def png(self, html: str) -> bytes:
        """Screenshot the markup. Fonts must settle before the capture or the
        first render of a new face comes out in the fallback."""
        if self._page is None:
            raise RuntimeError("Renderer.start() was not awaited")
        async with self._lock:
            await self._page.set_content(html, wait_until="load")
            try:
                await self._page.evaluate("document.fonts.ready")
            except Exception:
                pass
            return await self._page.screenshot(type="png", full_page=False)

    def bitmap(self, png: bytes) -> bytes:
        """Greyscale, stretch the range so mid-tones survive, then dither.

        autocontrast matters for album art: covers that sit in a narrow band of
        greys turn into flat noise otherwise. Text screens are already pure
        black and white and pass through it unchanged."""
        image = Image.open(io.BytesIO(png)).convert("L")
        if image.size != (WIDTH, HEIGHT):
            image = image.resize((WIDTH, HEIGHT))
        image = ImageOps.autocontrast(image, cutoff=0)
        image = image.convert("1", dither=Image.Dither.FLOYDSTEINBERG)
        if self.invert:
            image = ImageOps.invert(image.convert("L")).convert("1", dither=Image.Dither.NONE)
        out = io.BytesIO()
        image.save(out, format="BMP")
        return out.getvalue()

    async def render(self, html: str) -> tuple[bytes, float]:
        started = time.monotonic()
        png = await self.png(html)
        data = await asyncio.to_thread(self.bitmap, png)
        return data, time.monotonic() - started


class ImageStore:
    """Content-addressed. The device is told a `filename`; while that token is
    unchanged it skips the download entirely, so an idle screen costs one JSON
    round-trip a minute and no e-ink refresh at all."""

    def __init__(self, directory: str, keep: int = 10):
        self.directory = directory
        self.keep = keep
        os.makedirs(directory, exist_ok=True)

    @staticmethod
    def token(data: bytes) -> str:
        return hashlib.sha256(data).hexdigest()[:16]

    def path(self, token: str) -> str:
        return os.path.join(self.directory, f"{token}.bmp")

    def has(self, token: str) -> bool:
        return os.path.exists(self.path(token))

    def put(self, data: bytes) -> str:
        token = self.token(data)
        path = self.path(token)
        if not os.path.exists(path):
            tmp = f"{path}.tmp"
            with open(tmp, "wb") as handle:
                handle.write(data)
            os.replace(tmp, path)
        else:
            os.utime(path, None)
        self.prune()
        return token

    def prune(self):
        try:
            files = [os.path.join(self.directory, name)
                     for name in os.listdir(self.directory) if name.endswith(".bmp")]
        except OSError:
            return
        for path in sorted(files, key=os.path.getmtime, reverse=True)[self.keep:]:
            try:
                os.remove(path)
            except OSError:
                pass
