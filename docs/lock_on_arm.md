# Lock the doors when the alarm is armed

`blueprints/automation/lock_on_arm.yaml`

Locks your doors once the alarm panel has **finished** arming. With Alarmo the
panel is `arming` during the exit delay and `armed_away` after it, so you're
never locked in (or out) while you're still heading out the door.

| Event | What happens |
|---|---|
| Panel reaches a picked armed state | Every picked lock that isn't locked gets `lock.lock` |
| 30 s later, a lock still isn't locked (jammed, offline, door open) | Push + persistent notification naming it and its state |
| Everything locked | Any earlier "did NOT lock" notification is cleared |

| Input | Default | Notes |
|---|---|---|
| Alarm panel | - | Alarmo, Manual, any `alarm_control_panel` |
| Locks | - | One or more |
| Lock when armed as | Away, Vacation, Night, Home | |
| Phones to tell / Other notify action | - | Type your phone's notify action too, so a re-registered phone still gets it |

Test: `python tests/extras_test.py`.
