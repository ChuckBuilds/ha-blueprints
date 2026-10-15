[All blueprints](../README.md)

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

## One wait, not two

A manual alarm panel has its own entry delay (`delay_time`: the panel sits in
`pending` before `triggered`), and the dispatch countdown starts only after
that. Two waits, and only the second one notifies you.

Recommended: set the panel's `delay_time` to `0` and make the dispatch
**Countdown** the whole time you want (e.g. 90 s). A door opening then gives
you one critical push right away, with the camera snapshot and three buttons:
**Disarm** (Face ID), **Cancel - I'm safe**, **Dispatch now**.

```yaml
alarm_control_panel:
  - platform: manual
    name: Security Alarm
    code: !secret alarm_code
    arming_time: 60
    delay_time: 0        # the dispatch countdown is the entry delay
    trigger_time: 600
    disarm_after_trigger: false
```

If you later add a siren, start it from "When handed to Noonlight", not "When
the countdown starts", or it sounds on every normal arrival.

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
| **Disarm** tapped | The phone asks to be unlocked first (Face ID / passcode on iPhone; fingerprint / face / PIN on Android 12+; older Android does not ask), then the panel is disarmed and Noonlight is not called. If the panel does not disarm (wrong code), a loud "Panel did NOT disarm" push follows; Noonlight is still not called |
| **Cancel - I'm safe** tapped | Noonlight not called, panel **stays armed** (for when you are away and the camera shows nothing wrong) |
| Panel disarmed during countdown (app / keypad) | Same as Disarm |
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
| Panel code (for the Disarm button) | - | Adds the **Disarm** button, which needs the phone unlocked (iPhone, Android 12+). Not needed if the panel has no code. Stored in the automation like any input |
| Last tripped sensor helper | - | Optional `input_text` from the sensor blueprint, so Noonlight hears "Back door" |
| Service | Police | Police, Fire or Medical |
| Mode helper | - | `input_select` with Off / Local / Test / Live |
| Sandbox server token | - | Test mode only. In YAML: `!secret noonlight_sandbox_token` |
| Dispatcher instructions | - | Gate codes, pets, who lives here. The alarm cause goes in front |
| Phones to notify | - | Pick Companion app phones; each gets the critical countdown push |
| Other notify action | - | Optional, e.g. a notify group like `notify.family_phones` |
| Countdown | 60 s | On top of the panel's entry delay (see "One wait" below). 30 s is reasonable for Fire |
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
| Last tripped sensor helper | - | Optional; feeds the push title and the Noonlight alarm cause |

The helper gets what happened, worded by the sensor's type, plus the mode the panel was armed in, so the push and the Noonlight operator read `Police alarm: Front Door opened (armed night)`. The mode tells the operator whether people should be home: night means asleep inside, away means nobody should be there.

| Sensor type (device class) | Wording |
|---|---|
| door, window, garage door, opening | `Front Door opened (armed night)` |
| motion, occupancy, presence | `Motion detected: Kitchen Motion (armed away)` |
| anything else | `<name> triggered (armed home)` |

The name is the sensor's friendly name, so name your sensors the way you want them read out (e.g. "Front Door", not "Front Door Door").

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
through 53 scenarios. Needs `pip install homeassistant`; takes about 2.5
minutes and exits non-zero on any failure.

## Disclaimer

Noonlight Enhanced is a community integration, not supported by Noonlight,
Konnected or Home Assistant. These blueprints are not a certified alarm
system. Test thoroughly, keep a phone handy, and if in doubt call 911.
