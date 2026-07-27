# tkem/carreralib

- **Repo**: https://github.com/tkem/carreralib
- **Docs**: https://carreralib.readthedocs.io/ · https://pythonhosted.org/carreralib/
- **Language/platform**: Python (pySerial for cable, `bluepy`/BlueZ for BLE — Linux only for Bluetooth)
- **License**: MIT (confirmed: `pip install carreralib` and check the
  package metadata — verified 2026-07, version 1.0.3)
- **Verified by installing it**: on 2026-07 this package was actually
  `pip install`ed and its source read directly (`carreralib.cu`), rather
  than relying on web research alone — see corrections below.

## What it does

The most complete open-source interface to the CU. Connects either:

- via **serial cable** (`/dev/ttyUSB0` on Linux, `COM3` on Windows) through
  the CU's PC port, or
- via **Bluetooth LE** using the official Carrera **AppConnect®** adapter
  (30369), device parameter is the adapter's MAC address.

`ControlUnit` is the main class; it "provides all features needed to
implement a custom race management system."

## Data / commands available (confirmed against `carreralib.cu.ControlUnit` source, v1.0.3)

- `Status`: `fuel` (8-item list, **0-15**, not 0-100), `start` (**0-9**
  state code for the CU's own built-in start-light sequence), `mode`
  (4-bit mask: `FUEL_MODE`, `REAL_MODE`, `PIT_LANE_MODE`,
  `LAP_COUNTER_MODE`), `pit` (8-bit mask), `display` (6 or 8).
- `Timer`: `address` (0-indexed by the library, wire format is 1-indexed),
  `timestamp` (32-bit ms counter, no defined epoch), `sector` — **1 means
  start/finish**, 2/3 mean Check Lane splits. (Earlier notes in this repo
  assumed 0 = start/finish; that was wrong — corrected here.)
- Zero-based addressing: `0–5` = controllers 1–6, `6` = autonomous car,
  `7` = pace car.
- `setspeed(address, value)`, `setbrake(address, value)`,
  `setfuel(address, value)` (value 0-15) all validate only `0 <= address
  <= 7` **in the library** — no special-casing that blocks addresses 0-5.
  This means the library will send the command; it does **not** prove the
  CU firmware honors an external override for a slot with a live
  physical/wireless controller attached versus just reporting what that
  controller is doing. Still genuinely unconfirmed — test on real
  hardware before relying on it. `setfuel` in particular is useful even
  before that's resolved: it can override the CU's own *displayed* fuel
  value per car, independent of the write-to-controller-speed question.
- `start()` presses the CU's own **START/ENTER** button
  (`START_ENTER_BUTTON_ID = 2`) — confirms the start/pause race capability
  used by SmartRace/PCLapCounter. Other named buttons: `PACE_CAR_ESC_BUTTON_ID
  = 1`, `SPEED_BUTTON_ID = 5`, `BRAKE_BUTTON_ID = 6`, `FUEL_BUTTON_ID = 7`,
  `CODE_BUTTON_ID = 8`, all playable via `press(button_id)`.
- `setpos(address, position)` / `setlap(value)` / `clrpos()` drive an
  official Carrera **Position Tower** rank-display accessory, if attached.
- No explicit rate limit found in the library itself; ~75ms between speed
  updates was a figure from secondary web sources, not confirmed in
  source. Treat as a reasonable default, not a verified hard limit.
- Connection device string: a MAC-address-shaped string (`aa:bb:cc:dd:ee:ff`
  or 5-dash-separated) selects the BLE backend (`bluepy`-based); anything
  else is treated as a serial device path.

## Relevance to this project

This is the reference implementation for the **PC-port serial protocol**
(see `protocol-notes.md`). Its message shapes (`Status`, `Timer`,
addressing scheme) are the model to replicate in Arduino/C++ firmware that
talks to the CU over TTL serial. It's also the only found open-source
example of driving the pace-car/autonomous-car address — directly relevant
to the "custom variable-speed pace car" goal.
