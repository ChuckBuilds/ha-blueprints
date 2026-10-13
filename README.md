# ha-blueprints

Home Assistant automation blueprints, including a [Noonlight monitored-alarm suite](#noonlight-alarm-suite).

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
| Notify action | - | e.g. `notify.mobile_app_your_phone` or a notify group |
| Countdown | 60 s | On top of the panel's entry delay. 30 s is reasonable for Fire |
| When the countdown starts | - | Your actions: siren, lights, TTS warning |
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

### Inputs

| Input | Default | Notes |
|---|---|---|
| Notify action | - | Same as your dispatch automations |
| Household notify action | - | Optional. Everyone who may get Noonlight's calls |
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
through 37 scenarios. Needs `pip install homeassistant`; takes about 2.5
minutes and exits non-zero on any failure.

## Disclaimer

Noonlight Enhanced is a community integration, not supported by Noonlight,
Konnected or Home Assistant. These blueprints are not a certified alarm
system. Test thoroughly, keep a phone handy, and if in doubt call 911.
