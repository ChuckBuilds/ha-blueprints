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
| A notify service is mistyped or a phone renamed | The other phones are still alerted and the shutoff still happens; the failure is logged |
| Sensor still `unknown` after a restart, first report is wet | Alerts and starts the countdown |
| Sensor rejoins the mesh already wet (`unavailable -> on`) | Nothing |
| Home Assistant restarts | No detection while down; countdowns in flight are lost |

The `unknown` and `unavailable` rows are deliberately different. After a
restart, most Zigbee leak sensors stay `unknown` until they next report, often
for hours, so requiring a dry-to-wet edge would ignore a real leak on all of
them for that whole time. A sensor whose first report is "wet" is almost always
really wet. A sensor dropping off the mesh and rejoining wet is where stale
readings come from, so that one is ignored.

Notifications run beside the countdown and the shutoff, never in front of
them. A missing notify action raises an error that `continue_on_error` cannot
catch, so it can only fail its own branch, not the valve.

**Tip: pick the phone *and* type its notify action.** Re-adding the server in the Companion app, logging in again or reinstalling it registers the phone as a new device, and a phone picked by device then gets no pushes. Its notify action name (`notify.mobile_app_<phone name>`) stays the same, so also type it under "Other notify action". Duplicates are removed, so you still get one push.

**Missing phone warning.** If a phone you picked is removed, or the Companion app registers again as a new device, the automation raises a persistent notification naming itself (checked at start, on reload and when a device is removed). Re-pick the phone to clear it.

## Inputs

| Input | Default | Notes |
|---|---|---|
| Leak sensors | - | `binary_sensor` entities with `device_class: moisture` |
| Water shutoff valve | - | A `switch`, turned **off** to close |
| Phones to notify | - | Pick Companion app phones. Safer than typing: the action name comes from the phone |
| Other notify actions | - | Optional typed names, e.g. `notify.family_phones`. Sent after the phones |
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
