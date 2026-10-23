"""Runtime check for the door-aware auto-lock blueprint's failure handling.

Runs blueprints/automation/smart_auto_lock.yaml in a headless Home Assistant
with fake locks, door sensors and a phone. Four doors run side by side.

    pip install homeassistant
    python tests/auto_lock_test.py        # about 1.5 minutes, exits 1 on any FAIL
"""
import asyncio, logging, shutil, sys, tempfile
from pathlib import Path
from homeassistant import config_entries, core, loader
from homeassistant.exceptions import HomeAssistantError
from homeassistant.setup import async_setup_component
from homeassistant.helpers import (area_registry, category_registry, device_registry, entity_registry,
                                   floor_registry, issue_registry, label_registry)

logging.basicConfig(level=logging.CRITICAL)
REPO = Path(__file__).resolve().parent.parent
CFG = tempfile.mkdtemp(prefix="autolock-bp-test-")
shutil.copytree(REPO / "blueprints" / "automation", Path(CFG) / "blueprints" / "automation" / "ChuckBuilds")
DOORS = ["good", "dead", "jam", "reopen", "sleepy"]
awake = set()
calls = []


async def main():
    hass = core.HomeAssistant(CFG)
    loader.async_setup(hass)
    for reg in (category_registry, floor_registry, label_registry, area_registry,
                device_registry, entity_registry, issue_registry):
        await reg.async_load(hass)
    hass.config.skip_pip = True
    hass.config_entries = config_entries.ConfigEntries(hass, {})
    await hass.config_entries.async_initialize()
    await hass.async_start()

    def rec(name):
        async def handler(call):
            calls.append((name, dict(call.data)))
            if name == "lock.lock":
                for e in call.data["entity_id"]:
                    door = e.split(".")[1]
                    if door == "good":
                        hass.states.async_set(e, "locked", {"friendly_name": "Good Door"})
                    elif door == "jam":
                        hass.states.async_set(e, "jammed", {"friendly_name": "Jam Door"})
                        raise HomeAssistantError("Lock jammed")
                    elif door == "sleepy" and door in awake:
                        hass.states.async_set(e, "locked", {"friendly_name": "Sleepy Door"})
                    # dead / reopen / sleepy before a wake: accepted, nothing happens
            if name == "button.press":
                awake.update(e.split(".")[1].removesuffix("_wake") for e in call.data["entity_id"])
        return handler

    for svc in ["lock.lock", "button.press", "notify.mobile_app_me", "logbook.log",
                "persistent_notification.create", "persistent_notification.dismiss"]:
        d, s = svc.split(".")
        hass.services.async_register(d, s, rec(svc))

    entry = config_entries.ConfigEntry(data={}, domain="mobile_app", title="me", version=1, minor_version=1,
                                       source="user", options={}, unique_id="me", discovery_keys={},
                                       subentries_data=None)
    hass.config_entries._entries[entry.entry_id] = entry
    phone = device_registry.async_get(hass).async_get_or_create(
        config_entry_id=entry.entry_id, identifiers={("mobile_app", "me")}, name="me")

    hass.states.async_set("input_boolean.guest", "off")
    hass.states.async_set("input_boolean.party", "off")
    autos = []
    for door in DOORS:
        hass.states.async_set(f"lock.{door}", "locked", {"friendly_name": f"{door.title()} Door"})
        hass.states.async_set(f"binary_sensor.{door}_door", "off", {"device_class": "door"})
        autos.append({"id": f"lock_{door}", "alias": f"lock_{door}", "use_blueprint": {
            "path": "ChuckBuilds/smart_auto_lock.yaml", "input": {
                "lock_entity": f"lock.{door}", "door_sensor": f"binary_sensor.{door}_door",
                "normal_delay": 0.5, "guest_delay": 0.5,
                "guest_mode": "input_boolean.guest", "party_mode": "input_boolean.party",
                "lock_attempts": 2 if door in ("jam", "sleepy") else 1,
                **({"wake_button": "button.sleepy_wake"} if door == "sleepy" else {}),
                # picked phone + the same action typed: must still be ONE push
                "notify_devices": [phone.id], "notify_service": "notify.mobile_app_me",
            }}})
    assert await async_setup_component(hass, "automation", {"automation": autos})
    await asyncio.sleep(0.5)
    calls.clear()

    ok = []

    def check(name, cond, detail=""):
        ok.append(bool(cond))
        print(("PASS " if cond else "FAIL ") + name + ("" if cond else f"  -> {detail}"))

    for door in DOORS:
        hass.states.async_set(f"lock.{door}", "unlocked", {"friendly_name": f"{door.title()} Door"})
    await asyncio.sleep(32)          # past the 30 s countdown: first lock attempts are running
    hass.states.async_set("binary_sensor.reopen_door", "on", {"device_class": "door"})
    await asyncio.sleep(65)          # dead: 1 x 30 s confirm; jam: 2 attempts (error = no wait)

    def lock_calls(door):
        return [d for n, d in calls if n == "lock.lock" and d["entity_id"] == [f"lock.{door}"]]

    def alerts(door):
        return [d for n, d in calls if n == "notify.mobile_app_me" and d.get("title", "").startswith(f"{door.title()} Door")]

    def notes(door):
        return [d for n, d in calls if n == "persistent_notification.create"
                and d["notification_id"] == f"auto_lock_failed_automation.lock_{door}"]

    check("good: locked, no alert", hass.states.get("lock.good").state == "locked" and not alerts("good"), calls)
    check("good: stale failure notice cleared", [d for n, d in calls if n == "persistent_notification.dismiss"
                                                 and d["notification_id"] == "auto_lock_failed_automation.lock_good"], calls)
    check("dead: push says it did NOT lock", alerts("dead") and "did NOT lock" in alerts("dead")[0]["title"], alerts("dead"))
    check("dead: exactly one push (phone + same typed action deduped)", len(alerts("dead")) == 1, alerts("dead"))
    check("dead: persistent notification", notes("dead"), calls)
    check("jam: still retried after the lock errored", len(lock_calls("jam")) == 2, lock_calls("jam"))
    check("jam: alert reports 'jammed'", alerts("jam") and "jammed" in alerts("jam")[0]["message"], alerts("jam"))
    check("reopen: door opened during retry -> no alert", not alerts("reopen") and not notes("reopen"), calls)
    wakes = [d for n, d in calls if n == "button.press"]
    check("sleepy: woken once before the retry, then locked, no alert",
          wakes == [{"entity_id": ["button.sleepy_wake"]}] and hass.states.get("lock.sleepy").state == "locked"
          and not alerts("sleepy"), calls)
    check("jam: no wake button set -> never pressed", all(d["entity_id"] == ["button.sleepy_wake"] for d in wakes), wakes)

    await hass.async_stop(force=True)
    print(f"\n{sum(ok)}/{len(ok)} passed")
    sys.exit(0 if all(ok) else 1)


asyncio.run(main())
