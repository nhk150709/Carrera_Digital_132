# Carrera Digital 132 — Controller Communication Project

This repo is for building custom Arduino/microcontroller devices that talk
to a Carrera Digital 132/124 slot-car track's Control Unit (CU), for
race-management features Carrera doesn't sell (fuel-stop LED panel + pit
animatronics, lap timer/ranking display, derail stop buttons, custom
variable-speed pace car). The repo currently has no firmware yet — the
research below is the foundation the firmware should be built on.

Full detail and sources: [`docs/reference/`](docs/reference/README.md).

## Key facts (see `docs/reference/protocol-notes.md` for full detail)

The CU exposes **two different interfaces** — don't conflate them:

1. **PC port** (used by Carrera's PC-Unit adapter 30432, or by any USB-TTL
   serial cable): plain **TTL serial**, directly Arduino-UART-compatible,
   no level shifting. Also reachable wirelessly via the official
   **AppConnect BLE adapter (30369)**, same protocol over BLE. This is the
   well-documented path (`carreralib`, `pycarrera`) and gives:
   - `Status`: `fuel[8]`, `pit[8]`, `start`, `mode`, `display`
   - `Timer`: `address`, `timestamp`, `sector` (lap crossings — ranking is
     derived from these, not a direct field)
   - Addressing: `0–5` = controllers 1–6, `6` = autonomous car, `7` =
     pace car — both **commandable** (speed etc.) over this same
     connection, rate-limited to ~75ms between updates
   - Write commands exist too (e.g. start/pause a race), confirmed via
     `carreralib`'s `start()` and use by SmartRace/PCLapCounter
   - **Only one client can be connected at a time** (wired and BLE are
     mutually exclusive; BLE itself is single-connection only — this is
     the biggest architectural constraint for this project, see below)

2. **Track rail tap** (used by `tkem/CarreraDigitalControlUnit`, Arduino/
   mbed): direct tap of the two power rails, needs a resistor voltage
   divider (rail is 14.8V D132 / 18V D124 → 5V/3.3V). Gives the raw
   command stream sent to cars. **Not confirmed** to carry `fuel`/`pit`
   telemetry the way the PC port does — treat as unproven for that until
   tested.

## Reference projects found

| Project | Interface | License | Notes |
|---|---|---|---|
| [tkem/carreralib](https://github.com/tkem/carreralib) | PC port, serial or BLE | — | most complete; Python; source of the `Status`/`Timer`/addressing model above |
| [predictive/pycarrera](https://github.com/predictive/pycarrera) | PC port, TTL serial | MIT | Race Monitor + REST API |
| [tkem/CarreraDigitalControlUnit](https://github.com/tkem/CarreraDigitalControlUnit) | Rail tap | Apache-2.0 | Arduino/mbed; docs incomplete |
| [buntine/laser-drift](https://github.com/buntine/laser-drift) | IR emulation (Linux/lirc) | — | control-only, no telemetry |
| [sebastiankliem/carrera-platooning](https://github.com/sebastiankliem/carrera-platooning) | none (on-car sensor) | — | tangential, no CU comms |

Details, licenses to re-verify, and secondary German-language sources
(slotbaer.de, wasserstoffe.de, osm.hpi.de) are in
[`docs/reference/`](docs/reference/README.md).

## Architecture implication for this project's roadmap

Because the CU only serves one connected client, a build with multiple
devices (LED panel, lap timer, stop buttons, pace-car controller) must use
a **single bridge/hub node** that owns the one CU connection (via PC port
serial — BLE only if a wireless link is specifically needed) and fans
parsed events out to the other Arduino nodes over a separate local channel
(I2C, UART bus, ESP-NOW/nRF24, etc.). Do not design any node to open its
own independent connection to the CU.

## Planned devices (from initial project scoping)

1. **Fuel/pit LED panel** — shows which car is refueling and animates its
   gauge. Source: bridge node's `Status.fuel`/`Status.pit`, keyed by
   address. Prefer PC-port serial over rail tap here since fuel/pit is
   confirmed only on that path.
2. **Pit animatronics** — servos for a mechanic figure (refuel + tyre
   change), triggered off the same `pit[]` edge transitions as #1. Pure
   downstream logic, no new CU comms.
3. **Lap timer / ranking display** — from `Timer` messages (address,
   timestamp, sector) via the bridge node; ranking computed locally from
   lap counts/times, not read as a field.
4. **Derail stop buttons (4–5 players)** — send a stop/pause command to the
   CU (`start()`-style) on button press. This is Arduino-only: no BLE or
   Raspberry Pi required. If buttons are spread around a large table,
   prefer wired multi-drop or 2.4GHz (nRF24L01/ESP-NOW) over BLE for
   simplicity/cost — BLE's single-connection limit on the CU side is
   irrelevant here since buttons talk to the bridge node, not the CU
   directly.
5. **Custom variable-speed pace car** — use the CU's existing pace-car
   address (`7`) / autonomous-car address (`6`) and send it a speed
   profile over time from the bridge node. This is a software feature on
   top of the standard PC-port protocol, not a hardware modification —
   `carreralib` is the reference implementation to port the addressing/
   speed-command logic from.

None of the five require a Raspberry Pi or BLE by necessity — Arduino +
PC-port TTL serial covers all of them. BLE (AppConnect) is an optional
alternate transport for the bridge node only, useful for a cable-free hub,
not for talking to multiple peripherals — and a bare Arduino Uno/Nano has
no BLE radio, so that would need an ESP32/Nano 33 BLE-class board anyway.
