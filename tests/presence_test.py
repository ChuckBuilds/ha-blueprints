"""Runtime check for the alarm presence arm / disarm blueprint.

Runs blueprints/automation/alarm_presence_arm_disarm.yaml in a headless Home
Assistant with fake people, sensors, panel and phone. No real devices.

    pip install homeassistant
    python tests/presence_test.py        # about 1.5 minutes, exits 1 on any FAIL
"""
import asyncio, logging, shutil, sys, tempfile
from pathlib import Path
from homeassistant import config_entries, core, loader
from homeassistant.exceptions import ServiceValidationError
from homeassistant.setup import async_setup_component
from homeassistant.helpers import (area_registry, category_registry, device_registry, entity_registry,
                                   floor_registry, issue_registry, label_registry)

logging.basicConfig(level=logging.CRITICAL)
REPO = Path(__file__).resolve().parent.parent
CFG = tempfile.mkdtemp(prefix="presence-bp-test-")
shutil.copytree(REPO / "blueprints" / "automation", Path(CFG) / "blueprints" / "automation" / "ChuckBuilds")

P = "alarm_control_panel.house"          # people mode
P_ZONE = "alarm_control_panel.legacy"    # zone-count mode, old auto_disarm input
P_PHONE = "alarm_control_panel.phones"   # picked phones (device_tracker) instead of people
PH = "device_tracker.charles_iphone"
A, B = "person.a", "person.b"
calls = []
PANEL = {"refuse_arm": False, "code": "1234"}


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
            if name.startswith("alarm_control_panel."):
                if PANEL["code"] and call.data.get("code") not in (None, PANEL["code"]):
                    raise ServiceValidationError("Invalid alarm code")
                verb = name.split(".")[1]
                for e in call.data["entity_id"]:
                    if verb == "alarm_disarm":
                        hass.states.async_set(e, "disarmed")
                    elif not PANEL["refuse_arm"]:
                        hass.states.async_set(e, verb.replace("alarm_arm_", "armed_"))
        return handler

    for svc in ["notify.mobile_app_me", "logbook.log", "persistent_notification.create",
                "persistent_notification.dismiss", "alarm_control_panel.alarm_arm_away",
                "alarm_control_panel.alarm_arm_vacation", "alarm_control_panel.alarm_disarm"]:
        d, s = svc.split(".")
        hass.services.async_register(d, s, rec(svc))

    entry = config_entries.ConfigEntry(data={}, domain="mobile_app", title="me", version=1, minor_version=1,
                                       source="user", options={}, unique_id="me", discovery_keys={},
                                       subentries_data=None)
    hass.config_entries._entries[entry.entry_id] = entry
    phone = device_registry.async_get(hass).async_get_or_create(
        config_entry_id=entry.entry_id, identifiers={("mobile_app", "me")}, name="me")

    hass.states.async_set(PH, "home", {"friendly_name": "Charles iPhone"})
    for e in (P, P_ZONE, P_PHONE):
        hass.states.async_set(e, "disarmed")
    hass.states.async_set(A, "home", {"friendly_name": "Alice"})
    hass.states.async_set(B, "home", {"friendly_name": "Bob"})
    hass.states.async_set("zone.home", "1")
    hass.states.async_set("input_boolean.guest", "off")
    hass.states.async_set("binary_sensor.window", "off", {"friendly_name": "Kitchen Window"})
    hass.states.async_set("binary_sensor.motion", "off", {"friendly_name": "Hall Motion"})

    def bp(**inputs):
        return {"use_blueprint": {"path": "ChuckBuilds/alarm_presence_arm_disarm.yaml", "input": inputs}}

    assert await async_setup_component(hass, "automation", {"automation": [
        {"id": "pres", "alias": "pres", **bp(
            alarm_panel=P, people=[A, B], panel_code="1234",
            arm_delay=0.05, guest_mode="input_boolean.guest",
            motion_sensors=["binary_sensor.motion"], motion_exit_grace=0,
            open_sensors=["binary_sensor.window"], open_policy="block",
            arrival_action="ask", arrive_delay=2, notify_devices=[phone.id])},
        {"id": "phones", "alias": "phones", **bp(
            alarm_panel=P_PHONE, people=[PH], arm_action="alarm_control_panel.alarm_arm_vacation",
            arm_delay=0.05, arrival_action="disarm", panel_code="1234", notify_devices=[phone.id])},
        {"id": "legacy", "alias": "legacy", **bp(
            alarm_panel=P_ZONE, presence_zone="zone.home", arm_delay=0, auto_disarm=True,
            notify_service="notify.mobile_app_me")},
    ]})
    await asyncio.sleep(0.5)

    ok = []

    def check(name, cond, detail=""):
        ok.append(bool(cond))
        print(("PASS " if cond else "FAIL ") + name + ("" if cond else f"  -> {detail}"))

    def took(name):
        return [d for n, d in calls if n == name]

    def pushes():
        return [d for n, d in calls if n == "notify.mobile_app_me"]

    def titled(prefix):
        return [d for d in pushes() if d.get("title", "").startswith(prefix)]

    async def everyone(state, wait=0.3):
        hass.states.async_set(A, state, {"friendly_name": "Alice"})
        hass.states.async_set(B, state, {"friendly_name": "Bob"})
        await asyncio.sleep(wait)

    async def reset(panel_state="disarmed"):
        await everyone("home", 0.5)
        hass.states.async_set(P, panel_state)
        hass.states.async_set(P_ZONE, "disarmed")
        await asyncio.sleep(0.3)
        calls.clear()

    def button(prefix):
        acts = [a for d in pushes() for a in (d.get("data") or {}).get("actions", [])]
        return [a for a in acts if a["action"].startswith(prefix)]

    # 1. Both leave and stay gone -> armed away, with the code
    await reset()
    await everyone("not_home", 5)
    arms = took("alarm_control_panel.alarm_arm_away")
    check("everyone left -> armed away", [a for a in arms if a["entity_id"] == [P]], calls)
    check("armed with the code", [a for a in arms if a["entity_id"] == [P] and a.get("code") == "1234"], arms)
    check("'Alarm armed (away)' push", titled("Alarm armed (away)"), pushes())

    # 2. Flapping: gone, one back within the delay -> no arm
    await reset()
    await everyone("not_home", 1)
    hass.states.async_set(A, "home", {"friendly_name": "Alice"}); await asyncio.sleep(4)
    check("back within the delay -> not armed", not [a for a in took("alarm_control_panel.alarm_arm_away")
                                                     if a["entity_id"] == [P]], calls)

    # 3. Guest mode -> not armed, told why, no waiting
    await reset()
    hass.states.async_set("input_boolean.guest", "on")
    await everyone("not_home", 5)
    nope = titled("Alarm NOT armed")
    check("guest mode -> not armed, told why", nope and "guest mode" in nope[0]["message"]
          and not [a for a in took("alarm_control_panel.alarm_arm_away") if a["entity_id"] == [P]], pushes())
    hass.states.async_set("input_boolean.guest", "off")

    # 4a. Motion just BEFORE leaving (your own walk out) -> still arms
    await reset()
    hass.states.async_set("binary_sensor.motion", "on", {"friendly_name": "Hall Motion"}); await asyncio.sleep(0.2)
    hass.states.async_set("binary_sensor.motion", "off", {"friendly_name": "Hall Motion"}); await asyncio.sleep(0.2)
    await everyone("not_home", 5)
    check("motion before leaving -> still arms", hass.states.get(P).state == "armed_away", hass.states.get(P))

    # 4b. Motion AFTER everyone left -> not armed; "Arm anyway" arms
    await reset()
    await everyone("not_home", 1)
    hass.states.async_set("binary_sensor.motion", "on", {"friendly_name": "Hall Motion"}); await asyncio.sleep(0.2)
    hass.states.async_set("binary_sensor.motion", "off", {"friendly_name": "Hall Motion"})
    await asyncio.sleep(4)
    nope = titled("Alarm NOT armed")
    check("recent motion -> not armed, names the sensor", nope and "Hall Motion" in nope[0]["message"], pushes())
    btn = button("PRESENCE_ARM_ANYWAY_")
    check("blocked push offers 'Arm anyway'", btn and btn[0]["title"] == "Arm anyway", btn)
    if btn:
        hass.bus.async_fire("mobile_app_notification_action", {"action": btn[0]["action"]})
        await asyncio.sleep(1)
    check("'Arm anyway' arms", hass.states.get(P).state == "armed_away", hass.states.get(P))

    # 5. Window open (block) -> not armed, names it
    await reset()
    hass.states.async_set("binary_sensor.window", "on", {"friendly_name": "Kitchen Window"})
    await everyone("not_home", 5)
    nope = titled("Alarm NOT armed")
    check("open window -> not armed, names it", nope and "Kitchen Window" in nope[0]["message"]
          and hass.states.get(P).state == "disarmed", pushes())
    hass.states.async_set("binary_sensor.window", "off", {"friendly_name": "Kitchen Window"})

    # 6. Panel refuses to arm -> warned
    await reset()
    PANEL["refuse_arm"] = True
    await everyone("not_home", 16)
    check("panel refused -> 'Alarm did NOT arm'", titled("Alarm did NOT arm"), pushes())
    PANEL["refuse_arm"] = False

    # 7. Arrival, "ask": push with an unlock-required Disarm button
    await reset("armed_away")
    await everyone("not_home", 0.3)
    calls.clear()
    hass.states.async_set(A, "home", {"friendly_name": "Alice"}); await asyncio.sleep(3)
    ask = titled("Alice is home")
    btn = button("PRESENCE_DISARM_")
    check("arrival -> 'Alice is home' push", ask, pushes())
    check("Disarm button needs unlock", btn and btn[0].get("authenticationRequired") is True, btn)
    check("not disarmed until asked", hass.states.get(P).state == "armed_away", hass.states.get(P))
    if btn:
        hass.bus.async_fire("mobile_app_notification_action", {"action": btn[0]["action"]})
        await asyncio.sleep(1)
    dis = [d for d in took("alarm_control_panel.alarm_disarm") if d["entity_id"] == [P]]
    check("Disarm button disarms with the code", dis and dis[0].get("code") == "1234"
          and hass.states.get(P).state == "disarmed", dis)
    check("'Alarm disarmed' push", titled("Alarm disarmed"), pushes())

    # 8. Arrival while armed night -> ignored
    await reset("armed_night")
    await everyone("not_home", 0.3)
    calls.clear()
    hass.states.async_set(A, "home", {"friendly_name": "Alice"}); await asyncio.sleep(3)
    check("armed night -> arrival ignored", not titled("Alice is home"), pushes())

    # 9. Arrival flapping (home < arrive_delay) -> ignored
    await reset("armed_away")
    await everyone("not_home", 0.3)
    calls.clear()
    hass.states.async_set(A, "home", {"friendly_name": "Alice"}); await asyncio.sleep(0.5)
    hass.states.async_set(A, "not_home", {"friendly_name": "Alice"}); await asyncio.sleep(3)
    check("brief 'home' blip -> ignored", not titled("Alice is home"), pushes())

    # 10. Legacy zone mode + old auto_disarm: arms and disarms automatically
    await reset()
    hass.states.async_set(P, "armed_night")  # keep the people automation out of it
    hass.states.async_set("zone.home", "0"); await asyncio.sleep(1)
    check("zone empty -> legacy automation arms", hass.states.get(P_ZONE).state == "armed_away", hass.states.get(P_ZONE))
    hass.states.async_set("zone.home", "1"); await asyncio.sleep(1)
    check("old auto_disarm still disarms automatically", hass.states.get(P_ZONE).state == "disarmed",
          hass.states.get(P_ZONE))

    # 10b. Picked phone (device_tracker) + Arm as Vacation + automatic disarm
    await reset()
    hass.states.async_set(P, "armed_night")  # keep the people automation out of it
    hass.states.async_set(PH, "not_home", {"friendly_name": "Charles iPhone"}); await asyncio.sleep(5)
    check("picked phone away -> armed as Vacation", hass.states.get(P_PHONE).state == "armed_vacation",
          hass.states.get(P_PHONE))
    hass.states.async_set(PH, "home", {"friendly_name": "Charles iPhone"}); await asyncio.sleep(1)
    check("picked phone home -> disarmed automatically", hass.states.get(P_PHONE).state == "disarmed",
          hass.states.get(P_PHONE))
    check("disarm push names the phone", [d for d in pushes() if "Charles iPhone arrived" in d.get("message", "")],
          pushes())

    # 11. Missing-phone check: reload clears, removing the phone warns, nothing else happens
    await reset()
    hass.bus.async_fire("automation_reloaded", {}); await asyncio.sleep(1)
    check("phone present -> warning cleared",
          "missing_phone_automation.pres" in [d["notification_id"] for d in took("persistent_notification.dismiss")], calls)
    calls.clear()
    device_registry.async_get(hass).async_remove_device(phone.id); await asyncio.sleep(1)
    check("phone removed -> warning raised",
          "missing_phone_automation.pres" in [d["notification_id"] for d in took("persistent_notification.create")], calls)
    check("phone check does not arm or push", not pushes() and not took("alarm_control_panel.alarm_arm_away"), calls)

    await hass.async_stop(force=True)
    print(f"\n{sum(ok)}/{len(ok)} passed")
    sys.exit(0 if all(ok) else 1)


asyncio.run(main())
