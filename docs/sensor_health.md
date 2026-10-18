# Sensor health check (offline + low battery)

`blueprints/automation/sensor_health.yaml`

Finds a dead door sensor before the night the alarm needs it.

| Event | What happens |
|---|---|
| Daily, at the time you pick | One push + persistent notification listing every problem |
| A watched sensor offline for N minutes | Same report, right away |
| Everything healthy | The notification clears itself, no push |

Problems it finds:

- **offline**: the sensor is `unavailable` / `unknown`
- **low battery**: a battery sensor on the **same device** is below the
  threshold, or its "battery low" binary sensor is on. Pick the door sensor
  itself; its battery is found automatically.

| Input | Default | Notes |
|---|---|---|
| Sensors to watch | - | Doors, windows, motion, smoke, locks |
| Low battery below | 20 % | |
| Daily check at | 09:00 | |
| Alert when offline for | 30 min | 0 = daily check only |
| Phones to tell / Other notify action | - | |

Test: `python tests/extras_test.py`.
