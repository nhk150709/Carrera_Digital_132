# Reference material index

Research notes on existing open-source / community projects that
communicate with the Carrera Digital 124/132 Control Unit (CU), gathered
while scoping this project. These are **notes and links**, not vendored
source code — check each project's license before copying any code from it.

| File | Project | Interface | Gives you |
|---|---|---|---|
| [`carreralib.md`](carreralib.md) | tkem/carreralib | PC port (serial or BLE via AppConnect) | fuel, pit, lap timer, pace/autonomous car control, race start/pause |
| [`pycarrera.md`](pycarrera.md) | predictive/pycarrera | PC port (TTL serial) | Race Monitor + REST API on top of the same protocol |
| [`CarreraDigitalControlUnit.md`](CarreraDigitalControlUnit.md) | tkem/CarreraDigitalControlUnit | Track rail tap (Arduino/mbed) | low-level command stream sent to cars |
| [`laser-drift.md`](laser-drift.md) | buntine/laser-drift | IR emulation (Linux/lirc) | remote car control only, no telemetry |
| [`carrera-platooning.md`](carrera-platooning.md) | sebastiankliem/carrera-platooning | none (on-car sensor only) | car-following demo, not CU comms |

See [`protocol-notes.md`](protocol-notes.md) for the consolidated technical
summary (connectors, voltages, message formats, addressing scheme, and the
single-connection limitation that drives this project's architecture).

Other sources referenced but not summarized in their own file (secondary /
background reading):

- Peter Niehues, "Carduino" — DIY Arduino CU write-up (German):
  http://www.wasserstoffe.de/carrera-hacks/
- slotbaer.de — independent German-language protocol documentation
  ("CU Daten-Protokoll", "D132 & D124 Daten-Protokoll", "CU Hardware"):
  http://slotbaer.de/carrera-digital-124-132/
- HPI Operating Systems & Middleware group — academic write-up of the rail
  digital signal and hand-controller ADC: https://osm.hpi.de/carrera/
