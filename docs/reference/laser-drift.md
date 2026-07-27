# buntine/laser-drift

- **Repo**: https://github.com/buntine/laser-drift
- **Write-up**: https://dev.to/buntine/laser-drift-reverse-engineering-slot-cars-for-fun-and-no-profit
- **Language/platform**: Linux (lirc), USB IR transceiver (tested with
  USB-UIRT and irdroid devices)

## What it does

Emulates the **infrared wireless hand controllers** to remotely drive cars
(speed 0–15, lane change) for up to 4 players, over a TCP-controlled
server. Does **not** talk to the CU's PC port or rail at all — it replaces
the physical IR controllers by generating 38kHz IR signals via `lirc`.

## Capabilities / limitations

- Command-only: sets speed and lane-change state per player.
- Does **not** read telemetry — no lap times, fuel, or rankings come from
  this project.
- Requires a Linux host with `lirc` support and a USB IR transceiver — not
  Arduino-portable as-is (relies on `lirc`'s userspace stack).

## Relevance to this project

Not useful for the fuel/lap/ranking read-side goals. Only relevant if a
future feature needs to *drive* a car by emulating a hand controller
instead of going through the CU's own autonomous-car/pace-car address
(which `carreralib` shows is the simpler path — see `carreralib.md`).
