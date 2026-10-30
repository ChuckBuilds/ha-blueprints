# Presence-activated lights (multi-sensor, condition-aware)

`blueprints/automation/presence_lights.yaml`. Create one automation per area.

## Behaviour

| Event | What happens |
|---|---|
| Any sensor turns on, turn-on conditions pass | Lights on (at the set brightness, or untouched at 0), then your extra turn-on actions |
| Any sensor turns on, turn-on conditions fail | Your blocked actions instead, e.g. a 20% night-light |
| **Every** sensor clear, the last one for the full hold time, turn-off conditions pass | Lights off, then your extra turn-off actions |
| Home Assistant restart or automation reload | Waits the hold time, then runs the same "every sensor clear" check, so a dropped timer can't leave the lights on |
| Extended hold toggle on | The extended hold time replaces the hold time, e.g. 30 min during a party |
| Extended hold toggle switched off | Waits the normal hold time, then runs the same check, so rooms that emptied during the party go dark |

## Inputs

| Input | Default | Notes |
|---|---|---|
| Presence sensors | - | One or more. Mixing mmWave and PIR is fine |
| Lights | - | Lights, areas or devices |
| Hold time | 3 min | How long every sensor must stay clear |
| Brightness | 0 | 0 = don't touch brightness (Adaptive Lighting) |
| Turn-on conditions | - | All must pass to turn on. E.g. sun below horizon, sleep mode off |
| Turn-off conditions | - | All must pass to turn off. E.g. bed not occupied |
| Extended hold toggle | - | An `input_boolean`. While it is on, the extended hold time is used |
| Extended hold time | 30 min | How long every sensor must stay clear while the toggle is on |
| Blocked / extra turn-on / extra turn-off actions | - | Anything that isn't a light |

Leave the optional fields empty for a plain motion light.

### Party mode

Point the extended hold toggle of every shared-space room (kitchen, living
room, bar...) at one `input_boolean`, so a single switch keeps the house lit
while people are sitting still. The same toggle can drive the
[door-aware auto-lock](smart_auto_lock.md)'s party mode, so one switch also
keeps the doors unlocked. Pair it with an automation that turns the toggle off
overnight in case it is left on.

## Testing

`python tests/presence_lights_test.py` (headless Home Assistant, ~15 s). It
covers two sensors clearing at different times, a reload in the middle of the
hold time, and the extended hold toggle being on and then switched off.
