"""Runtime check for the Noonlight / alarm blueprints.

Loads the blueprints from this repo into a real, headless Home Assistant core,
replaces notify / Noonlight / alarm panel actions with recorders, and plays
through the safety scenarios (cancel, disarm, dispatch-now, each mode, failed
dispatch, missing integration, webhooks, presence). No network, no Noonlight.

    pip install homeassistant
    python tests/runtime_test.py        # ~2.5 minutes, exits 1 on any FAIL

Set DEBUG=1 for automation step logs.
"""
import asyncio, logging, os, shutil, sys, tempfile
from pathlib import Path
logging.basicConfig(level=logging.WARNING, format="%(asctime)s %(name)s %(message)s")
if os.environ.get("DEBUG"):
    logging.getLogger("homeassistant.components.automation").setLevel(logging.DEBUG)
from homeassistant import core, loader
from homeassistant.setup import async_setup_component
from homeassistant.helpers import (area_registry, entity_registry, device_registry, floor_registry,
                                   label_registry, category_registry, issue_registry)

REPO = Path(__file__).resolve().parent.parent
CFG = tempfile.mkdtemp(prefix="nl-bp-test-")
shutil.copytree(REPO / "blueprints" / "automation", Path(CFG) / "blueprints" / "automation" / "ChuckBuilds")
calls = []          # (service, data)
P = "alarm_control_panel.home_alarm"
MODE = "input_select.noonlight_mode"


def bp(path, **inputs):
    return {"use_blueprint": {"path": f"ChuckBuilds/{path}", "input": inputs}}


async def main():
    hass = core.HomeAssistant(CFG)
    loader.async_setup(hass)
    for reg in (category_registry, floor_registry, label_registry, area_registry,
                device_registry, entity_registry, issue_registry):
        await reg.async_load(hass)
    hass.config.skip_pip = True
    from homeassistant import config_entries
    hass.config_entries = config_entries.ConfigEntries(hass, {})
    await hass.config_entries.async_initialize()
    await hass.async_start()

    def rec(name):
        async def handler(call):
            calls.append((name, dict(call.data)))
            if name == "input_text.set_value":
                for e in call.data["entity_id"]:
                    hass.states.async_set(e, call.data["value"])
            if name.startswith("alarm_control_panel."):
                new = {"alarm_trigger": "triggered", "alarm_disarm": "disarmed",
                       "alarm_arm_away": "armed_away"}[name.split(".")[1]]
                for e in call.data["entity_id"]:
                    hass.states.async_set(e, new)
            if name == "noonlight.create_alarm":
                # mimic the integration: attempted, then created or failed
                env = "sandbox" if "sandbox" in call.data.get("api_endpoint", "") else "production"
                base = {"environment": env, "alarm_cause": call.data.get("alarm_cause"),
                        "services": [call.data["service"]], "api_endpoint": call.data.get("api_endpoint")}
                hass.bus.async_fire("noonlight_alarm_attempted", base)
                await asyncio.sleep(0.2)
                if env == "sandbox" and not call.data.get("server_token_override"):
                    hass.bus.async_fire("noonlight_alarm_failed", {**base, "error": "no sandbox token"})
                else:
                    hass.bus.async_fire("noonlight_alarm_created", {**base, "alarm_id": "ABC123", "status": "ACTIVE"})
            if name == "noonlight.cancel_alarm":
                hass.bus.async_fire("noonlight_alarm_canceled", {"alarm_id": call.data["alarm_id"], "environment": "production"})
        return handler

    for svc in ["notify.mobile_app_me", "notify.family", "logbook.log", "persistent_notification.create",
                "input_text.set_value", "noonlight.create_alarm", "noonlight.cancel_alarm",
                "alarm_control_panel.alarm_trigger", "alarm_control_panel.alarm_disarm",
                "alarm_control_panel.alarm_arm_away"]:
        d, s = svc.split(".")
        hass.services.async_register(d, s, rec(svc))

    hass.states.async_set(P, "disarmed")
    hass.states.async_set(MODE, "Off")
    hass.states.async_set("input_text.noonlight_last_trigger", "")
    hass.states.async_set("input_text.noonlight_last_alarm_id", "")
    for s in ["binary_sensor.front_door", "binary_sensor.smoke", "binary_sensor.motion"]:
        hass.states.async_set(s, "off")
    hass.states.async_set("zone.home", "1")
    hass.states.async_set("lock.front", "locked")
    from homeassistant import config_entries as ce
    phone_entry = ce.ConfigEntry(data={}, domain="mobile_app", title="me", version=1, minor_version=1,
                                 source="user", options={}, unique_id="me", discovery_keys={},
                                 subentries_data=None)
    hass.config_entries._entries[phone_entry.entry_id] = phone_entry
    phone = device_registry.async_get(hass).async_get_or_create(
        config_entry_id=phone_entry.entry_id, identifiers={("mobile_app", "me")}, name="me")

    assert await async_setup_component(hass, "automation", {"automation": [
        {"id": "trip", "alias": "trip", **bp("alarm_sensor_trigger.yaml", alarm_panel=P,
                           sensors=["binary_sensor.front_door", "binary_sensor.motion"], debounce=0,
                           last_trigger_helper="input_text.noonlight_last_trigger")},
        {"id": "police", "alias": "police", **bp("noonlight_dispatch.yaml", trigger_entities=[P], alarm_panel=P,
                             last_trigger_helper="input_text.noonlight_last_trigger", service="police",
                             mode_helper=MODE, sandbox_token="SBTOKEN", instructions="dog inside",
                             notify_devices=[phone.id], notify_service="notify.does_not_exist",
                             on_triggered_actions=[{"action": "notify.also_missing"}],
                             camera="camera.front", tap_url="/lovelace/security",
                             extra_message="Lock: {{ states('lock.front') }}", countdown=10)},
        {"id": "fire", "alias": "fire", **bp("noonlight_dispatch.yaml", trigger_entities=["binary_sensor.smoke"], service="fire",
                           mode_helper=MODE, notify_service="notify.mobile_app_me", countdown=10)},
        {"id": "tracker", "alias": "tracker", **bp("noonlight_status_tracker.yaml", notify_devices=[phone.id],
                              household_notify_service="notify.family",
                              alarm_id_helper="input_text.noonlight_last_alarm_id",
                              cancel_service_available=True, result_timeout=10)},
        {"id": "presence", "alias": "presence", **bp("alarm_presence_arm_disarm.yaml", alarm_panel=P, arm_delay=0)},
    ]})
    await hass.async_block_till_done()
    for e in ["automation.trip", "automation.police", "automation.fire", "automation.tracker", "automation.presence"]:
        st = hass.states.get(e)
        assert st and st.state == "on", (e, st)

    def took(name):
        return [d for n, d in calls if n == name]

    def pushes():
        return [d.get("title", "") for n, d in calls if n.startswith("notify.mobile_app_me")]

    def last_push(prefix):
        return [d for n, d in calls if n == "notify.mobile_app_me" and d.get("title", "").startswith(prefix)]

    def press(action):
        hass.bus.async_fire("mobile_app_notification_action", {"action": action})

    def countdown_actions():
        d = [d for n, d in calls if n == "notify.mobile_app_me" and "actions" in d.get("data", {})][-1]
        return [a["action"] for a in d["data"]["actions"]]

    async def settle(t=0.5):
        # plain sleep: block_till_done would wait out the whole countdown
        await asyncio.sleep(t)

    async def reset(mode):
        calls.clear()
        hass.states.async_set(P, "disarmed")
        hass.states.async_set("binary_sensor.front_door", "off", {"device_class": "door"})
        hass.states.async_set("binary_sensor.smoke", "off")
        hass.states.async_set(MODE, mode)
        await settle(1)
        calls.clear()

    results = []

    def check(name, cond, detail=""):
        results.append((name, bool(cond)))
        print(("PASS " if cond else "FAIL ") + name + ("" if cond else f"  -> {detail}"))

    # 1. sensor guard: unavailable -> on does not trip; armed_home not counted
    await reset("Off")
    hass.states.async_set(P, "armed_away")
    hass.states.async_set("binary_sensor.front_door", "unavailable", {"device_class": "door"}); await settle()
    hass.states.async_set("binary_sensor.front_door", "on", {"device_class": "door"}); await settle()
    check("unavailable->on ignored", not took("alarm_control_panel.alarm_trigger"), calls)
    hass.states.async_set("binary_sensor.front_door", "off", {"device_class": "door"}); hass.states.async_set(P, "armed_home"); await settle()
    hass.states.async_set("binary_sensor.front_door", "on", {"device_class": "door"}); await settle()
    check("armed_home not counted by default", not took("alarm_control_panel.alarm_trigger"), calls)

    # 2. Off mode: sensor trips panel -> countdown -> dry run, no Noonlight
    await reset("Off")
    hass.states.async_set(P, "armed_away")
    hass.states.async_set("binary_sensor.front_door", "on", {"device_class": "door"}); await settle(1)
    check("sensor trips panel", took("alarm_control_panel.alarm_trigger"))
    check("trip records what happened", hass.states.get("input_text.noonlight_last_trigger").state == "front door opened",
          hass.states.get("input_text.noonlight_last_trigger"))
    check("countdown push sent", any(t.startswith("Police alarm: ") for t in pushes()), pushes())
    # dedup: second sensor during countdown
    hass.states.async_set("binary_sensor.motion", "on", {"device_class": "motion"}); await settle()
    check("no second countdown", sum(t.startswith("Police alarm: ") for t in pushes()) == 1, pushes())
    await settle(11)
    check("Off -> DRY RUN push", last_push("Police alarm - DRY RUN"), pushes())
    check("Off -> no create_alarm", not took("noonlight.create_alarm"))
    hass.states.async_set("binary_sensor.motion", "off", {"device_class": "motion"})

    # 3. Live + Cancel button
    await reset("Live")
    hass.states.async_set(P, "triggered"); await settle()
    press(countdown_actions()[0]); await settle()
    check("Live cancel button -> cancelled push", last_push("Police alarm cancelled"), pushes())
    check("Live cancel button -> no create_alarm", not took("noonlight.create_alarm"))

    # 4. Live + stale button from an old notification does nothing
    await reset("Live")
    hass.states.async_set(P, "triggered"); await settle()
    press("NOONLIGHT_PRECANCEL_oldcontext"); await settle()
    check("stale cancel ignored", not last_push("Police alarm cancelled"))
    # 5. ... then disarm cancels
    hass.states.async_set(P, "disarmed"); await settle()
    check("disarm cancels", last_push("Police alarm cancelled") and not took("noonlight.create_alarm"), pushes())

    # 6. Live + Dispatch now -> production endpoint, no sandbox token, tracker reports ACTIVE
    await reset("Live")
    hass.states.async_set(P, "triggered"); await settle()
    press(countdown_actions()[1]); await settle(1.5)
    ca = took("noonlight.create_alarm")
    check("Live dispatch-now calls create_alarm once", len(ca) == 1, ca)
    check("bad notify target + failing custom action don't stop dispatch", len(ca) == 1, ca)
    cd = [d for n, d in calls if n == "notify.mobile_app_me" and d.get("title", "").startswith("Police alarm: ")]
    check("phone picker -> notify.mobile_app_me", cd, pushes())
    if cd:
        data, msg = cd[0]["data"], cd[0]["message"]
        check("push title names the sensor", "front door" in cd[0]["title"], cd[0]["title"])
        check("camera snapshot + live feed", data.get("image") == "/api/camera_proxy/camera.front"
              and data.get("entity_id") == "camera.front", data)
        check("tap opens dashboard (iOS + Android)", data.get("url") == "/lovelace/security"
              and data.get("clickAction") == "/lovelace/security", data)
        check("extra message template rendered", "Lock: locked" in msg, msg)
        check("countdown push still critical with buttons", data.get("push", {}).get("interruption-level") == "critical"
              and len(data.get("actions", [])) == 2, data)
    check("Live uses production endpoint", ca and ca[0].get("api_endpoint") == "https://api.noonlight.com/dispatch/v1", ca)
    check("Live sends no sandbox token", ca and "server_token_override" not in ca[0], ca)
    check("alarm_cause names the sensor", ca and "front door" in ca[0].get("alarm_cause", ""), ca)
    check("tracker ACTIVE push", last_push("Noonlight LIVE Police alarm ACTIVE"), pushes())
    check("household told", [d for n, d in calls if n == "notify.family"], calls)
    check("alarm id stored", hass.states.get("input_text.noonlight_last_alarm_id").state == "ABC123")
    act = last_push("Noonlight LIVE Police alarm ACTIVE")[0]["data"]["actions"]
    check("ACTIVE push has cancel button", act and act[0]["action"] == "NOONLIGHT_CANCEL_ABC123", act)
    press("NOONLIGHT_CANCEL_ABC123"); await settle()
    check("cancel button -> cancel_alarm(ABC123)", took("noonlight.cancel_alarm") == [{"alarm_id": "ABC123"}], took("noonlight.cancel_alarm"))
    check("cancel confirmed push", last_push("Noonlight alarm cancelled"), pushes())

    # 7. Test mode, timeout -> sandbox endpoint + token
    await reset("Test")
    hass.states.async_set(P, "triggered"); await settle(11.5)
    ca = took("noonlight.create_alarm")
    check("Test -> sandbox endpoint + token", ca and ca[0]["api_endpoint"].startswith("https://api-sandbox") and ca[0]["server_token_override"] == "SBTOKEN", ca)

    # 8. Fire, Test mode, no token -> integration fails closed -> FAILED critical push
    await reset("Test")
    hass.states.async_set("binary_sensor.smoke", "on"); await settle(11.5)
    check("Fire countdown push (notify_service only)", any(t.startswith("Fire alarm: ") for t in pushes()), pushes())
    check("missing token -> FAILED push", last_push("Noonlight alarm FAILED"), pushes())

    # 9. invalid mode -> NOT SENT
    await reset("Banana")
    hass.states.async_set(P, "triggered"); await settle(11.5)
    check("invalid mode -> NOT SENT, no create", last_push("Police alarm NOT SENT") and not took("noonlight.create_alarm"), pushes())

    # 10. Local mode -> simulated events -> tracker -> cancel locally
    await reset("Local")
    hass.states.async_set(P, "triggered"); await settle(12.5)
    lp = last_push("Noonlight LOCAL TEST Police alarm ACTIVE")
    check("Local -> simulated ACTIVE push", lp, pushes())
    check("Local -> no real create_alarm", not took("noonlight.create_alarm"))
    if lp:
        press(lp[0]["data"]["actions"][0]["action"]); await settle()
    check("Local cancel -> cancelled push, no cancel_alarm call",
          last_push("Noonlight alarm cancelled") and not took("noonlight.cancel_alarm"), pushes())
    check("Local -> no 'no response' warning", not last_push("Noonlight: no response"), pushes())

    # 11. webhooks: list payload, dict payload without meta
    calls.clear()
    hass.bus.async_fire("noonlight_webhook_received", {"webhook_id": "x", "payload": [
        {"event_type": "alarm.psap_contacted", "meta": {"alarm_id": "ABC123"}},
        {"event_type": "alarm.status.canceled", "meta": {"alarm_id": "ABC123", "canceled_by": {"phone": "15555550100"}}}]})
    hass.bus.async_fire("noonlight_webhook_received", {"webhook_id": "x", "payload": {"raw_body": "junk"}})
    await settle(1)
    msgs = [d["message"] for n, d in calls if n == "notify.mobile_app_me"]
    check("webhook psap text", any("contacted 911" in m for m in msgs), msgs)
    check("webhook canceled-by phone", any("15555550100" in m for m in msgs), msgs)
    check("webhook junk handled", any("Noonlight update: unknown" in m for m in msgs), msgs)

    # 12. integration missing in Live -> dispatch run dies -> tracker watchdog warns
    hass.services.async_remove("noonlight", "create_alarm")
    await reset("Live")
    hass.states.async_set(P, "triggered"); await settle(11)
    check("missing integration: no result yet", not last_push("Noonlight: no response"), pushes())
    await settle(11)
    check("missing integration -> no-response warning", last_push("Noonlight: no response"), pushes())

    # 12b. motion wording
    await reset("Off")
    hass.states.async_set("binary_sensor.motion", "off", {"device_class": "motion"})
    hass.states.async_set(P, "armed_away"); await settle()
    hass.states.async_set("binary_sensor.motion", "on", {"device_class": "motion"}); await settle(1)
    check("motion trip says 'Motion detected'", hass.states.get("input_text.noonlight_last_trigger").state == "Motion detected: motion",
          hass.states.get("input_text.noonlight_last_trigger"))
    hass.states.async_set("binary_sensor.motion", "off", {"device_class": "motion"})
    await settle(11)

    # 13. presence: everyone leaves -> armed away; arrive -> no auto disarm (default)
    await reset("Off")
    hass.states.async_set("zone.home", "0"); await settle(1)
    check("presence arms when empty", took("alarm_control_panel.alarm_arm_away"), calls)
    hass.states.async_set("zone.home", "1"); await settle(1)
    check("presence does not auto-disarm by default", not took("alarm_control_panel.alarm_disarm"), calls)

    await hass.async_stop(force=True)
    failed = [n for n, ok in results if not ok]
    print(f"\n{len(results) - len(failed)}/{len(results)} passed")
    sys.exit(1 if failed else 0)


asyncio.run(main())
