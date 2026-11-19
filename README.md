# trmnl-server

Drives the TRMNL e-ink panel. A BYOS ("build your own server") implementation:
the device polls this service instead of trmnl.com.

## What the device actually does

A TRMNL is an ESP32-C3 behind a 7.5" 800×480 1-bit panel. It wakes, calls
`GET /api/display` with its MAC in an `ID` header, is told an image URL and how
many seconds to sleep, downloads the bitmap, and powers down again. It renders
no HTML and runs no JavaScript — the server hands it a finished picture.

The contract is Terminus':
<https://github.com/usetrmnl/terminus/blob/main/doc/api.adoc>

**It polls once a minute at best.** That is a hardware limit and it shapes
everything here: nothing on a screen may depend on being current to the second,
which is why there is no progress bar on the Listening screen and no live chat
window. It is also why `refresh_rate` is computed per poll rather than fixed —
see below.

## Screens

A priority stack, not a rotation. Every screen says whether it is eligible
right now and the highest-priority eligible one wins.

| Priority | Screen | Eligible when | Shows |
|---:|---|---|---|
| 1 | House | homelab-health is not `ok` **and** has findings | Failing findings worst-first, plus who is on Minecraft |
| 2 | Minecraft | at least one player is online | Online player names, current count, and players seen today |
| 3 | Listening | spotify-server reports audio actually moving | Dithered cover, track, artist, album |
| 4 | Now | always | Clock, date, weather icon, next two calendar events |

House and Minecraft are gated on there being something to say. An ungated
top screen would win every time and the others would never appear — the
ordering is only meaningful because those screens are conditional. Now is the
floor, so selection always has an answer.

Listening keys off `audio.playing` rather than `player.paused`: the first
reflects PCM actually moving through spotify-server, the second reflects the
last event librespot bothered to send.

## Refresh rate

Fast polls are only worth spending on a panel somebody can see, so
presence-server decides:

| Presence | Rate |
|---|---|
| `present` | 60 s |
| seen in the last 30 min | 60 s |
| `absent` | 900 s |
| `absent`, 23:00–06:00 | 1800 s |
| `unknown` (camera down) | 300 s |

Presence outranks the clock deliberately: being in the room at midnight is a
reason to keep the screen current; being out of it at noon is not.

So does having been there recently. Somebody who steps out for a moment comes
back to the panel, and a 15-minute sleep beginning the instant the room empties
is what makes it stale exactly when they return. The grace window
(`TRMNL_SERVER_PRESENCE_GRACE_S`, default 1800 s) is measured from
presence-server's `last_seen`, which it reports whether or not the room is
occupied — so it survives a restart of this service, and it outranks the night
window for the same reason `present` does.

`filename` is a content hash of the rendered bitmap. While it is unchanged the
device skips the download entirely, so an idle screen costs one JSON round-trip
a minute and no e-ink refresh at all.

## How a screen is built

```
Zone tree  ->  HTML + static/screen.css, 800x480 absolute px
           ->  Playwright screenshot (Chromium, held warm)
           ->  Pillow: L -> autocontrast -> Floyd-Steinberg -> 1-bit BMP
           ->  /var/lib/trmnl-server/images/<sha>.bmp
```

`layout.py` keeps the recursive `Zone` split from the original version. What it
lacked was a canvas: it emitted `vw`/`vh`/`cqi` units against no viewport, so
nothing had a size. Everything is absolute pixels now.

Composition runs on its own 30-second loop, never inside a poll. The HTML is
hashed before it is rendered, so Chromium only runs when the markup actually
changed, and the device's request is a dictionary lookup. When nothing has
polled for 30 minutes the loop stops rendering until something does.

Only `Noto Sans` and `Noto Sans Mono` exist on deploy1, and Playwright's
Chromium ships no fonts of its own — that stack is the whole of what is
available.

## Data sources

Each has a timeout and keeps its last good answer, so a service that goes down
degrades one screen rather than stalling the render.

| Source | Where | TTL |
|---|---|---|
| presence | `deploy1:3344/api/presence` | 20 s |
| spotify | `pi1:3339/v1/status` + Spotify Web API for art | 15 s |
| minecraft | `minecraft2:3343/v1/players`, `/v1/today` | 45 s |
| health | `homelab-health/health.py --json`, over ssh to sys1 | 5 min |
| weather | the weather skill's `accuweather.py`, imported | 1 h |
| calendar | the calendar skill's `icloud_calendar.py`, imported | 10 min |

Three of those are worth knowing about:

- **health runs on sys1, not locally.** Its config marks whichever host it was
  written for as local (`ssh: null`), so a local run on deploy1 would check
  deploy1 twice and sys1 not at all. Running it where the cron already runs it
  means one config and no drift. It also takes tens of seconds, so it lives on
  a background timer and `get()` only ever reads the cache.
- **weather has an hour-scale TTL on purpose.** The free AccuWeather tier is
  metered in tens of calls a day; a 25-second TTL would burn it before
  breakfast. The resolved location key is cached to disk so a restart does not
  spend another call.
- **calendar re-execs itself if mishandled.** `icloud_calendar.py` calls
  `os.execv` to relaunch under Monika's venv when `caldav` is missing — that
  would replace *this* process. `sources/calendar.py` sets the guard variable
  before loading it and imports `caldav` itself first, so that path turns into
  a plain `SystemExit`, which is caught. (`caldav` 2.1.0 imports `requests`
  without declaring it; both are pinned in `requirements.txt`.)

## Install

Runs on **deploy1:8015** as `User=tjohannessen`, not root — it reads
`~/.credentials/spotify.json`, imports the weather and calendar skill modules
out of `~/.claude/skills`, and ssh's to sys1. monika runs the same way on this
host for the same reasons.

```bash
cd ~/repos/home/trmnl-server
make deps        # venv + pip + `playwright install chromium`
make dryrun      # preview the copy
make install     # rsync, unit, firewall, restart
systemctl enable trmnl-server
```

`make deps` downloads Chromium into `~/.cache/ms-playwright` — the NFS home, so
it is shared by every host and only downloads once.

Before changing anything here, diff `/usr/local/bin/trmnl-server` against the
repo: deployed copies in this lab have been ahead before. Deploy only via
`make install`; never hand-place files under `/usr/local/bin/<service>`.

## Poking at it

```bash
make test                     # unit tests, no browser needed
make preview                  # every screen to ./data/preview as PNG *and* BMP
make debug                    # run on :8016 against ./data
make status                   # what it is showing right now
curl -s localhost:8015/api/display -H 'ID: aa:bb:cc:11:22:33' | python3 -m json.tool
```

`GET /api/screen` selects the highest-priority eligible screen and returns the
panel-ready 800×480 1-bit BMP directly. It is intended for an external
management server such as Terminus; `/api/display` remains the firmware JSON
contract. A Terminus extension can embed it as an image with
`<img src="http://deploy1.sflabs.local:8015/api/screen">`; the Terminus
container must be able to resolve and reach that URL. Since this endpoint
returns binary image data, put it in the extension markup rather than using it
as a JSON exchange URL. For an extension that requires a JSON exchange, use
`/api/screen.json` and put `{{ source_1.image_url }}` in the image `src`.
That adapter builds its image URL from the host used for the request, so using
the server's LAN IP avoids hostname-resolution surprises in a container.

`/preview/{house,minecraft,listening,now}` renders a screen as HTML in a normal browser;
add `.png` for the bitmap as the panel would actually get it. Looking at the
PNG alone is not enough — a layout that reads fine in greyscale can fall apart
once it is dithered to two colours.

Registered with portal as `trmnl` (lab group, order 45); it hot-reloads
`dashboards.json` on mtime, so no restart is needed. The service serves no TLS,
so portal's HTTPS shell marks it `mixed_content` and links out instead of
embedding it — give it an HTTPS port like presence-server's 3346 if that
matters.

Metrics dashboard at `/metrics`. The firmware sends battery, RSSI, firmware
version, wake reason and awake-time in the headers of **every** poll, so device
telemetry comes for free; gauges and the `poll` session kind carry it.

## Bring-up

The panel was previously pointed at the old server, but its MAC and configured
base URL are not recorded anywhere. So:

1. Start the service and watch `journalctl -u trmnl-server -f`.
2. Wait for a poll. The `ID` header is the MAC; the path it asks for tells you
   what the firmware expects.
3. If it is pointed somewhere this service is not, repoint it via the device's
   wifi captive-portal setup screen. `/api/setup` provisions it either way.

If the panel comes up as a photographic negative, set
`TRMNL_SERVER_INVERT=1` in the unit and restart.

`TRMNL_SERVER_WEATHER_LOCATION` ships set to `Flushing, NY`. It takes a place
name or `"lat,lon"`, exactly as the weather skill does. **Keep it quoted in the
unit file** — systemd splits `Environment=` on whitespace, so an unquoted
`Flushing, NY` silently becomes `Flushing,`. Setting it empty makes the Now
screen omit the weather block.
