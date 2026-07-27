# tkem/carreralib

- **Repo**: https://github.com/tkem/carreralib
- **Docs**: https://carreralib.readthedocs.io/ · https://pythonhosted.org/carreralib/
- **Language/platform**: Python (pySerial for cable, `bluepy`/BlueZ for BLE — Linux only for Bluetooth)
- **License**: check repo (not confirmed here — verify before vendoring code)

## What it does

The most complete open-source interface to the CU. Connects either:

- via **serial cable** (`/dev/ttyUSB0` on Linux, `COM3` on Windows) through
  the CU's PC port, or
- via **Bluetooth LE** using the official Carrera **AppConnect®** adapter
  (30369), device parameter is the adapter's MAC address.

`ControlUnit` is the main class; it "provides all features needed to
implement a custom race management system."

## Data / commands available

- `Status`: `fuel` (8-tuple), `pit` (8-tuple of bool), `start`, `mode`,
  `display`.
- `Timer`: `address`, `timestamp` (ms), `sector` — one message per
  lap/sector crossing.
- Zero-based addressing: `0–5` = controllers 1–6, `6` = autonomous car,
  `7` = pace car — both programmatically commandable (speed etc.), which is
  how Carrera's own ghost-car/pace-car features work.
- Command/write side confirmed to exist (e.g. `start()` to start/pause a
  race), not just polling — this is what lets tools like SmartRace and
  PCLapCounter drive the CU, not just read it.
- Speed/command updates are rate-limited to ~75ms apart.

## Relevance to this project

This is the reference implementation for the **PC-port serial protocol**
(see `protocol-notes.md`). Its message shapes (`Status`, `Timer`,
addressing scheme) are the model to replicate in Arduino/C++ firmware that
talks to the CU over TTL serial. It's also the only found open-source
example of driving the pace-car/autonomous-car address — directly relevant
to the "custom variable-speed pace car" goal.
