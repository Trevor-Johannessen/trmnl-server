# Verification

Run on sys1 against the live lab on 2026-09-12, before installing on deploy1.
The service was started on :8016 as `tjohannessen` with real source URLs.

## Unit tests

`make test` — **56 tests, all passing**. They cover the parts that are cheap to
get wrong and expensive to notice:

- **Screen selection** (`test_screens.py`) — the priority stack, and that House
  is gated on having findings. An ungated House would win every time and the
  other two would never appear, so there is an explicit test that a non-`ok`
  status with an empty findings list is *not* eligible. Also: a screen whose
  `eligible()` raises is skipped rather than fatal, and every screen still
  renders when every source is down (the state after a restart).
- **Refresh policy** (`test_refresh.py`) — the whole table, including that the
  midnight-wrapping night window is right at 23, 0, 5 and 6, and that presence
  outranks the clock.
- **Source degradation** (`test_sources.py`) — a timeout is bounded, a failure
  falls back to the last good answer marked stale, and a last good answer
  eventually expires. The device is waiting on the poll that triggers a render;
  a source that hangs must not become a missed poll.
- **Token stability** (`test_render.py`) — same bytes, same token. A token that
  changed every render would mean an e-ink refresh every minute forever.
- **The BYOS contract** (`test_api.py`) — the response shape the firmware
  depends on, header separators being interchangeable, `/api/display` not 500ing
  with no headers at all (which is what bring-up will actually look like), and
  that `/image/{token}` cannot be walked out of.

## Live checks

**Renders a real bitmap.** `file` on what the device would download:

```
PC bitmap, Windows 3.x format, 800 x 480 x 1, image size 48000,
cbSize 48062, bits offset 62
```

800×480×1 is exactly right, and 48062 = 800·480/8 + 62 bytes of header.
Pillow reports `mode=1`, two colours, `{0, 255}`.

**The device contract, end to end.** `/api/setup` provisioned a device and
returned a stable `api_key` across repeat calls. `/api/display` returned:

```json
{"status": 0, "filename": "3a03069bc525dfb1.bmp",
 "image_url": "http://.../image/3a03069bc525dfb1.bmp",
 "refresh_rate": 900, "update_firmware": false, "special_function": "none"}
```

`refresh_rate: 900` was correct, not a default: presence-server reported the
room `absent` at the time. `filename` was identical across three consecutive
polls. The image served with `Cache-Control: public, max-age=31536000,
immutable`. `/api/log` returned 204.

**Device telemetry is recorded.** A poll carrying the firmware's headers stored
them on the session and on the gauges:

```
gauges: screen=now, device=aa:bb:cc:11:22:33, refresh_rate=900,
        battery=91.2, rssi=-58.0, fw_version=1.5.2
```

Polls without those headers correctly record none rather than zeros.

**Real data reaches the screens.** `make preview` against the live lab produced
Now with the actual clock, live presence from presence-server, real weather and
two real iCloud events. House and Listening correctly reported `eligible=False` — the lab
was healthy and nothing was playing, which is the normal resting state.

**Weather resolves and renders.** With `TRMNL_SERVER_WEATHER_LOCATION` set to
`Flushing, NY`, the adapter returned `79F / Mostly cloudy / High 79F Low 70F`
and cached the resolved AccuWeather location key (`329592`) to
`weather-location.json`, so a restart does not spend another call against the
metered free tier. Note the value is quoted in the unit file: systemd splits
`Environment=` on whitespace, so an unquoted `Flushing, NY` would silently
become `Flushing,`.

**Dithering was eyeballed, not assumed.** A 640×640 photograph rendered into
the 300 px cover slot stays recognisable after Floyd–Steinberg. Album covers,
which are higher-contrast and more graphic, should do better.

## Not yet verified

- **The physical panel.** Everything above is the server holding up its end.
  Whether this device accepts it is the bring-up step in the README — its MAC
  and configured base URL are recorded nowhere, so the first real poll is the
  test. If the panel renders a negative, set `TRMNL_SERVER_INVERT=1`.
- **House with real findings.** The lab was healthy throughout, so House was
  only rendered from synthetic findings. To force it, stop a unit that
  homelab-health watches and wait one poll.

## Environment notes

- **No passwordless sudo on deploy1**, so `make deps` and `make install` are
  run by hand as root — the same as presence-server.
- **synology1's clock is about three hours ahead** of sys1 and deploy1, so
  files on the NFS home carry future mtimes and `make` warns about it on every
  run. Pre-existing, unrelated to this service, and harmless here — but it is
  why `make` prints `modification time ... in the future`.
