"""Runtime check for lock_on_arm.yaml and sensor_health.yaml.

Headless Home Assistant with fake locks, a panel, door sensors with battery
sensors on the same device, and a phone.

    pip install homeassistant
    python tests/extras_test.py        # ~45 s, exits 1 on any FAIL
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
CFG = tempfile.mkdtemp(prefix="extras-bp-test-")
shutil.copytree(REPO / "blueprints" / "automation", Path(CFG) / "blueprints" / "automation" / "ChuckBuilds")
P = "alarm_control_panel.house"
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
                    if e == "lock.front":
                        hass.states.async_set(e, "locked", {"friendly_name": "Front Lock"})
                    elif e == "lock.back":
                        hass.states.async_set(e, "jammed", {"friendly_name": "Back Lock"})
                        raise HomeAssistantError("Lock jammed")
        return handler

    for svc in ["lock.lock", "notify.mobile_app_me", "logbook.log",
                "persistent_notification.create", "persistent_notification.dismiss"]:
        d, s = svc.split(".")
        hass.services.async_register(d, s, rec(svc))

    def entry(domain, uid):
        e = config_entries.ConfigEntry(data={}, domain=domain, title=uid, version=1, minor_version=1, source="user",
                                       options={}, unique_id=uid, discovery_keys={}, subentries_data=None)
        hass.config_entries._entries[e.entry_id] = e
        return e

    dr, er = device_registry.async_get(hass), entity_registry.async_get(hass)
    phone = dr.async_get_or_create(config_entry_id=entry("mobile_app", "me").entry_id,
                                   identifiers={("mobile_app", "me")}, name="me")
    zig = entry("zha", "zigbee")
    # Two door sensors, each with a battery sensor on the same device.
    for door, battery in (("front", 80), ("back", 9)):
        dev = dr.async_get_or_create(config_entry_id=zig.entry_id, identifiers={("zha", door)}, name=f"{door} door")
        er.async_get_or_create("binary_sensor", "zha", f"{door}_door", device_id=dev.id,
                               suggested_object_id=f"{door}_door", config_entry=zig)
        er.async_get_or_create("sensor", "zha", f"{door}_battery", device_id=dev.id,
                               suggested_object_id=f"{door}_battery", config_entry=zig)
        hass.states.async_set(f"binary_sensor.{door}_door", "off", {"friendly_name": f"{door.title()} Door", "device_class": "door"})
        hass.states.async_set(f"sensor.{door}_battery", str(battery), {"device_class": "battery"})
    hass.states.async_set("binary_sensor.window", "off", {"friendly_name": "Window", "device_class": "window"})
    hass.states.async_set(P, "disarmed")
    for lk in ("front", "back"):
        hass.states.async_set(f"lock.{lk}", "unlocked", {"friendly_name": f"{lk.title()} Lock"})

    assert await async_setup_component(hass, "automation", {"automation": [
        {"id": "lockarm", "alias": "lockarm", "use_blueprint": {"path": "ChuckBuilds/lock_on_arm.yaml", "input": {
            "alarm_panel": P, "locks": ["lock.front", "lock.back"], "armed_states": ["armed_away"],
            "notify_devices": [phone.id], "notify_service": "notify.mobile_app_me"}}},
        {"id": "health", "alias": "health", "use_blueprint": {"path": "ChuckBuilds/sensor_health.yaml", "input": {
            "sensors": ["binary_sensor.front_door", "binary_sensor.back_door", "binary_sensor.window"],
            "battery_threshold": 20, "offline_minutes": 0.02, "notify_devices": [phone.id]}}},
    ]})
    await asyncio.sleep(0.5)
    ok = []

    def check(name, cond, detail=""):
        ok.append(bool(cond))
        print(("PASS " if cond else "FAIL ") + name + ("" if cond else f"  -> {detail}"))

    def took(name):
        return [d for n, d in calls if n == name]

    # --- lock on arm
    hass.states.async_set(P, "arming"); await asyncio.sleep(0.5)
    check("exit delay ('arming') -> doors NOT locked yet", not took("lock.lock"), calls)
    hass.states.async_set(P, "armed_home"); await asyncio.sleep(0.5)
    check("armed in a mode not picked -> no lock", not took("lock.lock"), calls)
    hass.states.async_set(P, "armed_away"); await asyncio.sleep(31)
    check("armed_away -> both locks locked", took("lock.lock") and
          sorted(took("lock.lock")[0]["entity_id"]) == ["lock.back", "lock.front"], took("lock.lock"))
    pushes = [d for d in took("notify.mobile_app_me") if d["title"] == "Door did NOT lock"]
    check("jammed lock -> ONE push naming it (phone + typed action deduped)",
          len(pushes) == 1 and "Back Lock (jammed)" in pushes[0]["message"]
          and "Front Lock" not in pushes[0]["message"], pushes)
    check("jammed lock -> persistent notification",
          [d for d in took("persistent_notification.create") if d["notification_id"] == "lock_on_arm_automation.lockarm"], calls)

    calls.clear()
    hass.states.async_set("lock.back", "unlocked", {"friendly_name": "Back Lock"})
    hass.states.async_set("lock.front", "locked", {"friendly_name": "Front Lock"})
    hass.states.async_set(P, "disarmed"); await asyncio.sleep(0.2)
    hass.services.async_remove("lock", "lock")

    async def lock_ok(call):
        calls.append(("lock.lock", dict(call.data)))
        for e in call.data["entity_id"]:
            hass.states.async_set(e, "locked", {"friendly_name": "Back Lock"})
    hass.services.async_register("lock", "lock", lock_ok)
    hass.states.async_set(P, "armed_away"); await asyncio.sleep(1)
    check("already-locked door is skipped", took("lock.lock") and took("lock.lock")[0]["entity_id"] == ["lock.back"], took("lock.lock"))
    check("all locked -> notification dismissed, no push",
          [d for d in took("persistent_notification.dismiss") if d["notification_id"] == "lock_on_arm_automation.lockarm"]
          and not took("notify.mobile_app_me"), calls)

    # --- sensor health
    calls.clear()
    await hass.services.async_call("automation", "trigger", {"entity_id": "automation.health"}, blocking=True)
    await asyncio.sleep(0.5)
    made = [d for d in took("persistent_notification.create") if d["notification_id"] == "sensor_health_automation.health"]
    check("daily check -> low battery found via the door's own device", made and "Back Door: battery 9%" in made[0]["message"]
          and "Front Door" not in made[0]["message"], made or calls)

    calls.clear()
    hass.states.async_set("binary_sensor.window", "unavailable", {"friendly_name": "Window"}); await asyncio.sleep(3)
    push = [d for d in took("notify.mobile_app_me") if d["title"].startswith("Alarm sensors need attention")]
    check("sensor offline for the set time -> push lists offline + battery",
          push and "Window: offline" in push[-1]["message"] and "battery 9%" in push[-1]["message"], push or calls)

    calls.clear()
    hass.states.async_set("binary_sensor.window", "off", {"friendly_name": "Window", "device_class": "window"})
    hass.states.async_set("sensor.back_battery", "95", {"device_class": "battery"})
    await hass.services.async_call("automation", "trigger", {"entity_id": "automation.health"}, blocking=True)
    await asyncio.sleep(0.5)
    check("all healthy -> notification cleared, no push",
          [d for d in took("persistent_notification.dismiss") if d["notification_id"] == "sensor_health_automation.health"]
          and not took("notify.mobile_app_me"), calls)

    await hass.async_stop(force=True)
    print(f"\n{sum(ok)}/{len(ok)} passed")
    sys.exit(0 if all(ok) else 1)


asyncio.run(main())
