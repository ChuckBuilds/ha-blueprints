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
---

# Noonlight alarm suite

Four blueprints that turn Home Assistant into a monitored alarm using
[Noonlight](https://noonlight.com) through the
[Noonlight Enhanced](https://github.com/KruseLuds/noonlight-hass) integration.
They're built to send **zero false alarms**: every step can be tested without
calling anyone, every step can be cancelled, and everything that happens is
written to the logbook.

| Blueprint | What it does | How many |
|---|---|---|
| `alarm_sensor_trigger.yaml` | Doors / windows / motion trip the alarm panel while armed | One per sensor group |
| `noonlight_dispatch.yaml` | Panel triggered (or smoke sensor on) -> cancellable countdown -> Noonlight | One per service: Police, Fire, Medical |
| `noonlight_status_tracker.yaml` | Reports what Noonlight did: active, failed, cancelled, 911 contacted | Exactly one |
| `alarm_presence_arm_disarm.yaml` | Arms when everyone leaves, optional disarm on arrival | Optional |

## How an alarm flows

```
 door opens (off -> on, held for debounce)      smoke / CO sensor on
        |                                               |
 alarm panel armed? --no--> nothing                     |
        | yes                                           |
 panel "pending"  (entry delay - disarm here = nothing happens)
        |                                               |
 panel "triggered" ---------------------------+---------+
                                              |
                         CRITICAL PUSH  [Cancel - I'm safe] [Dispatch now]
                         countdown (default 60 s)
                                              |
           Cancel / panel disarmed --> "cancelled, Noonlight NOT called"
                                              |
                                  mode helper says...
       Off  -> "DRY RUN" push       Local -> simulated Noonlight events
       Test -> Noonlight SANDBOX    Live  -> Noonlight PRODUCTION
       anything else -> "NOT SENT - call 911 yourself"
                                              |
              status tracker hears the result |
       created -> "ACTIVE" push + [Cancel Noonlight alarm] + household told
       failed  -> CRITICAL "FAILED - call 911 yourself"
       nothing within 45 s -> CRITICAL "no response - call 911 yourself"
                                              |
              Noonlight webhooks (if your account sends them)
       "operator contacted 911"  "cancelled by +1555..."  "closed by dispatcher"
```

Read the whole story afterwards in **Logbook**, search `Noonlight`.

## Setup

1. Install **Noonlight Enhanced** (HACS custom repository
   `KruseLuds/noonlight-hass`) and set it up with your address, phone, PIN
   and secondary contact.
2. Add the helpers and alarm panel from `examples/noonlight_helpers.yaml`.
   The important one is `input_select.noonlight_mode` with options exactly
   `Off`, `Local`, `Test`, `Live`. It starts on **Off**.
3. Import the four blueprints (Settings > Automations & scenes > Blueprints >
   Import blueprint):

       https://github.com/ChuckBuilds/ha-blueprints/blob/main/blueprints/automation/alarm_sensor_trigger.yaml
       https://github.com/ChuckBuilds/ha-blueprints/blob/main/blueprints/automation/noonlight_dispatch.yaml
       https://github.com/ChuckBuilds/ha-blueprints/blob/main/blueprints/automation/noonlight_status_tracker.yaml
       https://github.com/ChuckBuilds/ha-blueprints/blob/main/blueprints/automation/alarm_presence_arm_disarm.yaml

4. Create the automations. `examples/noonlight_automations.yaml` shows a full
   working set (perimeter + motion, Police, Fire, tracker, presence).
5. Work through the [testing ladder](#testing-ladder) before you ever pick
   `Live`.

## Modes

| Mode | Countdown + pushes | Calls Noonlight | Use it for |
|---|---|---|---|
| Off | Yes, ends with "DRY RUN" | Never | Setting up sensors, notifications, cancel / disarm |
| Local | Yes | Never - fires simulated Noonlight events inside HA | Testing the tracker, cancel buttons, webhook handling |
| Test | Yes | Noonlight **sandbox** | Real SMS / voice calls, PIN, address, instructions |
| Live | Yes | Noonlight **production** | Real dispatch |
| anything else | Yes, ends with "NOT SENT" | Never | A renamed option or unavailable helper fails safe |

## Noonlight dispatch (countdown, cancel, Off/Local/Test/Live)

`blueprints/automation/noonlight_dispatch.yaml`

### Behaviour

| Situation | What happens |
|---|---|
| Panel goes triggered / smoke sensor on | Critical push with Cancel and Dispatch now, countdown starts |
| Cancel tapped | "Cancelled" push, Noonlight not called, your cancel actions run |
| Panel disarmed during countdown | Same as Cancel |
| Dispatch now tapped | Skips the rest of the countdown |
| Nobody responds | Dispatches when the countdown ends |
| Second sensor during the countdown | Ignored - one alarm at a time per service |
| Sensor comes back from unavailable | Ignored - not an alarm |
| Button from an old notification tapped | Ignored - buttons are unique per alarm |
| Mode helper unavailable / unknown value | Nothing sent, critical "call 911 yourself" push |
| Test mode without a sandbox token | Integration refuses, tracker sends "FAILED" |
| Live mode | Production endpoint forced, sandbox token never sent |
| Cancel buttons fail to register | Countdown still runs in full; disarm still cancels |
| A phone was renamed, a notify action is wrong, or your siren errors | Only that push / action fails; the countdown and dispatch still run |

### Inputs

| Input | Default | Notes |
|---|---|---|
| Trigger entities | - | Alarm panel (fires on `triggered`) and/or binary sensors / toggles (fire on `on`) |
| Alarm panel (disarm cancels) | - | Optional. Usually the same panel as above |
| Last tripped sensor helper | - | Optional `input_text` from the sensor blueprint, so Noonlight hears "Back door" |
| Service | Police | Police, Fire or Medical |
| Mode helper | - | `input_select` with Off / Local / Test / Live |
| Sandbox server token | - | Test mode only. In YAML: `!secret noonlight_sandbox_token` |
| Dispatcher instructions | - | Gate codes, pets, who lives here. The alarm cause goes in front |
| Phones to notify | - | Pick Companion app phones; each gets the critical countdown push |
| Other notify action | - | Optional, e.g. a notify group like `notify.family_phones` |
| Countdown | 60 s | On top of the panel's entry delay. 30 s is reasonable for Fire |
| Camera | - | Optional. Snapshot in the push; long-press on iPhone for the live feed |
| Open when tapped | - | Optional dashboard path, e.g. `/lovelace/security` |
| Extra message line | - | Optional. Templates work: `Front door lock: {{ states('lock.front_door') }}` |
| When the countdown starts | - | Your actions: siren, lights, TTS warning. Run alongside the countdown |
| When cancelled before dispatch | - | Your actions: siren off |
| When handed to Noonlight | - | Your actions: lights on, unlock for responders |

### Notes

- `mode: single` is what stops duplicate dispatches. Don't change it.
- The countdown push uses iOS critical alerts (rings through silent / Focus)
  and the Android `alarm_stream` channel. Allow critical alerts for the HA
  Companion app on iOS.
- Fire and Medical usually have no panel: leave "Alarm panel" empty and
  cancel with the button.

## Noonlight status tracker

`blueprints/automation/noonlight_status_tracker.yaml`

### Behaviour

| Event | What happens |
|---|---|
| Dispatch requested | Logbook. If no result arrives within the timeout: critical "no response - call 911 yourself" |
| Alarm created | Critical "ACTIVE" push with alarm ID (+ Cancel button), household told, ID saved |
| Alarm failed | Critical "FAILED - call 911 yourself", household told |
| Cancel button tapped | Local alarms: simulated cancel. Real alarms: `noonlight.cancel_alarm` |
| Alarm cancelled | Push + household told |
| Noonlight webhook | Plain-English push: 911 contacted / closed / cancelled by phone |
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
| Phones to notify | - | Same phones as your dispatch automations |
| Other notify action | - | Optional, e.g. a notify group |
| Household phones / notify action | - | Optional. Everyone who may get Noonlight's calls |
| Last alarm ID helper | - | Optional `input_text` |
| Integration has `noonlight.cancel_alarm` | Off | See [Cancelling](#cancelling-an-alarm). Leave off unless your integration has it |
| Result timeout | 45 s | How long to wait for Noonlight before warning |
| Push Noonlight webhook updates | On | Off = logbook only |
| Show latest status as a notification card | On | Sidebar notification with the last status |

## Alarm sensor trigger

`blueprints/automation/alarm_sensor_trigger.yaml`

| Input | Default | Notes |
|---|---|---|
| Alarm panel | - | |
| Sensors | - | `on` = open / motion |
| Armed states that count | Away, Night | Make one automation for perimeter (all modes) and one for interior motion (away only) |
| Debounce | 1 s | Sensor must stay open this long |
| Last tripped sensor helper | - | Optional; feeds the dispatch alarm cause |

Only `off -> on` counts. Sensors coming back from `unavailable` after a
reboot or radio drop never trip the panel.

## Alarm presence arm / disarm

`blueprints/automation/alarm_presence_arm_disarm.yaml`

| Input | Default | Notes |
|---|---|---|
| Alarm panel | - | |
| Zone | `zone.home` | Arms when its person count hits 0 |
| Arm as | Away | |
| Arm after everyone has been gone for | 5 min | |
| Disarm when someone arrives | **Off** | A stolen phone or GPS glitch would disarm the house. Never disarms a panel that is already `triggered` |
| Panel code | - | Only if your panel needs one |
| Notify action | - | Optional |

## Cancelling an alarm

| When | How |
|---|---|
| Entry delay (panel `pending`) | Disarm the panel. Nothing else happens |
| Countdown | Tap **Cancel - I'm safe**, or disarm the panel |
| After dispatch, Local mode | Tap **Cancel Noonlight alarm** |
| After dispatch, Test / Live | Answer Noonlight's call or text and give your **PIN**. Or tap **Cancel Noonlight alarm** if your integration has `noonlight.cancel_alarm` |

The current Noonlight Enhanced release has no cancel action; a pull request
adding `noonlight.cancel_alarm` is proposed upstream. Until your installed
version has it, keep "Integration has noonlight.cancel_alarm" **off** - the
ACTIVE push then tells you to cancel by phone instead of showing a button
that cannot work.

## Testing ladder

Do every stage, in order. Don't move on until everything in the stage passes.

**Stage 0 - Off.** Arm the panel, trip every sensor. Check entry delay,
countdown push, Cancel, disarm-cancel, Dispatch now and the DRY RUN push.

**Stage 1 - Local.** No network, nobody gets called. Trip a sensor and let
the countdown run out, then use the three scripts from
`examples/noonlight_webhook_tests.yaml` (dashboard buttons) to send
Noonlight-format webhooks to your own HA.

**Stage 2 - Test (Noonlight sandbox).** Put your sandbox server token in the
dispatch automation. Noonlight's sandbox really texts and calls the phone
numbers in the integration.

**Stage 3 - Live.** First tell everyone who may get a call or text. Set the
Police instructions to `TEST - please call to verify, do not dispatch`, set
mode Live, trip a sensor, answer Noonlight, give your PIN and confirm the
cancel. Put your real instructions back. Leave mode on Live.

| Check | Stage | How |
|---|---|---|
| Automations behave correctly | 0, 1 | Cancel, disarm, Dispatch now and timeout each end in the right push and logbook line |
| HA events | 1, 2 | Developer tools > Events, listen to `noonlight_alarm_created` etc.; tracker pushes |
| Logging and diagnostics | 0-3 | Logbook `Noonlight`, status card, automation traces |
| Notification routing / escalation | 0-3 | Countdown reaches you; household gets ACTIVE / FAILED / cancelled |
| Deduplication | 0, 1 | Open three doors during one countdown: one push, one dispatch |
| Webhook handling | 1, 2 | Stage 1 test scripts; Stage 2 real sandbox webhooks if your account sends them |
| TEST vs LIVE helper protection | 0, 1 | Temporarily add a `Banana` option to the mode helper and select it: "NOT SENT" push |
| Sandbox endpoint selection | 2 | `noonlight_alarm_attempted` shows `environment: sandbox` |
| Sandbox token handling | 2 | Blank token: "FAILED"; wrong token: "FAILED" with the API error |
| Sandbox vs production protection | 2, 3 | Live traces show the production endpoint and no token |
| Fail-safe on errors | 1, 2 | Wrong token, and the "no response" warning (disable the integration, run Test) |
| Dispatch instructions | 2, 3 | Operator reads back the alarm cause and your instructions |
| Address | 2, 3 | Sandbox text / Live operator confirms it |
| SMS notifications | 2, 3 | Primary and secondary phones get Noonlight's texts |
| Voice calls | 2, 3 | Primary and secondary phones get Noonlight's calls |
| Cancellation and PIN | 1, 2, 3 | Local cancel button; sandbox cancel + wrong PIN; Live cancel by phone with PIN |
| Phone numbers / PIN correct | 2, 3 | Calls arrive where expected; PIN accepted |
| Internet connectivity | 3 | Dispatch needs internet. The "no response" warning covers an outage, but only reaches you if your phone has its own data connection |
| Household knows the procedure | 3 | Everyone knows who Noonlight calls, the PIN, and how to cancel |
| Cancellation is understood | 3 | Everyone has read [Cancelling](#cancelling-an-alarm) |

### Automated check

`tests/runtime_test.py` runs all four blueprints inside a headless Home
Assistant with recorded (fake) notify, Noonlight and panel actions and plays
through 44 scenarios. Needs `pip install homeassistant`; takes about 2.5
minutes and exits non-zero on any failure.

## Disclaimer

Noonlight Enhanced is a community integration, not supported by Noonlight,
Konnected or Home Assistant. These blueprints are not a certified alarm
system. Test thoroughly, keep a phone handy, and if in doubt call 911.
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
