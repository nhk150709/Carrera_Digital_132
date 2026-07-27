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
  and testable with no hardware at all;
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

### Run it

```bash
pip install -r requirements.txt
python -m uvicorn app.network.server:app --host 0.0.0.0 --port 8000
```

Open `http://<pi-address>:8000/` from any device on the network. By
default it runs against the built-in mock CU (six simulated cars) so you
can try the whole app immediately, with no track connected.

To use real hardware instead of the mock, wire up a `CarreralibCUClient`
(serial device path or the AppConnect adapter's BLE MAC address) in
`app/network/server.py`'s `build_default_session()`. **Read the docstring
in `app/cu/carreralib_client.py` first** -- writing a speed value to
addresses 0-5 (the six controller slots) is unconfirmed against real
hardware and is blocked by default; see
`docs/reference/protocol-notes.md`.

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

- **Writing a speed value to controller addresses 0-5**: the `carreralib`
  library allows it, but whether the CU firmware actually honors an
  external override for a slot with a live physical/wireless controller
  attached is unconfirmed. Confirmed-safe targets for software speed
  control are the autonomous car (6) and pace car (7) addresses.
- **Jump-start / early-movement detection**: the CU's own Status/Timer
  messages don't expose a live per-car throttle field, so this app can
  only detect it from (a) a locally-attached controller's own raw input,
  or (b) a dedicated Arduino start-line sensor sending `EARLY <addr>` --
  not from CU telemetry alone.
