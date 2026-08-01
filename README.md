# Carrera Digital 132 — Controller Communication Project

Custom race-management app + Arduino/microcontroller devices for a Carrera
Digital 132/124 slot-car track, built on the Control Unit's own PC-port
serial/BLE protocol. See [`CLAUDE.md`](CLAUDE.md) for the full project
brief and [`docs/reference/`](docs/reference/README.md) for the protocol
research this is built on.

## The app (`app/`)

A Python race-management server -- runs on a Raspberry Pi or any other
machine with Python -- that:

- talks to the CU over serial or BLE (via `carreralib`) for real hardware,
  or a built-in simulator (`MockCUClient`) so the whole thing is usable
  and testable with no hardware at all -- which backend is actually active
  is always shown as a banner under the header (and in the debug tab), so
  it's never ambiguous whether you're looking at simulated or real data;
- GO presses the CU's own physical START/ENTER button (native light
  sequence, not an app-driven one) and starts lap timing once the CU's own
  `start` status field signals the sequence finished, so timing is
  synchronized with the real lights rather than a separately-guessed
  delay (heuristic -- see `app/network/server.py::_run_cu_synced_start`);
  "Quick Start" skips this and goes straight to running, for debugging
  without hardware;
- serves a browser-based dashboard (lap time, position, delta, penalties,
  fuel, big start/stop buttons, car/controller assignment, weather and
  debug panels) over one local web server -- every browser on the network,
  including the Pi's own screen, is just another client of the same race
  state, which is also what makes "others can access their own screen"
  work;
- accepts input from local gamepads (pygame) or from any browser
  (keyboard/touch), each tagged with its own controller ID, with a
  per-player throttle/brake sensitivity curve;
- runs Race mode (laps + ranking + time penalties) and Time Attack mode
  (fastest lap ranking);
- records a player's input over time and can replay it as a variable-
  speed "ghost" pace car;
- simulates fuel drain from tyre wear + acceleration (independent of the
  CU's own lap-time-based fuel simulation) and can push the result back
  to the CU's own fuel display;
- exposes a compact serial protocol for Arduino peripherals (fuel/pit
  panel, start lights, rank display, stop buttons, early-movement/jump-
  start sensor) -- see `app/network/arduino_api.py` and `arduino/` for
  example sketches.

Race-strategy layer on top of that core loop:

- **fuel/tyres**: a pre-race fuel *load* choice costs top speed while the
  tank is fuller, burning off as it's used. Fuel refuels during a pit
  stop (gradually, not instantly), and tyres are only actually changed
  once that refuel completes -- leave before it's full and you keep worn
  tyres, a real "splash and go" trade-off. Tyre wear visibly cuts top
  speed and braking as it climbs, not just fuel drain rate. Three
  compounds (soft/medium/hard) trade grip for wear rate. **Honesty note**:
  this whole simulation (fuel drain, tyre wear, refuel) only reflects
  reality for cars actually driven *through this app* -- a physical hand
  controller's throttle/brake is unreadable over the CU protocol
  (confirmed), so none of it runs for a car driven that way. The one
  fuel number that's real regardless is the CU's own `fuel[]` reading,
  shown separately on each car card and in the debug tab.
- **weather**: a track-wide grip cap (existing "weather mode") plus a
  separate per-car tyre/weather match bonus or penalty, and a lap-count-
  based forecast (`app/race/forecast.py`) -- scheduled against the race
  *leader's lap number*, not wall-clock time, with a calibrated confidence
  players have to gamble on (a "70% chance of rain by lap 20" forecast
  really is right ~70% of the time, not just flavor text).
- **strategy planning**: a pre-race plan per car (fuel load, compound,
  planned pit laps) with a lap-by-lap fuel/tyre projection graph (planned
  vs actual) in the UI, plus a "recommended" balanced default for
  newcomers, derived from the same simulation constants the race actually
  runs on (`app/race/strategy.py`).
- **push-to-pass**: a ~5s throttle boost triggerable from the player's own
  screen, at a heavy fuel/tyre cost and a cooldown (`app/race/overtake.py`).
- **safety car**: a virtual field-wide speed cap (works with zero extra
  hardware), or a real physical pace-car command if one is actually
  sitting on the track (`app/race/safety_car.py`) -- see the honesty note
  below on what triggering it actually does.
- **reliability**: a low-probability random breakdown forcing a car to a
  dead stop until it's serviced in the pit (`app/race/reliability.py`).
- **qualifying**: an optional mode ranked by best lap, producing a grid
  order for display -- entirely skippable, Race/Time Attack don't require
  it.
- **ghost delta**: live gap to a recorded lap, updated at each lap
  boundary (see the honesty note below on why it's not continuous).
- **sound/voice**: browser-native text-to-speech (Web Speech API -- free,
  offline, no API keys) plus optional user-supplied short clips for pit/
  repair/breakdown/final-lap/race-win events (`app/static/sound.js`).

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
default it runs against the built-in mock CU (six simulated cars) so you
can try the whole app immediately, with no track connected.

### Easiest way to run it (recommended for regular use/debugging)

```bash
cp .env.example .env   # then edit CARRERA_RMS_CU_DEVICE etc. inside it
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

**Read the docstring in `app/cu/carreralib_client.py` before relying on
controller writes.** Writing a speed/brake value to addresses 0-5 (the
six controller slots) is unconfirmed against real hardware -- it's
blocked by default and logged rather than silently doing nothing. Set
`CARRERA_RMS_CU_ALLOW_CONTROLLER_WRITES=1` to try it anyway once you're
ready to test that specifically; see `docs/reference/protocol-notes.md`
for why it's gated.

To enable the Arduino serial bridge, set `CARRERA_RMS_ARDUINO_PORT`
(e.g. `/dev/ttyACM0`) before starting the server.

### Run the tests

```bash
pip install -r requirements.txt
pytest
```

All of `app/race/*`, `app/controllers/*`, `app/cu/mock_client.py`, and the
Arduino protocol formatting are unit/integration tested without any
hardware. `app/cu/carreralib_client.py`'s actual hardware I/O is
untestable in this environment by definition -- only its address-write
guard logic is covered.

## Open hardware questions (test before relying on them)

- **Writing a speed/brake value to controller addresses 0-5**: the
  `carreralib` library allows it (both `setspeed()` and `setbrake()`
  place no restriction beyond the protocol's own 0-7 address range), but
  whether the CU firmware actually honors an external override for a slot
  with a live physical/wireless controller attached -- versus the real
  controller's own input winning, or the two fighting each other -- is
  unconfirmed. Confirmed-safe targets for software speed control are the
  autonomous car (6) and pace car (7) addresses. `carreralib` also exposes
  an `ignore(mask)` command (an 8-bit bitmask telling the CU to ignore
  certain controllers' own input entirely) that, per its docstring, may be
  the actual mechanism for cleanly handing an address to app control
  without a fight -- not yet used by this app, and not independently
  confirmed either; worth testing alongside the write-guard override.
- **Jump-start / early-movement detection**: the CU's own Status/Timer
  messages don't expose a live per-car throttle field, so this app can
  only detect it from (a) a locally-attached controller's own raw input,
  or (b) a dedicated Arduino start-line sensor sending `EARLY <addr>` --
  not from CU telemetry alone.
- **Safety car placement**: triggering the safety car only ever *commands*
  speed to whatever's already sitting at the pace-car address (7) -- the
  CU cannot place a car onto the track by itself. If `physically_present`
  is False (the default), triggering it only applies the field-wide
  virtual caution; a physical pace car has to be put on the track by hand
  beforehand for the "real car slows down" part to mean anything.
- **Ghost delta is lap-boundary, not continuous**: the CU only reports
  discrete lap/sector crossings, not continuous position, so the ghost
  comparison updates once per lap (or per Check Lane sector, if
  configured) -- not smoothly like a telemetry-based delta bar in a sim.
  True continuous tracking would need either Check Lane hardware or a
  separate continuous position source (e.g. a camera-based system).
