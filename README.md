# Carrera Digital 132 — Controller Communication Project

Custom Arduino/microcontroller devices + a Python tool for a Carrera
Digital 132/124 slot-car track, built on the Control Unit's own PC-port
serial/BLE protocol. See [`CLAUDE.md`](CLAUDE.md) for the full project
brief and [`docs/reference/`](docs/reference/README.md) for the protocol
research this is built on.

## The app (`app/`) — a read-only CU monitor

**This app currently does one thing: connect to the Control Unit and show
everything it reports, live, with nothing else attached.** No race
management, no lap timing/ranking, no controller-to-car assignment, no
fuel/tyre simulation -- that layer existed in an earlier version of this
app and was deliberately stripped out (its design is fully preserved in
[`CLAUDE.md`](CLAUDE.md)'s "Race manager" section for reintegration
later; the code itself is recoverable from git history). What's here now:

- talks to the CU over serial or BLE (via `carreralib`) for real
  hardware, or a built-in simulator (`MockCUClient`) so it's usable with
  no track connected;
- a big, impossible-to-miss connection badge: **MOCK** (yellow, no real
  hardware), **CONNECTED** (green), or **DISCONNECTED** (red) -- plus the
  exact backend identity (which device/address) and a running connect-
  attempt counter, so it's never ambiguous whether you're looking at
  simulated or real data, or whether the connection actually dropped;
- decodes and shows every `Status` field live: `fuel[8]` (0-15 raw and
  as %), `pit[8]`, `start` (0-9 raw), `mode` (bitmask, decoded into
  `FUEL_MODE`/`REAL_MODE`/`PIT_LANE_MODE`/`LAP_COUNTER_MODE`), `display`;
- a scrolling log of every `Timer` event (lap/sector crossing) as it
  arrives -- address, sector (translated to "start/finish" or "check
  lane N"), wall-clock time, and the CU's own raw timestamp;
- a scrolling **raw wire-level log**: carreralib's own DEBUG-level
  logging of literal send/receive bytes over serial, or raw BLE
  notification payloads, captured instead of only printed -- the actual
  data stream, not a paraphrase (empty against the mock backend, since
  nothing goes over a wire there);
- one manual "Reconnect" button/endpoint (`POST /api/reconnect`); the
  poll loop also retries on its own every 5s if the connection drops.

That's the entire feature set. No endpoint writes anything to the CU
(no speed/brake/fuel/start commands) -- this is deliberately read-only.

### Run it

Raspberry Pi OS (Bookworm and later) blocks system-wide `pip install`
(PEP 668, "externally-managed-environment") to protect the OS's own
Python tools. Use a virtual environment -- this is also just the right
way to run it regardless of that restriction:

```bash
cd Carrera_Digital_132
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m uvicorn app.network.server:app --host 0.0.0.0 --port 8000
```

If `python3 -m venv` itself fails with a missing-module error, install it
first: `sudo apt install python3-venv python3-full`.

Every new SSH session needs `source .venv/bin/activate` again before
`python -m uvicorn ...` (from inside the `Carrera_Digital_132` directory)
-- the venv doesn't stay active across logins. To avoid all of that and
have it just run persistently in the background (starts on boot, no
manual activation, restarts itself if it crashes), see
[`deploy/README.md`](deploy/README.md) for a systemd service.

Open `http://<pi-address>:8000/` from any device on the network. By
default it runs against the built-in mock CU (fuel/pit for 6 simulated
addresses, no Timer events since nothing ever presses the mock's own
start) so the page itself is checkable with no track connected -- the
badge will clearly say **MOCK** the whole time.

### Easiest way to run it (recommended for regular use/debugging)

```bash
cp .env.example .env   # then edit CARRERA_RMS_CU_DEVICE inside it
./run.sh
```

`run.sh` activates the venv, loads `.env` if present (the same file the
systemd service in `deploy/` reads), and starts the server -- one command
instead of remembering the activate/env-var/uvicorn sequence each time.
Add `CARRERA_RMS_CU_DEVICE=auto` to `.env` (see below) and you never have
to look up or paste in a MAC address again either.

### Connecting to the real CU (serial or the AppConnect BLE adapter)

Set `CARRERA_RMS_CU_DEVICE` before starting the server -- no code editing
needed. A serial device path (`/dev/ttyUSB0`) uses a wired connection; a
MAC-address-shaped string (`aa:bb:cc:dd:ee:ff`) uses the AppConnect BLE
adapter instead (`carreralib` picks the transport based on which shape
the string is); the special value **`auto`** scans for a BLE device
advertising the name `Control_Unit` (confirmed name of the AppConnect
adapter) and uses whatever address it finds -- no need to hardcode or
re-discover a MAC by hand:

```bash
CARRERA_RMS_CU_DEVICE=auto ./run.sh
```

This re-scans on every startup (a few seconds added to boot time) rather
than reusing a saved address, which sidesteps a real gotcha: BLE
addresses aren't guaranteed stable across power cycles or across
different machines (and on macOS they're not real MAC addresses at all --
see the note further down), so "auto" is more robust long-term than a
hardcoded value even though it's slightly slower to start.

**Finding the AppConnect adapter's BLE MAC address by hand** (only needed
if you want to skip the auto-scan and pin a specific address), from the
Pi:

```bash
python3 -c "
import asyncio
from bleak import BleakScanner

async def main():
    for d in await BleakScanner.discover(timeout=5.0):
        print(d.address, d.name)

asyncio.run(main())
"
```

Power-cycle the CU/AppConnect adapter right before running this so it's
easy to spot which entry is new. Once you have the address:

```bash
CARRERA_RMS_CU_DEVICE=aa:bb:cc:dd:ee:ff python -m uvicorn app.network.server:app --host 0.0.0.0 --port 8000
```

(or `CARRERA_RMS_CU_DEVICE=/dev/ttyUSB0` for a wired connection instead.)

**Before wiring this into the full app, test the raw connection on its
own first.** The BLE connection has no built-in timeout -- if the address
is wrong, the adapter's powered off, or it's out of range, connecting
will hang indefinitely with no error, and that's much easier to notice
and Ctrl+C out of in a two-line script than buried inside server startup:

```bash
python3 -c "
import carreralib
cu = carreralib.ControlUnit('aa:bb:cc:dd:ee:ff')
print(cu.version())
"
```

### Run the tests

```bash
pip install -r requirements.txt
pytest
```

`app/cu/mock_client.py`, `app/cu/protocol.py`, and the monitor server's
own logic (`MonitorState`, mode-bitmask decoding, the raw log handler,
its REST/WebSocket endpoints) are unit/integration tested without any
hardware. `app/cu/carreralib_client.py`'s actual hardware I/O is
untestable in this environment by definition -- only its address-write
guard logic and connection-retry logic are covered.

## Open hardware questions (test before relying on them)

- **Writing a speed/brake value to controller addresses 0-5**: the
  `carreralib` library allows it (both `setspeed()` and `setbrake()`
  place no restriction beyond the protocol's own 0-7 address range), but
  whether the CU firmware actually honors an external override for a slot
  with a live physical/wireless controller attached -- versus the real
  controller's own input winning, or the two fighting each other -- is
  unconfirmed. `carreralib` also exposes an `ignore(mask)` command (an
  8-bit bitmask telling the CU to ignore certain controllers' own input
  entirely) that, per its docstring, may be the actual mechanism for
  cleanly handing an address to external control without a fight -- not
  independently confirmed either. This monitor doesn't write anything to
  the CU at all, so neither is exercised by the current app; both are
  relevant again once/if the write-driving layer (pace car, race manager)
  comes back.
- **The CU's `start` field (0-9)**: only documented as "start light
  indicator" with no per-value meaning -- the monitor just shows the raw
  number live. Watching it during a real countdown (now easy, since it's
  right there on the page) is exactly how to figure out what the values
  actually mean.
- **`Status.mode`'s `PIT_LANE_MODE` bit**: indicates whether a physical
  pit-lane adapter is even connected, i.e. whether `pit[]` means
  anything at all -- decoded and shown, not yet validated against an
  actual adapter.

See [`CLAUDE.md`](CLAUDE.md)'s "Race manager" section for the additional
open questions that only mattered for the now-removed race-management
layer (jump-start detection, safety car placement, ghost delta
continuity, etc.) -- still relevant if/when that layer is rebuilt.
