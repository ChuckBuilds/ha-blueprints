# ha-blueprints

Home Assistant automation blueprints by ChuckBuilds. Click **Import** to add one to your
Home Assistant, then read its guide for setup and testing.

| Blueprint | What it does | Import | Guide |
|---|---|---|---|
| Door-aware auto-lock | Replaces a smart lock's auto-lock: counts down only once the door is closed, restarts on every opening | [![Import](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2FChuckBuilds%2Fha-blueprints%2Fblob%2Fmain%2Fblueprints%2Fautomation%2Fsmart_auto_lock.yaml) | [Guide](docs/smart_auto_lock.md) |
| Leak detection + auto shutoff | Leak sensor alerts every phone, then shuts the water main off if nobody answers | [![Import](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2FChuckBuilds%2Fha-blueprints%2Fblob%2Fmain%2Fblueprints%2Fautomation%2Fleak_shutoff.yaml) | [Guide](docs/leak_shutoff.md) |
| Bed-exit bathroom lights | Lights the bathroom when you leave the bed, before the motion sensor can see you | [![Import](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2FChuckBuilds%2Fha-blueprints%2Fblob%2Fmain%2Fblueprints%2Fautomation%2Fbed_exit_bathroom_lights.yaml) | [Guide](docs/bed_exit_bathroom_lights.md) |
| Noonlight dispatch | Cancellable countdown, then police / fire / medical via Noonlight (Off / Local / Test / Live) | [![Import](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2FChuckBuilds%2Fha-blueprints%2Fblob%2Fmain%2Fblueprints%2Fautomation%2Fnoonlight_dispatch.yaml) | [Guide](docs/noonlight.md#noonlight-dispatch-countdown-cancel-offlocaltestlive) |
| Noonlight status tracker | Active / failed / cancelled pushes, after-dispatch cancel button, Noonlight webhooks | [![Import](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2FChuckBuilds%2Fha-blueprints%2Fblob%2Fmain%2Fblueprints%2Fautomation%2Fnoonlight_status_tracker.yaml) | [Guide](docs/noonlight.md#noonlight-status-tracker) |
| Alarm sensor trigger | Doors, windows and motion trip your alarm panel while armed | [![Import](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2FChuckBuilds%2Fha-blueprints%2Fblob%2Fmain%2Fblueprints%2Fautomation%2Falarm_sensor_trigger.yaml) | [Guide](docs/noonlight.md#alarm-sensor-trigger) |
| Alarm presence arm / disarm | Arms when the people you pick leave (flapping, guest, motion and open-door checks); asks or disarms on arrival | [![Import](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2FChuckBuilds%2Fha-blueprints%2Fblob%2Fmain%2Fblueprints%2Fautomation%2Falarm_presence_arm_disarm.yaml) | [Guide](docs/noonlight.md#alarm-presence-arm--disarm) |

The four alarm blueprints work together as one system: start with the
[Noonlight alarm suite guide](docs/noonlight.md).

## Other guides

- [Bed-aware sleep mode (Adaptive Lighting safe)](docs/sleep_mode.md): a pattern built from
  helpers and automations, no blueprint to import.

## Importing by URL

If the Import button doesn't work for you: Settings > Automations & scenes > Blueprints >
Import blueprint, and paste the blueprint's GitHub URL from its guide.

## Repository layout

| Folder | Contents |
|---|---|
| `blueprints/automation/` | The blueprint files (these paths are what Home Assistant re-imports from, so they don't move) |
| `docs/` | One guide per blueprint |
| `examples/` | Helpers and example automations in YAML |
| `tests/` | `runtime_test.py` (alarm blueprints), `presence_test.py` (presence arm / disarm), `leak_test.py` (leak shutoff) and `auto_lock_test.py` (auto-lock failures), run in a headless Home Assistant |
