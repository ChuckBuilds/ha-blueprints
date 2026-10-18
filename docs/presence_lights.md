# Presence-activated lights (multi-sensor, condition-aware)

`blueprints/automation/presence_lights.yaml`. Create one automation per area.

## Behaviour

| Event | What happens |
|---|---|
| Any sensor turns on, turn-on conditions pass | Lights on (at the set brightness, or untouched at 0), then your extra turn-on actions |
| Any sensor turns on, turn-on conditions fail | Your blocked actions instead, e.g. a 20% night-light |
| **Every** sensor clear, the last one for the full hold time, turn-off conditions pass | Lights off, then your extra turn-off actions |
| Home Assistant restart or automation reload | Waits the hold time, then runs the same "every sensor clear" check, so a dropped timer can't leave the lights on |

## Inputs

| Input | Default | Notes |
|---|---|---|
| Presence sensors | - | One or more. Mixing mmWave and PIR is fine |
| Lights | - | Lights, areas or devices |
| Hold time | 3 min | How long every sensor must stay clear |
| Brightness | 0 | 0 = don't touch brightness (Adaptive Lighting) |
| Turn-on conditions | - | All must pass to turn on. E.g. sun below horizon, sleep mode off |
| Turn-off conditions | - | All must pass to turn off. E.g. bed not occupied |
| Blocked / extra turn-on / extra turn-off actions | - | Anything that isn't a light |

Leave the optional fields empty for a plain motion light.

## Testing

`python tests/presence_lights_test.py` (headless Home Assistant, ~15 s). It
covers two sensors clearing at different times and a reload in the middle of the
hold time.
