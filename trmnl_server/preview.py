"""Render every screen to a PNG and its 1-bit BMP, for eyeballing.

`make preview` writes into ./data/preview. Looking at the PNG is not enough --
the panel only has two colours, and a layout that reads fine in greyscale can
fall apart once it is dithered. Both are written for exactly that reason.
"""
import asyncio
import os
import sys

from .app import CSS_PATH
from .compose import Composer
from .config import Config
from .layout import document
from .render import ImageStore, Renderer
from .screens import SCREENS
from .sources.calendar import Calendar
from .sources.health import Health
from .sources.minecraft import Minecraft
from .sources.presence import Presence
from .sources.spotify import Spotify
from .sources.weather import Weather
from .telemetry import SCHEMA, Recorder


async def main():
    config = Config.from_env()
    out = os.path.join(config.data_dir, "preview")
    os.makedirs(out, exist_ok=True)
    css = open(CSS_PATH).read()

    metrics = Recorder("trmnl-server-preview", schema=SCHEMA, data_dir=config.data_dir)
    sources = {"presence": Presence(config, metrics), "spotify": Spotify(config, metrics),
               "health": Health(config, metrics), "minecraft": Minecraft(config, metrics),
               "weather": Weather(config, metrics), "calendar": Calendar(config, metrics)}
    renderer = Renderer(invert=config.invert)
    composer = Composer(config, metrics, renderer, ImageStore(out), sources, css)

    # Live data, so House is usually empty -- that is the honest preview.
    await sources["health"].refresh()
    await renderer.start()
    ctx = await composer.context()
    try:
        for screen in SCREENS:
            html = document(screen.body(ctx), css, title=screen.title)
            png = await renderer.png(html)
            with open(os.path.join(out, f"{screen.name}.png"), "wb") as handle:
                handle.write(png)
            with open(os.path.join(out, f"{screen.name}.bmp"), "wb") as handle:
                handle.write(renderer.bitmap(png))
            print(f"{screen.name:10} eligible={screen.eligible(ctx)!s:5} -> {out}/{screen.name}.png")
    finally:
        await renderer.stop()
        from .sources import http
        await http.close()
        metrics.close()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()) or 0)
