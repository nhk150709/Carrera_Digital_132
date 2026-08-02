# Carrera Digital 132 — Controller Communication Project

Custom Arduino/microcontroller devices + a Python tool for a Carrera
Digital 132/124 slot-car track, built on the Control Unit's own PC-port
serial/BLE protocol. See [`CLAUDE.md`](CLAUDE.md) for the full project
brief and [`docs/reference/`](docs/reference/README.md) for the protocol
research this is built on.

## The app (`app/`) — a CU monitor + manual command console

**This app connects to the Control Unit, shows everything it reports
live, and lets you manually trigger any write the protocol supports so
you can see what happens.** No race management, no lap timing/ranking,
no controller-to-car assignment, no fuel/tyre simulation, no automated
driving of any kind -- that layer existed in an earlier version of this
app and was deliberately stripped out (its design is fully preserved in
[`CLAUDE.md`](CLAUDE.md)'s "Race manager" section for reintegration
later; the code itself is recoverable from git history). What's here now:

**Monitoring:**
- talks to the CU over serial or BLE (via `carreralib`) for real
  hardware, or a built-in simulator (`MockCUClient`) so it's usable with
  no track connected;
- a big, impossible-to-miss connection badge: **MOCK** (yellow, no real
  hardware), **CONNECTED** (green), or **DISCONNECTED** (red) -- plus the
  exact backend identity (which device/address), whether controller-
  address (0-5) writes are currently allowed, and a running connect-
  attempt counter, so it's never ambiguous whether you're looking at
  simulated or real data, or whether the connection actually dropped;
- decodes and shows every `Status` field live: `fuel[8]` (0-15 raw and
  as %), `pit[8]`, `start` (0-9 raw **and its confirmed meaning** -- see
  below), `mode` (bitmask, decoded into `FUEL_MODE`/`REAL_MODE`/
  `PIT_LANE_MODE`/`LAP_COUNTER_MODE`), `display`;
- a scrolling log of every `Timer` event (lap/sector crossing) as it
  arrives -- address, sector (translated to "start/finish" or "check
  lane N"), wall-clock time, and the CU's own raw timestamp;
- a scrolling **raw wire-level log**: carreralib's own DEBUG-level
  logging of literal send/receive bytes over serial, or raw BLE
  notification payloads, captured instead of only printed -- the actual
  data stream, not a paraphrase (empty against the mock backend, since
  nothing goes over a wire there);
- a scrolling **command log**: every manual write below, logged with
  whether it succeeded or was rejected and why.

**Manual commands** (one-shot -- each fires exactly once, exactly when
you click it; nothing runs automatically):
- per-address **speed**, **brake**, and **fuel-override** (0-15 each) --
  the direct way to test whether writing to a controller address (0-5)
  actually affects a car with a live physical controller plugged in, vs.
  the real controller just winning (addresses 6/7 -- autonomous/pace car
  -- are always allowed; 0-5 need `CARRERA_RMS_CU_ALLOW_CONTROLLER_
  WRITES=1`, see below);
- one button per CU **button ID** (START/ENTER, PACE CAR/ESC, SPEED,
  BRAKE, FUEL, CODE);
- **ignore(mask)** -- an 8-bit checklist telling the CU to ignore chosen
  controllers' own input entirely (unconfirmed against real hardware);
- **reset()** (CU's own internal timer) and Position Tower controls
  (`set_position`/`set_lap`/`clear_position`, no observable effect
  without that accessory attached).

There is **no readback for speed/brake/throttle anywhere in the
protocol** -- confirmed structurally, not just by omission: the CU's
`poll()` response has a fixed shape (8 fuel bytes + start + mode + pit +
display + checksum) with no room for one. The only way to confirm a
speed/brake write did anything is to watch the physical car/track, never
this page.

**Confirmed from real hardware**: the `start` field (0-9) -- `0` =
racing, `1` = stopped, `2..7` = the light sequence stepping up after
START/ENTER is pressed while stopped, back to `0` when it finishes. `8`/
`9` not yet observed. There is **no dedicated safety-car/pace-car mode
field** anywhere in the protocol; if pressing PACE CAR/ESC does anything
observable, it would show up as a change to `start`/`mode`/`display`,
which is exactly what the monitor is for watching.

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
addresses, starts "stopped" -- press the START/ENTER button in the
manual-command panel to see it flip to "racing" and start producing
Timer events) so the whole page is checkable with no track connected --
the badge will clearly say **MOCK** the whole time.

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

**If you see a `TimeoutError` from `bleak` (e.g. "Exception in thread
Thread-N" during connect) and the server seems to hang forever at
"Waiting for application startup"**: that hang is now fixed (see
`_construct_control_unit_with_timeout` in `app/cu/carreralib_client.py`) --
`carreralib`'s own BLE connection thread has no timeout of its own on the
underlying `bleak` connect, so a real connection failure previously left
the app stuck forever with no error and no retry. It now gives up on a
stuck attempt after 15s and retries (up to `ble_connect_attempts`, default
4) instead, and connecting no longer blocks the server from starting up at
all -- the page comes up immediately showing DISCONNECTED while connecting
retries in the background. The underlying `TimeoutError` itself usually
means one of: the CU/AppConnect adapter is out of range or powered off, or
it's already connected to something else (BLE is single-connection only --
e.g. the official Carrera app still open on a phone). Power-cycling the
CU/AppConnect adapter and retrying is usually enough.

**If you see `bleak.exc.BleakDBusError: [org.bluez.Error.InProgress]` and/or
`BleakError: failed to discover services, device disconnected`**: this
almost always means something else on the Pi is *also* holding or
attempting a BLE connection to the CU at the same time -- BLE only
supports one connection at a time. The most common cause is a leftover
server process from an earlier run that's still running in the
background (a telltale sign: if starting the server also fails with
`address already in use` on port 8000, something is already running).
Check and clean up first:

```bash
sudo lsof -i :8000        # or: ps aux | grep uvicorn
kill <pid>                 # the leftover process
ps aux | grep uvicorn      # confirm nothing's left
```

Also make sure nothing else -- a phone with the official Carrera app open,
a second terminal, `bluetoothctl` -- is connected to the CU/AppConnect
adapter at the same time. If it still happens with only one process
running, BlueZ itself can get stuck holding a phantom connection state
from an earlier failed attempt; clear it with
`sudo systemctl restart bluetooth` and retry.

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

**Testing controller-address (0-5) speed/brake writes.** Blocked by
default -- `set_speed`/`set_brake` to addresses 0-5 raise (and log to the
command log) instead of silently sending a command that may be ignored
by the hardware. Set `CARRERA_RMS_CU_ALLOW_CONTROLLER_WRITES=1` to try it
anyway once you're ready to test that specifically:

```bash
CARRERA_RMS_CU_ALLOW_CONTROLLER_WRITES=1 CARRERA_RMS_CU_DEVICE=auto ./run.sh
```

Addresses 6 (autonomous) and 7 (pace car) are always allowed regardless,
since there's no physical controller to fight there.

### Run the tests

```bash
pip install -r requirements.txt
pytest
```

`app/cu/mock_client.py` (including its simulated start/stop toggle),
`app/cu/protocol.py` (`describe_start()` and the confirmed value mapping),
and the monitor server's own logic (`MonitorState`, mode-bitmask decoding,
the raw log handler, `run_write()`'s success/rejection/exception paths,
and every `/api/cu/*` write endpoint) are unit/integration tested without
any hardware. `app/cu/carreralib_client.py`'s actual hardware I/O is
untestable in this environment by definition -- only its address-write
guard logic and connection-retry logic are covered.

## Open hardware questions (test before relying on them)

- **Writing a speed/brake value to controller addresses 0-5**: the
  `carreralib` library allows it (both `setspeed()` and `setbrake()`
  place no restriction beyond the protocol's own 0-7 address range), but
  whether the CU firmware actually honors an external override for a slot
  with a live physical/wireless controller attached -- versus the real
  controller's own input winning, or the two fighting each other -- is
  unconfirmed. Test it from the monitor's manual-command panel (see
  above, needs `CARRERA_RMS_CU_ALLOW_CONTROLLER_WRITES=1`) while someone
  actually holds that address's controller, and watch the physical car.
- **`ignore(mask)`**: an 8-bit bitmask telling the CU to ignore certain
  controllers' own input entirely -- per its docstring, may be the actual
  mechanism for cleanly handing an address to external control without a
  fight. Not independently confirmed. Also reachable from the manual-
  command panel.
- **Whether PACE CAR/ESC (or any other button) changes anything
  observable**: there's no dedicated safety-car/pace-car status field in
  the protocol at all. Press it from the "Buttons" panel and watch
  `start`/`mode`/`display` for any change -- that's the only way to find
  out, and nothing has confirmed an effect yet.
- **`Status.mode`'s `PIT_LANE_MODE` bit**: indicates whether a physical
  pit-lane adapter is even connected, i.e. whether `pit[]` means
  anything at all -- decoded and shown, not yet validated against an
  actual adapter.
- **`start` values 8/9**: documented range is 0..9, but only 0-7 have
  been observed so far (0=racing, 1=stopped, 2-7=light sequence -- see
  above). Whether 8/9 are reachable at all, and under what condition, is
  unknown.

See [`CLAUDE.md`](CLAUDE.md)'s "Race manager" section for the additional
open questions that only mattered for the now-removed race-management
layer (jump-start detection, safety car placement, ghost delta
continuity, etc.) -- still relevant if/when that layer is rebuilt.
