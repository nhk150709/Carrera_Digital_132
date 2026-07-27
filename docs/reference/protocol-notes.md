# Carrera Digital 124/132 — Control Unit hardware & protocol notes

Consolidated facts gathered from community reverse-engineering projects (see
the per-project files in this folder for sources). Nothing here is official
Carrera documentation — treat voltage/timing numbers as "confirmed by
multiple independent sources," not as a datasheet.

## Two separate interfaces on the Control Unit (CU)

The CU exposes two electrically and logically different ways to get data
out of it. Projects in this folder tap one or the other — don't mix them up.

### 1. PC port (a.k.a. "Lap Counter" / "PC-Unit" port)

- A dedicated connector on the CU, historically used with Carrera's own
  **PC-Unit adapter (30432)** or third-party cables like Professor Motor's
  **PMTR6852**.
- Electrically: **TTL-level serial** (~5V logic) — directly compatible with
  a microcontroller UART (Arduino, ESP32, Pi), no level shifting needed
  (unlike the rail tap below).
- This is what `carreralib`, `pycarrera`, PCLapCounter, and SmartRace all
  use as their primary transport.
- Also reachable wirelessly via the **AppConnect Bluetooth LE adapter
  (30369)**, which plugs into the *same physical port* and re-exposes the
  identical protocol over BLE. **Only one client can be connected to this
  port at a time** — wired and AppConnect are mutually exclusive, and
  AppConnect itself accepts only a single simultaneous BLE connection (you
  cannot have the phone app and a Pi connected at once).
- Protocol is message-based (confirmed by installing `carreralib` 1.0.3
  and reading its source directly — see `carreralib.md` for full detail):
  - **Status** message: `fuel` (tuple of 8 ints **0-15**, one per
    address), `pit` (tuple of 8 bools), `start` (**0-9** state code for
    the CU's own start-light sequence, not a simple 0/1), `mode`, `display`.
  - **Timer** message: `address`, `timestamp` (ms), `sector` — emitted on
    every lap/sector crossing. **`sector == 1` means start/finish**, 2/3
    mean Check Lane splits (earlier draft of this doc guessed 0; that was
    wrong). Ranking/position is *derived* from these (no single "rank"
    field), not read directly.
  - **Addressing** is zero-based: `0–5` = controllers 1–6, `6` = the
    **autonomous car** slot, `7` = the **pace car** slot. `setspeed()` in
    the library accepts all of 0-7 with no extra restriction — but that
    only proves the library will *send* the command for 0-5, not that the
    CU firmware honors it over a live physical/wireless controller on
    that slot. Confirmed-safe for software speed control: 6 and 7 only.
  - Speed/command rate limit: ~75ms was a figure from secondary web
    sources; **not found in the `carreralib` source itself** — treat as a
    sensible default to use, not a confirmed hard limit.
  - Write-side commands exist too (not just polling) — e.g. `start()`
    (presses the CU's own START/ENTER button) to start/pause a race, as
    used by race-management tools like SmartRace and
    PCLapCounter to control the CU, not just read it.

### 2. Track rail signal (direct tap)

- The same 2-wire copper rail that supplies motor power to the cars also
  carries a **digital command signal** (car address, speed, lane-change,
  etc.) multiplexed for all cars, encoded as short low pulses (~50µs/100µs
  depending on bit value).
- Rail voltage is **14.8V (D132) / 18V (D124)** — this must be dropped to
  5V/3.3V with a resistor voltage divider (+ recommended reverse-polarity
  diode) before it touches a microcontroller pin. This is what
  `tkem/CarreraDigitalControlUnit` (Arduino/mbed) does.
- This tap gives you the low-level command stream the CU sends *to cars*.
  It has **not been confirmed** (by any source found) to carry the same
  rich `fuel`/`pit` telemetry that the PC-port `Status` message provides —
  the Arduino library's own docs are explicitly incomplete here. Treat this
  path as good for "what is the CU telling the cars right now," not as a
  drop-in replacement for the PC-port status feed.
- Wired hand controllers are read by the CU directly via ADC on their own
  wired ports (not via the rail); wireless hand controllers go through the
  wireless tower.

## Practical implication for multi-device builds

Because the CU's data port (wired or BLE) only serves **one connected
client at a time**, any build with several Arduino peripherals (LED panel,
lap timer, stop button, pace-car controller, etc.) cannot each open their
own independent connection to the CU. The working pattern used by every
serious project in this space (SmartRace, PCLapCounter, carreralib-based
tools) is a single **bridge/hub node** that owns the one CU connection and
fans the parsed data back out to other devices over a separate local
channel (I2C, UART bus, ESP-NOW/nRF24, etc.).
