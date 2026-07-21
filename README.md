# Solar CYD Dashboard

A MicroPython project that turns a **CYD (Cheap Yellow Display)** — an ESP32 board with an
integrated 320×240 ILI9341 TFT — into a live dashboard for a home solar system. It polls an
Enphase Envoy gateway on the local network and displays current generation, consumption, and
net power, along with a scrolling line graph of recent history.

Written in MicroPython.

## Important note about versions

There is a TLS bug in MicroPython for ESP32 in versions above 1.25 (at the time of writing) —
see [micropython/micropython#16650](https://github.com/micropython/micropython/issues/16650).
It causes intermittent/consistent `OSError` failures during the HTTPS handshake this project
depends on. Use version 1.25 from
[micropython.org/download/ESP32_GENERIC](https://micropython.org/download/ESP32_GENERIC/).

## What it does

On boot, the device:

1. Connects to Wi-Fi using credentials from `secrets.py`.
2. Repeatedly (every 10 seconds) fetches `https://envoy.local/production.json` — the local status
   endpoint exposed by an Enphase Envoy/IQ Gateway — authenticated with a bearer token (see
   [Envoy authentication](#envoy-authentication) below). The Envoy resets plain HTTP connections
   on port 80 outright, so this has to be HTTPS.
3. Parses the JSON response to extract:
   - **Generating** — current solar production (`production[1].wNow`, the "eim" reading)
   - **Using** — current household consumption (`consumption[0].wNow`)
   - **Net** — the difference between the two
4. Renders the three values as text at the top of the screen using a large bitmap font.
5. Appends the latest generation/consumption values to a rolling history (last 64 samples) and
   redraws a two-line (green = generating, red = using) graph beneath the text, with a
   horizontal midline and W-scaled axis labels.
6. If the HTTP request fails (Envoy unreachable, timeout, etc.), the error is shown in the text
   area while the graph is left untouched, and the loop retries on the next cycle.

The whole thing runs forever in a `while True` loop — there's no button/touch interaction, it's
a passive read-only dashboard.

## File overview

| File | Purpose |
|---|---|
| `boot.py` | MicroPython entry point. Simply imports `solarDisplay` and calls `main()`. |
| `solarDisplay.py` | Application logic: Wi-Fi connection, polling the Envoy (via `envoy_auth`), and drawing the text readouts + history graph. |
| `envoy_auth.py` | Makes authenticated `GET` requests to the local Envoy over HTTPS (self-signed cert, verification off), attaching a pre-provisioned bearer token (`ENVOY_TOKEN` from `secrets.py`) as an `Authorization: Bearer` header. Retries a failed handshake up to 3 times on a fresh connection. |
| `secrets.py` | Wi-Fi credentials and the Envoy bearer token, imported by `solarDisplay.py` / `envoy_auth.py`. **Contains real, plaintext credentials — keep this file out of version control / public sharing.** |
| `template.secrets.py` | Blank template for `secrets.py` — copy this to `secrets.py` and fill in your own values when setting the project up fresh. |
| `lib/ili9341.py` | Driver for the ILI9341 TFT controller (SPI). Provides the `Display` class (`clear`, `draw_text`, `draw_text8x8`, `fill_rectangle`, `draw_hline`, `draw_line`, …) and the `color565()` RGB→RGB565 helper used throughout `solarDisplay.py`. |
| `lib/xglcd_font.py` | Loader for the `.c` bitmap font files in `fonts/`, used to render the large "Generating / Using / Net" text via `XglcdFont`. |
| `fonts/EspressoDolce18x24.c` | The one bitmap font actually used, for the readout text. |
| `pc_test/verify_envoy_auth.py` | Standalone CPython script (no MicroPython needed) that repeats the same HTTPS request as `envoy_auth.py`, for testing `ENVOY_TOKEN` and Envoy connectivity from a regular computer. Run with `python3 pc_test/verify_envoy_auth.py` from the project root. |

## Hardware

- **CYD (Cheap Yellow Display)** — ESP32 dev board with an onboard 2.8" 320×240 ILI9341 SPI TFT.
- Display SPI pins configured in `solarDisplay.py`: `SCK=14`, `MOSI=13`, `DC=2`, `CS=15`,
  `RST=15` (shared with CS), 40 MHz baud rate, rotated 90°.
- Backlight is driven from `Pin(21)` and switched on unconditionally at startup.
- Requires an [Enphase Envoy / IQ Gateway](https://enphase.com/) solar gateway reachable at
  `envoy.local` (or wherever it resolves via mDNS/local DNS) on the same network, over HTTPS
  (port 443). No outbound internet access is needed by the device itself — see below.

## Envoy authentication

Newer Envoy/IQ Gateway firmware requires a bearer token for local API access instead of allowing
plain unauthenticated requests (see Enphase's ["IQ Gateway Local APIs / UI Access Using
Token-Based Authentication" tech
brief](https://enphase.com/download/iq-gateway-local-apis-or-ui-access-using-token), and the
[Enphase-IQ-Gateway-access](https://github.com/DieWaldfee/Enphase-IQ-Gateway-access) project,
which documents the full Enlighten-login → token-exchange flow that produces this token).

An earlier version of this project had the CYD perform that login/exchange itself, over HTTPS to
`enlighten.enphaseenergy.com`. That reliably failed with TLS/heap-related `OSError`s — at the
time this looked like the ESP32 running out of heap mid-handshake against a large, CDN-fronted
certificate chain, but it later turned out to be the MicroPython version bug described above
(any TLS handshake was unreliable on that firmware, not just this one). Even so, doing the login
from a computer instead of the device is kept as the approach here: it avoids the CYD needing
public internet access and avoids storing your Enlighten account password on the device.

The easiest way to get the token: while logged in to
[enlighten.enphaseenergy.com](https://enlighten.enphaseenergy.com) in a browser, visit
`https://enlighten.enphaseenergy.com/entrez-auth-token?serial_num=YOUR_SERIAL_HERE` (see
`template.secrets.py`) — it returns the JWT directly. Copy that into `secrets.py` as
`ENVOY_TOKEN`. The token is long-lived (on the order of a year), so this is an infrequent,
manual step.

`envoy_auth.py` attaches the token as an `Authorization: Bearer <token>` header on a single
HTTPS request to the local Envoy. Plain HTTP (port 80) isn't an option — the Envoy resets those
connections outright. Certificate verification is left off (MicroPython's `ssl.wrap_socket`
doesn't validate by default), since the Envoy's cert is self-signed. As a defensive measure
against transient failures, `envoy_auth.py` retries a failed handshake up to `HANDSHAKE_RETRIES`
(3) times with a short delay between attempts — each retry opens a **brand new TCP connection**
rather than reusing the one that failed, since a socket that fails mid-handshake is left in a
corrupted state and further TLS attempts on it just produce different, more confusing errors.

## Setup

1. Flash MicroPython **v1.25** to the CYD board (see [Important note about
   versions](#important-note-about-versions) above).
2. Copy `boot.py`, `solarDisplay.py`, `envoy_auth.py`, the `lib/` and `fonts/` directories to the
   device.
3. Copy `template.secrets.py` to `secrets.py` and fill in your own Wi-Fi credentials, Envoy
   serial number, and bearer token (see [Envoy authentication](#envoy-authentication) above for
   how to get the token).
4. Ensure the Envoy is reachable as `envoy.local` on the same network.
5. Power on — the display shows a "Connecting to..." message, then switches to the live
   dashboard once data starts flowing.

You can sanity-check `secrets.py` before flashing anything by running
`python3 pc_test/verify_envoy_auth.py` from your computer — it makes the same authenticated
request as the device and prints the parsed generation/consumption values.

## Notes / quirks

- The graph autoscales its Y-axis to the maximum value seen across both generation and
  consumption in the current 64-sample window.
- History is capped at `MAX_HISTORY = 64` samples (~10.6 minutes at the 10-second poll interval).
