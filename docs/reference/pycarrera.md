# predictive/pycarrera

- **Repo**: https://github.com/predictive/pycarrera
- **Language/platform**: Python
- **License**: MIT

## What it does

Python bindings for the Carrera Digital Slot Car 132/124 Control Unit,
connecting via a **TTL-serial cable** (example uses `/dev/ttyUSB0`).
Protocol implementation credited to Stephan Heß's reverse-engineering work
(same source lineage as the `CarreraDigitalControlUnit` Arduino library and
slotbaer.de's protocol write-ups).

Adds on top of the raw protocol:

- A **Race Monitor** class that tracks race state.
- A **REST API** for querying the Race Monitor over HTTP.

## Relevance to this project

Second independent confirmation (alongside `carreralib`) that the CU's PC
port is a plain TTL-serial connection any microcontroller UART can read —
no special adapter chip required beyond a USB-serial bridge if going
through a PC/Pi, or a direct level-compatible UART on an Arduino.
