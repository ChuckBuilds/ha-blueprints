# ha-blueprints

Home Assistant automation blueprints.

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

## Leak detection - alert, countdown, shut off the water

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
## Bed-exit predictive bathroom lights

`blueprints/automation/bed_exit_bathroom_lights.yaml`

A motion-activated bathroom light that starts **before** the motion sensor
could possibly see you.

If your night-time bathroom light always feels a step behind, the automation is
probably not the problem. A PIR cannot report you until you are already in the
room and inside its field of view, and most battery PIRs then go blind for a
cooldown period. Shaving milliseconds off the automation cannot fix a sensor
that has not fired yet.

So this stops waiting for the PIR. A bed occupancy sensor releases a second or
two after you sit up - several seconds before you reach the bathroom door - and
that is the head start. The bed going empty brings the light up immediately,
then waits for motion to confirm the guess. No motion, no harm: the light backs
itself out.

The pre-light waits for the *last* person out. Lighting up while someone is
still in bed just shines on the person you are trying not to wake, and they are
not the one heading for the bathroom anyway.

Brightness is decided once and used for both the pre-light and the motion that
follows, so walking in never changes what you are already looking at. A 3am trip
is dim; a morning get-up is already at full brightness before you reach the
door.

Works with any bed occupancy sensor that releases promptly (ESPHome load cells
or pressure mats, Sleep Number, Withings, a mmWave sensor aimed at the bed).

### Behaviour

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
| Last person leaves the bed at 3am | Dim pre-light immediately, before any motion |
| Last person leaves the bed at 7:30am | Full brightness pre-light - walk into a lit room |
| One person up, partner still in bed | No pre-light, and the visit stays dim |
| Motion follows the pre-light | Same brightness it was already at, no jump |
| Pre-light guessed wrong | Switches itself back off after the confirm window |
| Rolled over, both still in bed | Nothing - the sensor never released |
| Night mode still on at 08:00 | Full brightness anyway, once the bed is empty |
| Motion, bed empty, night mode off | Full brightness group |
| Light already on when bed empties | Left alone - someone is using the room |
| Motion returns during an off delay | Delay cancelled, lights stay up |
| Second person gets up | Restarts cleanly, no duplicate runs |

### Inputs

| Input | Default | Notes |
|---|---|---|
| Leak sensors | - | `binary_sensor` entities with `device_class: moisture` |
| Water shutoff valve | - | A `switch`, turned **off** to close |
| Notification services | - | Full names, e.g. `notify.mobile_app_your_phone` |
| Countdown before shutoff | 2 min | The whole safety margin |
| Snooze after Cancel | 30 min | How long a cancelled sensor stays quiet |
| Snooze timer prefix | `timer.leak_snooze_` | See Install - needs helpers |
| Extra actions on shutoff | - | Siren, lights, tablet message |
| Bathroom motion sensor | - | `binary_sensor`, occupancy or motion |
| Bed occupancy sensors | - | One per side; any release starts a pre-light |
| Night mode toggle | - | An `input_boolean` you flip at bedtime |
| Night starts | 21:00 | Earliest night mode may dim the bathroom |
| Night ends | 07:00 | After this, full brightness once the bed is empty |
| Dim light | - | Single fixture used at night, and pre-lit |
| Full brightness lights | - | Daytime group; a light group is fine |
| Pre-light brightness | 8% | Night pre-light only; keep it low |
| Confirmed night brightness | 20% | After motion backs up the guess |
| Confirmation window | 90 s | How long a pre-light waits for motion |
| Night off delay | 3 min | No-motion delay while night mode is on |
| Extra daytime delay | 5 min | Added on top when night mode is off |

### Install

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

### Testing

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
    https://github.com/ChuckBuilds/ha-blueprints/blob/main/blueprints/automation/bed_exit_bathroom_lights.yaml

Settings > Automations & scenes > Blueprints > Import blueprint, paste that URL.

Create a night mode toggle if you do not already have one (see
`examples/helpers.yaml`), then create one automation per bathroom.
`examples/automations.yaml` shows the YAML form. The bed sensors can be shared
between bathrooms - an ensuite and a hall bathroom can both watch the same bed.

**Turn off any existing motion-light automation for the same room**, including
Node-RED flows, or the two will fight over the lights.

### Tuning

Everything here is one number, and the two worth touching are:

- **Pre-light firing when you did not get up.** Some bed sensors twitch when you
  shift position. The confirm window already cleans this up, so first decide
  whether you can even see it from the bed - if not, ignore it. If it bothers
  you, drop the pre-light brightness before anything else. Adding a `for:`
  debounce to the bed sensor also works, but it comes straight out of the head
  start the blueprint exists to buy, so it is the last resort rather than the
  first.
- **Still dim when you are up for the day.** This is the one that bites, and it
  is why the night window exists. A sleep-mode toggle is only ever as accurate
  as your memory of switching it off, so "night mode is on" alone is not allowed
  to decide anything - it has to agree with the clock. If you are brushing your
  teeth at 20% at 08:00, night mode is stale and **Night ends** is the input to
  move, not the brightness. Someone still in bed keeps the room dim regardless
  of the hour, which is deliberate.
- **Lights dying mid-shower.** Raise the extra daytime delay. A PIR cannot see
  through a shower curtain, and its own occupancy timeout usually burns most of
  the off delay before Home Assistant hears anything at all.

### Testing

You do not need to wait for bedtime. Turn night mode on, make sure the
bathroom lights are off, then trigger a bed sensor from Developer tools >
States (set it to `on`, then `off`) and watch the dim light come up. Walk into
the bathroom to confirm the step up; or stay put and watch it switch itself off
a confirm window later.

Set the confirm window to 15 seconds while testing so the wrong-guess path does
not take a minute and a half to show up. Restore it afterwards.

Automation traces show which trigger fired and which branch ran.

### Notes

- `mode: restart` is load-bearing in three places: returning motion cancels a
  pending off delay, confirming motion cancels the pre-light's back-out timer,
  and a second person getting up does not queue a duplicate pre-light. Do not
  change it to `single` or `queued`.
- The dim light and the full group are both switched off at the end of every
  visit, so it does not matter whether the dim light is a member of the group.
- Lights switched on by hand with no motion at all are not switched off by this
  blueprint - the off delay needs a motion sensor transition to start from.
- In-flight delays do not survive a Home Assistant restart, so a restart during
  a visit can leave the lights on until the next one.
