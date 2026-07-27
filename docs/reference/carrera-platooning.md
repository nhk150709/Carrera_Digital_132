# sebastiankliem/carrera-platooning

- **Repo**: https://github.com/sebastiankliem/carrera-platooning
- **Language/platform**: Arduino Nano

## What it does

A university project implementing car-following ("platooning") on Carrera
Digital 132: an Arduino Nano on board the car reads a VL53L0X time-of-flight
sensor to measure distance to the car ahead, and runs a PID loop to adjust
motor PWM directly.

## Relevance to this project

Tangentially related only — it does **not** communicate with the CU at
all (no rail tap, no PC port). The on-board Arduino drives the car's own
motor directly, using diodes to protect against back-EMF disrupting the
rail signal. Not a source for CU protocol details; noted here only because
it came up in the same research pass and shows an alternative "put a brain
on the car itself" pattern, if that's ever relevant to a future car-mounted
feature.
