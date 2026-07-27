# tkem/CarreraDigitalControlUnit

- **Repo**: https://github.com/tkem/CarreraDigitalControlUnit
- **Language/platform**: C++ (Arduino library + mbed OS)
- **License**: Apache License 2.0
- **Credited protocol research**: Stephan Heß and Peter Niehues

## What it does

A cross-platform library for interfacing a microcontroller directly with
the Carrera DIGITAL 124/132 system by tapping the **track rail signal**
(not the PC port) — no Carrera adapter hardware required, just wiring into
the two rail conductors.

## Hardware requirements

- Rail voltage is **14.8V (D132) / 18V (D124)** — too high for MCU GPIO.
  Requires a **resistor voltage divider** down to 5V/3.3V, plus an
  optional reverse-polarity protection diode. Wiring diagram is in the
  repo.
- Works on Arduino boards and mbed OS boards.

## Capabilities / limitations

- Decodes the digital command stream the CU sends to cars over the rail.
- The library's own documentation is explicitly **incomplete** — it points
  to the German-language protocol write-up on slotbaer.de ("CU Daten-
  Protokoll") for the full spec, and says "documentation leaves a lot to be
  desired." **Not confirmed** whether this rail-level stream exposes the
  same `fuel`/`pit` telemetry as the PC-port `Status` message used by
  `carreralib`/`pycarrera` — see `protocol-notes.md`.

## Relevance to this project

Primary candidate if the goal is a zero-extra-hardware rail tap (no
PC-Unit/AppConnect adapter). For features that specifically need
per-car fuel/pit status, the PC-port serial protocol (`carreralib`,
`pycarrera`) is the better-documented, lower-risk source — verify rail-tap
fuel/pit decoding experimentally before committing to it for that purpose.
