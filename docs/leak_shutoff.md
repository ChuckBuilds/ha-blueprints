[All blueprints](../README.md)

# Leak detection - alert, countdown, shut off the water

`blueprints/automation/leak_shutoff.yaml`

A leak sensor going wet sends an actionable notification to every phone you
list and starts a countdown. If nobody answers before it expires, the water
main is shut off automatically.

The countdown is the safety net, not the mechanism. The notification carries a
**Shut off now** button that closes the valve immediately and a **Cancel**
button that leaves the water on. Not answering is the same as saying yes -
which is the right default, because the common failure mode at 3am is nobody
hearing the phone at all.

Built for a Flo by Moen shutoff, but works with any valve exposed as a `switch`
that is turned **off** to close.

## Behaviour

| Situation | What happens |
|---|---|
| Sensor goes wet | Every phone is alerted, countdown starts |
| Nobody answers | Valve closes when the countdown expires |
| **Shut off now** tapped | Valve closes immediately |
| **Cancel** tapped | Water left on, that sensor snoozes; others stay armed |
| Two sensors wet at once | One countdown each, both named |
| A second sensor while the water is already off | Quiet "also wet" note, no duplicate alarm |
| Valve does not confirm closed | Loud "SHUTOFF DID NOT CONFIRM - check the main" |
| A notify service is mistyped | Shutoff still happens; the failure is logged |
| Sensor rejoins the mesh already wet | Nothing - only a real dry-to-wet edge arms it |
| Home Assistant restarts | No detection while down; countdowns in flight are lost |

That second-to-last row is deliberate. A bare `to: "on"` trigger also matches
`unavailable -> on`, so a sensor that drops off the mesh and rejoins wet - or a
stuck sensor whose entity is re-added at startup - would arm a real countdown.
Nobody is watching their phone during an update. Requiring a definite
`off -> on` edge costs a rare missed alert and buys never shutting the water
off on a restart artefact.

## Inputs

| Input | Default | Notes |
|---|---|---|
| Leak sensors | - | `binary_sensor` entities with `device_class: moisture` |
| Water shutoff valve | - | A `switch`, turned **off** to close |
| Notification services | - | Full names, e.g. `notify.mobile_app_your_phone` |
| Countdown before shutoff | 2 min | The whole safety margin |
| Snooze after Cancel | 30 min | How long a cancelled sensor stays quiet |
| Snooze timer prefix | `timer.leak_snooze_` | See Install - needs helpers |
| Extra actions on shutoff | - | Siren, lights, tablet message |

## Install

Import the blueprint:

    https://github.com/ChuckBuilds/ha-blueprints/blob/main/blueprints/automation/leak_shutoff.yaml

Settings > Automations & scenes > Blueprints > Import blueprint, paste that URL.

**Create one timer helper per leak sensor** before you rely on Cancel. Home
Assistant blueprints cannot create helpers, so this step is manual. Each timer
is named `timer.leak_snooze_` + the sensor's object id:

    binary_sensor.kitchen_sink_water_leak
      -> timer.leak_snooze_kitchen_sink_water_leak

See `examples/helpers.yaml`, or Settings > Devices & services > Helpers >
Create helper > Timer. `examples/automations.yaml` shows the YAML form of the
automation itself.

Skipping the helpers is safe but degraded: alerts still fire and the water is
still shut off, only Cancel's snooze stops working. The blueprint says so in
the cancel confirmation and logs a warning naming the timer it wanted.

## Testing

Do this before you need it, not during a leak.

1. Developer Tools > States, set one leak sensor to `on`. Confirm every phone
   gets the alert with both buttons, and that it names the right sensor.
2. Tap **Cancel**. The water should stay on and the sensor's snooze timer
   should start counting down in the UI.
3. Set the same sensor wet again while the snooze runs - nothing should fire.
4. Let one run time out for real and confirm the valve actually closes. Knowing
   your valve answers a `switch.turn_off` is the entire point of the automation.

**Check which way your valve is modelled.** This blueprint turns the switch
**off** to close. If yours is inverted, it will open the main on a leak.
