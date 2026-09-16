# ha-blueprints

Home Assistant automation blueprints and patterns.

## Door-aware auto-lock (resettable countdown)

`blueprints/automation/smart_auto_lock.yaml`

A replacement for a smart lock's built-in auto-lock. Instead of counting down
from the moment the lock was unlocked, it waits until the door contact sensor
reports the door is actually **closed**, then starts the countdown - and every
time the door is opened again, the countdown restarts. The deadbolt is never
driven into an open door, and it never fires "too soon" during a run of trips
in and out.

Built for August locks with DoorSense, but works with any lock plus a
`device_class: door` binary sensor.

### Behaviour

| Situation | What happens |
|---|---|
| Unlocked, door never opened | Locks after the normal countdown |
| Opened, closed, opened, closed | Countdown restarts on each close |
| Door standing open | Nothing - it waits |
| Guest mode on | Longer countdown |
| Party mode on | Never auto-locks; turning it off starts the countdown |
| Door sensor unavailable | Nothing locks (fail-safe, not fail-shut) |
| Lock command missed or jammed | Retried and verified against the lock state |
| Home Assistant restarts mid-countdown | Countdown resumes on start |

### Inputs

| Input | Default | Notes |
|---|---|---|
| Lock | - | The `lock` entity to close |
| Door contact sensor | - | `binary_sensor` with `device_class: door` |
| Normal countdown | 20 min | Minutes after the door closes |
| Guest mode countdown | 35 min | Used while the guest toggle is on |
| Guest mode toggle | - | An `input_boolean` |
| Party mode toggle | - | An `input_boolean` |
| Lock attempts | 3 | Retries if the lock does not confirm |

### Install

Import the blueprint:

    https://github.com/ChuckBuilds/ha-blueprints/blob/main/blueprints/automation/smart_auto_lock.yaml

Settings > Automations & scenes > Blueprints > Import blueprint, paste that URL.

Create the two toggles (see `examples/helpers.yaml`, or make them in the UI as
Helpers > Toggle), then create one automation per door from the blueprint.
`examples/automations.yaml` shows the YAML form.

**Turn off the lock's own auto-lock in the manufacturer's app.** Otherwise the
two schedules fight and you get the early locking this blueprint exists to fix.

### Testing

Set both countdowns to 0.5 minutes on one door, then walk through: unlock,
open, close (locks in 30 s); unlock, open, close, open (countdown cancels),
close (fresh 30 s); party mode on, open/close (no lock), party mode off
(countdown starts). Restore the real values afterwards.

Automation traces show which trigger fired and where a run is parked.

### Notes

- `mode: restart` is what makes the countdown resettable - each new trigger
  cancels the pending run. Do not change it to `single` or `queued`.
- Doors pointed at the same toggles share guest/party state. For independent
  control, create a second pair of helpers.
- An optional automation in `examples/automations.yaml` expires party mode
  after 6 hours.

## Bed-aware sleep mode (Adaptive Lighting safe)

`examples/sleep_mode.yaml`

A goodnight button that actually leaves the house dark, and a sleep mode that
clears itself when everybody is genuinely up rather than at a fixed hour. Not a
blueprint - a four-part pattern you copy and adjust, because the interesting
part is the shape rather than the entity names.

### How the pieces fit

The toggle is the wire. Nothing calls the goodnight steps directly; the button
writes to an `input_boolean` and a separate automation watches it. That
indirection is the whole design: button, dashboard, voice assistant and bed
sensors all set the same toggle, so every way of going to bed behaves
identically and a new one costs nothing.

```
 SOURCES             DECIDER              STATE           REACTOR           ACTIONS
 -------             -------              -----           -------           -------

bedside buttons -+
                 |   automation          input_boolean    automation        script
bed empty 10min -+-> sleep_mode_set ---->  .sleepmode ---> sleep_mode_apply -> .goodnight
                 |   "may it flip,        (on / off)      "it flipped,        |
07:00 clock -----+    and which way?"          ^           now what?"         +- AL sleep ON
                                               |               |              +- wait 5s
dashboard / voice -----------------------------+               |              +- lights off
                                                               |              +- porch to 25%
                                                               +- (off) --> AL sleep OFF
```

| Part | Its one job |
|---|---|
| `binary_sensor.bed_occupied` / `bed_sensors_trusted` | Turn two flaky load cells into two trustworthy facts |
| `automation.sleep_mode_set` | **Policy.** Who may flip the toggle, and when |
| `input_boolean.sleepmode` | **State.** Is the house asleep? |
| `automation.sleep_mode_apply` | **Reaction.** Notice the flip, dispatch |
| `script.goodnight` | **Steps.** The actual house-to-bed list |

`set` decides, `apply` reacts, `goodnight` does. When something misbehaves that
tells you which one to open.

The script exists rather than being inlined because two callers need it. An
automation that triggers on a state *change* never fires when an already-on
toggle is set on again, so a second button press at night is silently a no-op.
The button branch works around that by calling `script.goodnight` directly when
it can see the toggle will not move.

### Behaviour

What a button press does:

| Time | Sleep mode | Press does |
|---|---|---|
| 20:00-06:00 | off | Sets sleep mode, full goodnight |
| 20:00-07:00 | on | Lights off only, sleep mode untouched |
| 06:00-07:00 | off | Lights off only |
| 07:00-20:00 | on | Clears sleep mode (manual escape hatch) |
| 07:00-20:00 | off | Lights off only |

Sleep mode clears by itself when every side of the bed reads empty continuously
for 10 minutes, any time between 05:00 and 20:00, with the sensors trusted. The
07:00 trigger is a backstop, not the main path.

| Situation | What happens |
|---|---|
| One person up for the bathroom | Nothing - the other side still reads occupied |
| Both up for six minutes, back to bed | Nothing - the 10 minute timer is cancelled |
| Both up at 05:30 and stay up | Sleep mode clears at 05:40 |
| Up at 05:30, back to bed, press the button | Lights off, sleep mode stays on |
| Second press because a lamp survived | Goodnight runs again |
| Both up at 04:30 | Before the window - holds until the 07:00 backstop |
| Bed sensors dead for 36h | Neither auto path clears it; press between 07:00 and 20:00 |
| Toggle flipped from the dashboard | Identical result - the reactor watches the toggle |

### Install

Copy `examples/sleep_mode.yaml` to `config/packages/sleep_mode.yaml` and add to
`configuration.yaml`:

    homeassistant:
      packages: !include_dir_named packages

Then adjust the entity IDs: the two MQTT button topics, the bed occupancy
binary sensors, the light groups, and the Adaptive Lighting sleep-mode switch.
Reload scripts before reloading automations, or the automations will reference
a script that does not exist yet.

Works without bed sensors too - drop the `bed_empty` trigger and its branch and
keep the 07:00 backstop.

### Testing

Run `script.goodnight` from Developer Tools > Actions at any hour; it is
independent of the toggle, so you can tune the step list without waiting for
bedtime. Then watch the lights for a full ten seconds rather than one - the
failure this pattern exists to fix happens on the second after the lights go
out.

Temporarily drop the `bed_empty` trigger's `for:` to 30 seconds to exercise the
morning path, and set the time windows to whatever hour you are testing in.
Automation traces show which trigger fired and which branch was taken.

### Notes

- **Adaptive Lighting must be told about bedtime before the lights go off, not
  after.** Flipping AL's sleep-mode switch makes it force-adapt every light it
  still believes is `on`, and `light.turn_off` on a group returns as soon as the
  commands are dispatched - members keep reporting back for another half second
  or so. Turn the lights off first and AL re-lights them roughly a second later
  at `sleep_brightness`, which reads as "the goodnight button does not work".
  Recorded on one such night: group reported off at 21:56:13.5, AL flipped at
  21:56:13.3, bedside lamps back on at 21:56:14.7. The 5 second delay in the
  script is what keeps those apart. Do not reorder those two steps.
- `choose` is first-match-wins. The narrow daytime clear has to come before the
  broad "sleep mode is on" catch-all, or you can never clear sleep mode by hand.
- `for:` on a state trigger is a self-cancelling timer, which is what makes the
  brief-trip-out-of-bed case free. No timer helper, no cleanup.
- Bed occupancy fails towards occupied. `unavailable` and `unknown` both count
  as somebody in bed, because a light that fails to come on is a light switch
  away and a light that comes on at 7am is two people awake. The separate
  `bed_sensors_trusted` sensor is what stops a dead sensor being read as an
  empty bed forever.
- Brightness levels are not in this file. `sleep_brightness`, `min_brightness`
  and the rest live in the Adaptive Lighting config entry, edited only through
  Settings > Devices & services > Adaptive Lighting > Configure. When a light
  comes on at a brightness nothing in YAML asked for, that is where it came
  from.
