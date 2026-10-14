[All blueprints](../README.md)

# Bed-exit predictive bathroom lights

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

## Behaviour

| Situation | What happens |
|---|---|
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

## Inputs

| Input | Default | Notes |
|---|---|---|
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

## Install

Import the blueprint:

    https://github.com/ChuckBuilds/ha-blueprints/blob/main/blueprints/automation/bed_exit_bathroom_lights.yaml

Settings > Automations & scenes > Blueprints > Import blueprint, paste that URL.

Create a night mode toggle if you do not already have one (see
`examples/helpers.yaml`), then create one automation per bathroom.
`examples/automations.yaml` shows the YAML form. The bed sensors can be shared
between bathrooms - an ensuite and a hall bathroom can both watch the same bed.

**Turn off any existing motion-light automation for the same room**, including
Node-RED flows, or the two will fight over the lights.

## Tuning

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

## Testing

You do not need to wait for bedtime. Turn night mode on, make sure the
bathroom lights are off, then trigger a bed sensor from Developer tools >
States (set it to `on`, then `off`) and watch the dim light come up. Walk into
the bathroom to confirm the step up; or stay put and watch it switch itself off
a confirm window later.

Set the confirm window to 15 seconds while testing so the wrong-guess path does
not take a minute and a half to show up. Restore it afterwards.

Automation traces show which trigger fired and which branch ran.

## Notes

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
