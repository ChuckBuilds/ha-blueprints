"""Runtime check for the leak shutoff blueprint.

Runs blueprints/automation/leak_shutoff.yaml in a headless Home Assistant with
recorded (fake) notify, valve, timer and logbook actions. No real devices.

    pip install homeassistant
    python tests/leak_test.py        # about 1 minute, exits 1 on any FAIL
"""
import asyncio, logging, shutil, sys, tempfile
from pathlib import Path
from homeassistant import config_entries, core, loader
from homeassistant.setup import async_setup_component
from homeassistant.helpers import (area_registry, category_registry, device_registry, entity_registry,
                                   floor_registry, issue_registry, label_registry)

logging.basicConfig(level=logging.CRITICAL)
REPO = Path(__file__).resolve().parent.parent
CFG = tempfile.mkdtemp(prefix="leak-bp-test-")
shutil.copytree(REPO / "blueprints" / "automation", Path(CFG) / "blueprints" / "automation" / "ChuckBuilds")
VALVE = "switch.valve"
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
            if name == "switch.turn_off":
                for e in call.data["entity_id"]:
                    hass.states.async_set(e, "off")
            if name == "timer.start":
                for e in call.data["entity_id"]:
                    hass.states.async_set(e, "active")
        return handler

    for svc in ["notify.mobile_app_good", "switch.turn_off", "system_log.write", "timer.start",
                "logbook.log", "persistent_notification.create"]:
        d, s = svc.split(".")
        hass.services.async_register(d, s, rec(svc))

    sensors = ["a", "b", "c", "d"]
    for s in sensors:
        hass.states.async_set(f"binary_sensor.{s}_water_leak", "off", {"device_class": "moisture"})
        hass.states.async_set(f"timer.leak_snooze_{s}_water_leak", "idle")
    hass.states.async_set(VALVE, "on")
    hass.states.async_set("binary_sensor.e_water_leak", "off", {"device_class": "moisture"})

    # a real mobile_app device named "good" -> notify.mobile_app_good
    phone_entry = config_entries.ConfigEntry(
        data={}, domain="mobile_app", title="good", version=1, minor_version=1, source="user",
        options={}, unique_id="good", discovery_keys={}, subentries_data=None)
    hass.config_entries._entries[phone_entry.entry_id] = phone_entry
    phone = device_registry.async_get(hass).async_get_or_create(
        config_entry_id=phone_entry.entry_id, identifiers={("mobile_app", "good")}, name="good")

    assert await async_setup_component(hass, "automation", {"automation": [
        {"id": "leak", "alias": "leak", "use_blueprint": {"path": "ChuckBuilds/leak_shutoff.yaml", "input": {
            "leak_sensors": [f"binary_sensor.{s}_water_leak" for s in sensors],
            "valve_switch": VALVE,
            "notify_devices": [phone.id],
            # plus a typed notify action that does not exist
            "notify_services": ["notify.does_not_exist"],
            "grace_period": {"hours": 0, "minutes": 0, "seconds": 3},
            "extra_shutoff_actions": [{"action": "logbook.log", "data": {"name": "extra", "message": "ran"}}],
        }}},
        # typed actions only, the bad one first: the valve must still close
        {"id": "leak_typed", "alias": "leak_typed", "use_blueprint": {"path": "ChuckBuilds/leak_shutoff.yaml", "input": {
            "leak_sensors": ["binary_sensor.e_water_leak"],
            "valve_switch": VALVE,
            "notify_services": ["notify.does_not_exist", "notify.mobile_app_good"],
            "grace_period": {"hours": 0, "minutes": 0, "seconds": 3},
        }}}]})
    await asyncio.sleep(0.5)

    ok = []

    def check(name, cond, detail=""):
        ok.append(bool(cond))
        print(("PASS " if cond else "FAIL ") + name + ("" if cond else f"  -> {detail}"))

    def took(name):
        return [d for n, d in calls if n == name]

    def pushes():
        return [d for n, d in calls if n == "notify.mobile_app_good"]

    def buttons():
        return [a["action"] for d in pushes() for a in d.get("data", {}).get("actions", [])]

    async def reset():
        calls.clear()
        hass.states.async_set(VALVE, "on")
        for s in sensors:
            hass.states.async_set(f"binary_sensor.{s}_water_leak", "off", {"device_class": "moisture"})
            hass.states.async_set(f"timer.leak_snooze_{s}_water_leak", "idle")
        await asyncio.sleep(0.5)
        calls.clear()

    # 1. Missing notify action first: real phone still alerted, valve still closes, extras still run.
    hass.states.async_set("binary_sensor.a_water_leak", "on", {"device_class": "moisture"})
    await asyncio.sleep(6)
    check("picked phone alerted despite a bad typed action", any("Leak detected" in d.get("title", "") for d in pushes()), calls)
    check("valve closed on timeout despite a bad typed action", took("switch.turn_off"), calls)
    check("shutoff reported to the phone", any("shut off" in d.get("title", "").lower() for d in pushes()), pushes())
    check("extra shutoff actions ran", [d for d in took("logbook.log") if d.get("name") == "extra"], calls)

    # 2. unknown -> on alerts (sensor not yet reported since restart).
    await reset()
    hass.states.async_set("binary_sensor.b_water_leak", "unknown", {"device_class": "moisture"})
    await asyncio.sleep(0.3)
    hass.states.async_set("binary_sensor.b_water_leak", "on", {"device_class": "moisture"})
    await asyncio.sleep(6)
    check("unknown -> on alerts and shuts off", pushes() and took("switch.turn_off"), calls)

    # 3. unavailable -> on is ignored (mesh drop / rejoin).
    await reset()
    hass.states.async_set("binary_sensor.c_water_leak", "unavailable", {"device_class": "moisture"})
    await asyncio.sleep(0.3)
    hass.states.async_set("binary_sensor.c_water_leak", "on", {"device_class": "moisture"})
    await asyncio.sleep(6)
    check("unavailable -> on ignored", not pushes() and not took("switch.turn_off"), calls)

    # 4. Cancel: water stays on, sensor snoozes, phone told.
    await reset()
    hass.states.async_set("binary_sensor.d_water_leak", "on", {"device_class": "moisture"})
    await asyncio.sleep(0.5)
    cancel = [b for b in buttons() if b.startswith("LEAK_CANCEL_")]
    check("alert has Cancel and Shut off now buttons", cancel and any(b.startswith("LEAK_SHUTOFF_NOW_") for b in buttons()), buttons())
    if cancel:
        hass.bus.async_fire("mobile_app_notification_action", {"action": cancel[0]})
    await asyncio.sleep(5)
    check("cancel: valve NOT closed", not took("switch.turn_off"), calls)
    check("cancel: snooze timer started", took("timer.start"), calls)
    check("cancel: phone told water left on", any("cancelled" in d.get("title", "").lower() for d in pushes()), pushes())
    hass.states.async_set("binary_sensor.d_water_leak", "off", {"device_class": "moisture"})
    await asyncio.sleep(0.3)
    calls.clear()
    hass.states.async_set("binary_sensor.d_water_leak", "on", {"device_class": "moisture"})
    await asyncio.sleep(1)
    check("snoozed sensor stays quiet", not pushes(), calls)

    # 5. Shut off now: closes immediately, well before the countdown.
    await reset()
    hass.states.async_set("binary_sensor.a_water_leak", "on", {"device_class": "moisture"})
    await asyncio.sleep(0.5)
    now = [b for b in buttons() if b.startswith("LEAK_SHUTOFF_NOW_")]
    if now:
        hass.bus.async_fire("mobile_app_notification_action", {"action": now[0]})
    await asyncio.sleep(1)
    check("shut off now closes immediately", took("switch.turn_off"), calls)
    await asyncio.sleep(3)

    # 6. Two sensors at once: both named in their own alert.
    await reset()
    hass.states.async_set("binary_sensor.a_water_leak", "on", {"device_class": "moisture"})
    hass.states.async_set("binary_sensor.b_water_leak", "on", {"device_class": "moisture"})
    await asyncio.sleep(0.7)
    titles = [d.get("title", "") for d in pushes() if "Leak detected" in d.get("title", "")]
    check("two sensors: two alerts", len(titles) == 2, titles)
    await asyncio.sleep(6)

    # 7. Typed actions only, bad one first: pushes after it are lost, the valve is not.
    await reset()
    hass.states.async_set("binary_sensor.e_water_leak", "on", {"device_class": "moisture"})
    await asyncio.sleep(6)
    check("typed list with a bad entry: valve still closes", took("switch.turn_off"), calls)

    await hass.async_stop(force=True)
    print(f"\n{sum(ok)}/{len(ok)} passed")
    sys.exit(0 if all(ok) else 1)


asyncio.run(main())
