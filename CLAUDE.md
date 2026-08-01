# Carrera Digital 132 — Controller Communication Project

This repo is for building custom Arduino/microcontroller devices and a
Python race-management app that talk to a Carrera Digital 132/124 slot-car
track's Control Unit (CU), for race-management features Carrera doesn't
sell (fuel-stop LED panel + pit animatronics, lap timer/ranking display,
derail stop buttons, custom variable-speed pace car).

Full detail and sources: [`docs/reference/`](docs/reference/README.md).
Run/setup instructions: [`README.md`](README.md).

## The app (`app/`) — currently a CU monitor, not a race manager

**As of the commit after `fce2d33`, this app was deliberately stripped
down to a read-only Control Unit monitor.** Per explicit request, all
race-management functionality (lap timing/ranking, controller-to-car
assignment, fuel/tyre simulation, strategy/weather/safety-car/overtake/
reliability/ghost/qualifying, the Arduino peripheral bridge, the browser
race dashboard) was removed from the running app — it wasn't reflecting
reality accurately enough on real hardware and was getting in the way of
just seeing what the CU actually reports. The **full previous
implementation is still in git history** (`fce2d33` and everything before
it has the complete race manager, fully working with 154 passing tests)
and the **complete design/logic is preserved below** in "Race manager
(removed — logic preserved for reintegration)" so it can be rebuilt from
this doc alone if git history isn't handy. Do not reintroduce any of that
logic into `app/` without being asked — the current app is monitor-only
by design, not by accident.

What actually runs now:

- `app/cu/` — hardware-agnostic CU client interface, a `MockCUClient`
  simulator (no hardware needed to develop/test against), and
  `CarreralibCUClient` wrapping the real `carreralib` package. Unchanged
  by the strip-down; this layer has no race-manager knowledge and never
  did.
- `app/network/server.py` — a minimal FastAPI app: connects to the CU
  (mock or real, same `CARRERA_RMS_CU_DEVICE` env var contract as
  before), polls it continuously (`MonitorState.poll_once()`, ~20Hz),
  and broadcasts a live snapshot over one WebSocket (`/ws`) to every
  connected browser: decoded `Status` (fuel[]/pit[]/start/mode/display,
  mode bitmask decoded), a rolling log of decoded `Timer` events, and a
  rolling **raw wire-level log** captured from carreralib's own DEBUG
  logging (`carreralib.cu`/`carreralib.ble`/`carreralib.connection`/
  `carreralib.serial` loggers, via `RawLogHandler`) — actual raw
  send/receive bytes over serial, or raw BLE notification payloads, not
  a paraphrase. `/api/state` (REST snapshot) and `/api/reconnect` (manual
  retry) exist alongside the WebSocket. No POST endpoint writes anything
  to the CU — this app never commands speed/brake/fuel/start on this CU,
  by design, since it's a monitor.
- `app/static/` — one plain HTML/CSS/JS page (`index.html` +
  `monitor.js` + `style.css`) rendering that snapshot live: a big
  connected/disconnected/mock badge, backend identity, a fuel/pit table
  per address, start/mode/display, a Timer event log, and the raw byte
  stream. No controller assignment, no race controls, no simulation of
  any kind.

Removed entirely (recoverable from git history at or before `fce2d33`):
`app/race/` (all race logic), `app/controllers/` (gamepad/browser player
input), `app/network/state_view.py`, `app/network/arduino_api.py`,
`app/network/schemas.py`, the old `app/static/app.js`/`sound.js`, and all
their corresponding tests. The `pygame` dependency (only needed for
`app/controllers/gamepad.py`) was dropped from `requirements.txt`; the
`arduino/` example sketches were left in place (harmless reference, but
they speak the now-removed `arduino_api.py` protocol so won't do anything
useful until/unless that bridge comes back).

Key facts learned by actually installing and reading `carreralib` 1.0.3's
source (more reliable than the web research below, which hit blocked
pages on this point):

- `ControlUnit.setspeed(address, value)` / `setbrake` / `setfuel` place
  **no address restriction beyond the protocol's own 0-7 range** — the
  library will happily send a command for addresses 0-5. This does **not**
  confirm the CU firmware honors it for a slot with a live physical/
  wireless controller attached (still unconfirmed, still needs a real-
  hardware test) — but it's less restricted than earlier research assumed.
  `CarreralibCUClient.set_speed()` blocks 0-5 by default; pass
  `allow_unconfirmed_controller_writes=True` to try anyway.
- `setfuel(address, value)` can **override** the CU's own displayed fuel
  value per car — this is how the app's custom fuel model can drive the
  real CU/LED fuel display instead of just reading it.
- Real `Timer.sector` values: **1 = start/finish** (not 0), 2/3 = Check
  Lane splits. `app/race/engine.py` uses its own sector==0-means-lap
  convention internally for simplicity/testability; the CU adapter
  translates 1→0 at the boundary.
- **Clock-domain rule, learned from a real bug on real hardware**: never
  seed `RaceEngine`'s per-car `last_crossing_timestamp` with this app's
  own clock (`session.clock()`/`time.monotonic()`). A real CU's `Timer`
  timestamps come back through `CarreralibCUClient._to_seconds()`, an
  entirely different, CU-internal domain with no fixed relationship to
  when `go()`/`resume()` was called — mixing the two domains produced
  wildly wrong (huge negative) lap times against real hardware, even
  though it looked fine against the mock (whose clock *is* the session's
  clock, masking the bug). `go()`/`resume()` now leave
  `last_crossing_timestamp` as `None`; the next sector-0 crossing
  becomes an unrecorded baseline, and only crossings *within the same
  reported domain* are ever subtracted from each other. Keep this
  invariant if touching engine.py — don't reintroduce clock mixing.
- The CU's `start` status field is a **0-9 state code** for its own
  built-in start-light sequence. Real firmware semantics per value are
  still **not confirmed** (carreralib's own docs just say "0..9 start
  light indicator"). The monitor just displays the raw value live; the
  removed race manager's GO-button-sync heuristic that interpreted it is
  documented in the "Race manager" section below.
- `press(PACE_CAR_ESC_BUTTON_ID)` simulates the CU's own Pace Car/ESC
  button; `setpos()`/`setlap()`/`clrpos()` drive an official Carrera
  **Position Tower** accessory, if one is ever added.
- **Full audit of everything `carreralib.cu.ControlUnit` exposes** (done
  by reading its entire source, not just the parts this app already
  used), in response to "is that all the information available, and what
  else can be inferred":
  - `ignore(mask)` — an 8-bit bitmask write command telling the CU to
    ignore the listed controller addresses' own physical/wireless input
    entirely. **Not yet used anywhere in this app, and not independently
    confirmed against real hardware** — but if it does what its one-line
    docstring says, it's the actual mechanism for cleanly handing an
    address over to app-driven control (`set_speed`/`set_brake`) without
    fighting a live driver's real controller, rather than just racing
    against it. Worth testing before relying on it for anything.
  - `reset()` — resets the CU's own internal timer. Not currently called
    by this app.
  - Button IDs beyond the two already used (`START_ENTER_BUTTON_ID`,
    `PACE_CAR_ESC_BUTTON_ID`): `SPEED_BUTTON_ID`, `BRAKE_BUTTON_ID`,
    `FUEL_BUTTON_ID`, `CODE_BUTTON_ID` — these simulate pressing the
    CU's own physical SPEED/BRAKE/FUEL/CODE buttons (global handicap
    levels, fuel-mode toggle, and wireless-controller pairing mode,
    respectively, based on what those buttons do on the real hardware —
    not independently confirmed via this library). Not used by this app.
  - **`Status.mode`'s bits aren't just informational** — `PIT_LANE_MODE`
    (`0x4`) specifically indicates whether a physical pit-lane adapter is
    even connected, i.e. whether `pit[]` means anything at all, versus
    just being a meaningless all-`False` array. The monitor decodes and
    displays the bit (`app/cu/protocol.py::PIT_LANE_MODE`,
    `app/network/server.py::_decode_mode()`) but doesn't act on it --
    the removed race manager's pit-sync logic that gated on it is
    documented below.
  - Nothing beyond `fuel[]`/`pit[]`/`Timer`/`start`/`mode`/`display`
    exists in the protocol at all — confirmed by reading every method on
    `ControlUnit`, not just the docstring table. In particular there is
    still no live throttle/brake/speed readback for a physically-driven
    car anywhere in the library, and no tyre-wear concept of any kind —
    both remain permanently unconfirmable/nonexistent by design, not
    just unimplemented.

## Race manager (removed — logic preserved here for reintegration)

Everything in this section describes code that **no longer runs** (removed
after commit `fce2d33`, which has the last full working copy with 154
passing tests — `git show fce2d33:app/race/fuel.py` etc. to read exact
source). Recorded here so it can be rebuilt from this doc alone. Rebuild
by re-adding `app/race/`, `app/controllers/`, `app/network/state_view.py`,
`app/network/arduino_api.py`, `app/network/schemas.py`, and wiring them
back into `app/network/server.py` (which is now the monitor-only file) --
either by restoring the pre-strip files from git history, or reimplementing
against the design below plus each subsystem's own honesty notes.

**Composition root**: `RaceSession` (`app/race/session.py`) owned one
`CUClient`, a `RaceEngine`, and one instance of each subsystem below;
`RaceSession.tick()` ran the whole per-frame loop in a fixed order (poll
CU timer events -> feed engine -> sync pit from CU -> advance forecast ->
check race-finished -> per app-driven-car: early movement / stop button /
overtake / breakdown / speed+brake commands / fuel-or-refuel / recording).
FastAPI's `app/network/server.py` ran this in a ~20Hz `tick_loop` and
broadcast `state_view.serialize(session)` over `/ws` to every browser
(the same "every browser is just another client of shared state" pattern
the monitor still uses).

**Race engine** (`app/race/engine.py`): state machine `IDLE -> COUNTDOWN
-> RUNNING -> PAUSED/FINISHED`, one `CarState` per address (laps,
penalties, jump_start, fuel, tyre_wear, in_pit, pending_tyre_change).
`handle_timer_event(address, timestamp, sector)`: sector != 0 (Check Lane
split) never completes a lap or sets the baseline; the first sector-0
crossing after `go()`/`resume()` is an **unrecorded baseline**
(`last_crossing_timestamp`), the next one is lap 1, timed from that
baseline. **Critical, hard-won invariant**: never seed that baseline with
this app's own clock (`session.clock()`) -- a real CU's `Timer`
timestamps are a separate, CU-internal clock domain
(`CarreralibCUClient._to_seconds()`, anchored to whenever the first real
Timer message happened to arrive) with no fixed relationship to when
`go()` was called. Mixing the two domains produced huge negative lap
times on real hardware while looking fine against the mock (whose clock
literally *is* the session's clock, which is what hid the bug for so
long). Ranking/delta/gap were derived from lap records, not read as CU
fields (the CU has no ranking concept). Penalties
(`app/race/penalties.py`): jump start = 5s, triggering a race stop = 10s,
both just appended `PenaltyRecord`s totaled into `elapsed_time` for
RACE-mode ranking.

**Fuel/tyre model** (`app/race/fuel.py`, `FuelConfig` defaults) --
**the most important honesty note of the whole subsystem: this entire
simulation only ever reflects reality for a car actually driven *through
this app's own controller input* (keyboard/gamepad/browser touch) — a
real Carrera hand controller's throttle/brake is unreadable over the CU
protocol (confirmed, see audit above), so none of this ever ran for a
physically-driven car.** The one number that's real regardless of driver
is the CU's own `fuel[]` reading (0-15 scale) -- the monitor still shows
that.
- `fuel_capacity=100`, `base_drain_per_second=0.6`,
  `throttle_drain_exponent=1.5`: `drain = 0 if throttle<=0 else
  base_drain_per_second + throttle**1.5 * base_drain_per_second * 2`, `*=
  boost_fuel_multiplier(2.5)` if push-to-pass active, `dt`-scaled. **Zero
  throttle must mean zero drain** -- an earlier version applied
  `base_drain_per_second` unconditionally every tick and fuel quietly
  drained to empty over a multi-hour idle session with the car never
  touched; a real, confirmed bug from an actual session, fixed by gating
  the whole drain expression on `throttle > 0`.
- `tyre_wear_cap=100`, `accel_wear_per_second=0.9`,
  `brake_wear_per_second=0.6`: `wear_gain = (throttle*0.9 + brake*0.6) *
  compound.wear_rate_multiplier`, `*= boost_tyre_wear_multiplier(2.0)` if
  boosting, `dt`-scaled, capped at 100.
- Compounds (`TyreCompound`/`CompoundProfile`): soft
  `(grip=1.05, wear_rate=1.6)`, medium `(1.0, 1.0)`, hard `(0.93, 0.6)`.
  Weather-match multiplier (`weather_match_multiplier`): dry->soft,
  damp->medium, wet->hard is the "right call"; matching gives `1.0 +
  0.08` bonus, each step of mismatch costs `0.12`, floored at `0.4`.
  Applied to both speed and braking.
- Weight penalty: `1.0 - max_weight_penalty(0.08) * (fuel/fuel_capacity)`
  -- a full tank costs up to 8% effective speed, burning off linearly as
  fuel is used.
- Tyre performance/brake multipliers: `1.0 - max_tyre_performance_drop
  (0.5) * wear_fraction**2` for speed, `1.0 - max_tyre_brake_drop(0.35) *
  wear_fraction**2` for braking -- quadratic, so wear barely matters
  until it's high, then falls off a cliff (deliberately, "how real tyres
  feel").
- **Refuel + deferred tyre change** (last design before removal, reversing
  an earlier "no mid-race refuel" decision per explicit request): a pit
  stop refuels at `pit_refuel_rate=20.0` fuel/second
  (`refuel_tick()`/`is_full()`) instead of instantly; the tyre change
  only actually fires once the refuel completes
  (`car.pending_tyre_change`, armed on pit entry, resolved on
  `is_full()`, cancelled if the car leaves before that -- a real "splash
  and go" trade-off, no free tyres for touching the pit box).
- `car.in_pit` was **auto-synced from the CU's own real `pit[]` telemetry**
  every tick (`RaceSession._sync_pit_from_cu()`), but only for the real
  backend (mock's `pit[]` never changes on its own) and only when
  `Status.mode & PIT_LANE_MODE` confirmed a physical pit-lane adapter was
  actually connected (otherwise `pit[]` is a meaningless all-`False`
  array). A manual `set_in_pit()` override existed for the mock / tracks
  without the adapter.

**Weather** (`app/race/weather.py`): a software-only grip cap since the
CU can't change physical track grip -- `WeatherMode.cap_speed()` scales
any commanded speed by a per-level `grip_multiplier` (dry 1.0, damp 0.8,
wet 0.6) and a `wear_multiplier` (1.0/1.3/1.6) applied on top of the tyre
wear formula above.

**Weather forecast** (`app/race/forecast.py`): scheduled against the race
*leader's lap count*, not wall-clock time (lap duration varies too much
by track/speed for a clock-based schedule to mean anything).
`generate_forecast()` picks `num_changes` random laps beyond lap 3, each
with a hidden `actual_level` and a *calibrated* `confidence` (uniform
0.5-0.9): the shown `predicted_level` equals the actual level with
probability == confidence, else a random other level -- so a "70%
confidence" forecast really is right ~70% of the time, not flavor text.
Only the prediction+confidence were ever exposed to players
(`visible_forecast()`); `actual_level` stayed hidden until reached.

**Strategy planning** (`app/race/strategy.py`): a pre-race
`RaceStrategy(fuel_load, compound, planned_pit_laps)` per car, plus
`project_plan()` -- a straight-line lap-by-lap fuel/tyre projection at
"typical" driving (`typical_throttle=0.75`, `typical_brake=0.35`, not
100% throttle) using the *same* per-lap rate formula
(`_per_lap_rates()`) as `recommend_strategy()`, so the UI's planned-vs-
actual graph and the "recommended" default could never contradict each
other. `recommend_strategy()`: fuel load = enough to cover the full race
at typical driving; one suggested pit lap at the point typical-driving
wear would cross `RECOMMENDED_TYRE_CHANGE_WEAR=65.0`.

**Push-to-pass** (`app/race/overtake.py`, `OvertakeConfig`): a
player-triggered ~5s (`duration_seconds`) boost, `boost_multiplier=1.18`
effective top speed, `cooldown_seconds=20.0`, at the fuel/tyre cost
multipliers noted above.

**Safety car** (`app/race/safety_car.py`, `SafetyCarConfig`):
`field_speed_cap=5` applied to every racing car's commanded speed while
active (works with zero extra hardware); if `physically_present=True`,
also sends `pace_car_speed=6` to the CU's pace-car address (7) -- **but
the CU cannot place a car onto the track by itself**, so this only means
anything if a physical pace car was manually put on the track first.
`random_trigger_chance_per_lap` (default 0, i.e. off) could trigger it
automatically per completed lap.

**Reliability/breakdowns** (`app/race/reliability.py`,
`ReliabilityConfig`): `breakdown_chance_per_second=0.0008` random chance
while driving, forces speed to 0 until repaired; `repair_seconds=8.0` of
continuous time with `car.in_pit=True` (progress reset if the car left
the pit mid-repair).

**Qualifying**: a `RaceMode.QUALIFYING` ranked by best lap instead of lap
count/elapsed time, producing a grid order (`RaceEngine.grid_order()`)
that could carry into a following Race-mode session. Entirely optional --
Race/Time Attack never required it.

**Ghost delta** (`app/race/ghost.py` + `recorder.py`): `InputRecorder`
logged a player's throttle/brake/lap/lane-change events over time as a
named `Recording`; `GhostComparator.delta_at_lap()` compared the live
car's elapsed time at a given lap number against the recording's elapsed
time at the same lap -- updated once per lap boundary (or Check Lane
sector, if configured), **not continuous** like a sim's live delta bar,
because the CU only reports discrete crossings, not continuous position.
The same recording could also drive `PaceCarPlayback` (`pace_car.py`) to
replay a run as a variable-speed pace car at the CU's pace-car address.

**Controllers** (`app/controllers/`): `GamepadController` (pygame, local
Xbox-style controllers) and `WebController` (per-browser-tab keyboard/
touch input pushed over the same `/ws` the state broadcast used, tagged
by `controller_id`), each with its own throttle/brake sensitivity curve
(`mapping.py`). `RaceSession.assign_controller(address, controller)` was
the only way a car's fuel/tyre/throttle simulation ever ran for it --
unassigned cars got lap timing only, straight from CU `Timer` events.

**Arduino peripheral bridge** (`app/network/arduino_api.py`): a compact
line-based serial protocol so external Arduino peripherals (fuel/pit LED
panel, start lights, rank display, stop buttons, an early-movement/jump-
start sensor) could stay in sync without their own CU connection --
per-tick outbound `STATE`/`FUEL`/`PIT`/rank lines, inbound `BTN STOP
<addr>` and `EARLY <addr>`. Matches the project's core architectural
constraint (see "Architecture implication" below): only one client can
ever be connected to the CU, so peripherals must go through this app's
one connection, never open their own. Example sketches are still in
`arduino/fuel_panel/` and `arduino/start_lights/` (now orphaned --
they speak this protocol, which no longer runs).

**GO-button CU sync** (was in `app/network/server.py::
_run_cu_synced_start`): pressed the CU's own START/ENTER button directly
(`cu.start()`, once -- `RaceSession.go(press_cu_start=False)` existed
specifically so the caller that already pressed it wouldn't double-press
when finalizing the state transition, since a double-press could
pause/re-trigger the CU if the button toggles) instead of running an
independent software 5-light countdown, then treated the first return to
`0` after a nonzero `start` value as "green" -- an explicitly-labeled,
unconfirmed heuristic, with a 20s timeout fallback (needed for the mock
CU, whose `start` is always 0 and would otherwise never trigger the
transition).

**Stop/resume also commanded the CU**: `RaceSession.stop()`/`resume()`
called `cu.start()` too (best-effort, `UnsupportedCommand` logged not
raised), on the inferred-but-unconfirmed assumption that the button
toggles pause/resume when a race is already running.

**Debug tooling**: a "Copy full status snapshot" button dumped the whole
serialized state as JSON to the clipboard (with a manual-select textarea
fallback for non-HTTPS LAN access, since the Clipboard API needs a secure
context); a `cu_backend` field + colored banner made mock-vs-real
unmistakable (the monitor kept this idea -- see `describe()` on
`CUClient`).

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
