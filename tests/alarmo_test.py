"""Real-Alarmo check for the Noonlight blueprints.

runtime_test.py fakes the alarm panel. This test runs the real Alarmo
integration instead, loads examples/noonlight_alarmo_automations.yaml as-is
(entity IDs swapped for test ones), and plays through what a household does:
arming with codes, doors / windows / motion per mode, the Disarm button,
keypad disarm before and after dispatch, three doors at once, sensor dropouts,
arming with a door open, fire, and each Noonlight mode. Noonlight and phones
are recorded mocks; nothing leaves the machine.

    pip install homeassistant paho-mqtt
    python tests/alarmo_test.py          # ~1 minute, exits 1 on any FAIL

Alarmo is downloaded from its GitHub release (ALARMO_VERSION, default below)
unless ALARMO_DIR points at a custom_components/alarmo folder, e.g. a copy
of the one installed on your Home Assistant.
"""
import asyncio, base64, io, json, logging, os, shutil, subprocess, sys, tarfile, tempfile, urllib.request
from pathlib import Path

logging.basicConfig(level=logging.CRITICAL)
REPO = Path(__file__).resolve().parent.parent
ALARMO_VERSION = os.environ.get("ALARMO_VERSION", "v1.10.19")
CODE = "1234"
PANEL = "alarm_control_panel.alarmo"
MODE = "input_select.noonlight_mode"
FRONT, BACK = "binary_sensor.front_door", "binary_sensor.back_door"
WINDOW, MOTION = "binary_sensor.office_window", "binary_sensor.living_room_motion"
SMOKE, CO = "binary_sensor.hallway_smoke", "binary_sensor.hallway_co"
PHONE, PARTNER = "notify.mobile_app_your_phone", "notify.mobile_app_partner_phone"
SIREN = "switch.alarm_panel_pro_siren"


def get_alarmo(dest: Path):
    src = os.environ.get("ALARMO_DIR")
    if src:
        shutil.copytree(src, dest)
        return f"ALARMO_DIR={src}"
    url = f"https://github.com/nielsfaber/alarmo/archive/refs/tags/{ALARMO_VERSION}.tar.gz"
    with urllib.request.urlopen(url, timeout=60) as r:
        tar = tarfile.open(fileobj=io.BytesIO(r.read()))
    for m in tar.getmembers():
        parts = Path(m.name).parts
        if len(parts) > 2 and parts[1:3] == ("custom_components", "alarmo") and m.isfile():
            rel = Path(*parts[3:])
            out = dest / rel
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_bytes(tar.extractfile(m).read())
    return f"Alarmo {ALARMO_VERSION} from GitHub"


def alarmo_store(entry_time):
    import bcrypt
    h = base64.b64encode(bcrypt.hashpw(CODE.encode(), bcrypt.gensalt(rounds=4))).decode()
    mode = lambda: {"enabled": True, "exit_time": 0, "entry_time": entry_time, "trigger_time": 1800}
    all_modes = ["armed_away", "armed_home", "armed_night"]
    def sensor(eid, typ, modes):
        return {"entity_id": eid, "type": typ, "modes": modes, "use_exit_delay": True,
                "use_entry_delay": True, "always_on": False, "arm_on_close": False,
                "allow_open": False, "trigger_unavailable": False, "auto_bypass": False,
                "auto_bypass_modes": [], "area": "1", "enabled": True, "entry_delay": None,
                "delay_on": None}
    return {"version": 6, "minor_version": 3, "key": "alarmo.storage", "data": {
        "config": {"code_arm_required": True, "code_mode_change_required": True,
                   "code_disarm_required": True, "code_format": "number",
                   "disarm_after_trigger": False, "ignore_blocking_sensors_after_trigger": False,
                   "master": {"enabled": False, "name": "master"},
                   "mqtt": {"enabled": False, "state_topic": "alarmo/state", "state_payload": {},
                            "command_topic": "alarmo/command", "command_payload": {},
                            "require_code": True, "event_topic": "alarmo/event"}},
        "areas": [{"area_id": "1", "name": "Alarmo",
                   "modes": {m: mode() for m in all_modes}}],
        "sensors": [sensor(FRONT, "door", all_modes), sensor(BACK, "door", all_modes),
                    sensor(WINDOW, "window", all_modes), sensor(MOTION, "motion", ["armed_away"])],
        "users": [{"user_id": "u1", "name": "Test", "enabled": True, "code": h, "can_arm": True,
                   "can_disarm": True, "is_override_code": False, "code_format": "number",
                   "code_length": 4, "area_limit": []}],
        "automations": [], "sensor_groups": []}}


def example_automations():
    """examples/noonlight_alarmo_automations.yaml with test entities and short timers."""
    import yaml
    class Loader(yaml.SafeLoader):
        pass
    secrets = {"alarmo_code": CODE, "noonlight_sandbox_token": "SBTOKEN"}
    Loader.add_constructor("!secret", lambda l, n: secrets[l.construct_scalar(n)])
    text = (REPO / "examples/noonlight_alarmo_automations.yaml").read_text()
    for old, new in {"camera.front_doorbell": "camera.test", "switch.alarm_panel_pro_siren": SIREN}.items():
        text = text.replace(old, new)
    autos = yaml.load(text, Loader=Loader)
    for a in autos:
        inp = a.get("use_blueprint", {}).get("input", {})
        if a["id"] == "noonlight_police":
            inp["countdown"] = 4
        if a["id"] == "noonlight_fire":
            inp["countdown"] = 3
        if a["id"] == "noonlight_status_tracker":
            inp["result_timeout"] = 5
    return autos


results = []
def check(name, ok, detail: object = ""):
    ok = bool(ok)
    results.append(ok)
    print(("PASS " if ok else "FAIL ") + name + ("" if ok else f"   -> {detail}"), flush=True)


async def run(entry_time):
    from homeassistant import bootstrap, core, loader, config_entries as ce
    from homeassistant.setup import async_setup_component

    cfg = Path(tempfile.mkdtemp(prefix="alarmo-test-"))
    shutil.copytree(REPO / "blueprints/automation", cfg / "blueprints/automation/ChuckBuilds")
    source = get_alarmo(cfg / "custom_components/alarmo")
    manifest = cfg / "custom_components/alarmo/manifest.json"
    m = json.loads(manifest.read_text())
    m["dependencies"], m["after_dependencies"] = [], []      # no frontend in a headless test
    manifest.write_text(json.dumps(m))
    (cfg / ".storage").mkdir()
    (cfg / ".storage/alarmo.storage").write_text(json.dumps(alarmo_store(entry_time)))

    hass = core.HomeAssistant(str(cfg))
    loader.async_setup(hass)
    hass.config.skip_pip = True
    hass.config_entries = ce.ConfigEntries(hass, {})
    await bootstrap.async_load_base_functionality(hass)
    await hass.async_start()

    calls, events = [], []
    def rec(name):
        async def handler(call):
            calls.append((name, dict(call.data)))
            if name == "noonlight.create_alarm":
                env = "sandbox" if "sandbox" in call.data.get("api_endpoint", "") else "production"
                base = {"environment": env, "alarm_cause": call.data["alarm_cause"],
                        "services": [call.data["service"]]}
                hass.bus.async_fire("noonlight_alarm_attempted", base)
                await asyncio.sleep(0.2)
                hass.bus.async_fire("noonlight_alarm_created", {**base, "alarm_id": "NL1", "status": "ACTIVE"})
            if name == "noonlight.cancel_alarm":
                hass.bus.async_fire("noonlight_alarm_canceled", {"alarm_id": call.data["alarm_id"]})
            if name == "input_text.set_value":
                for e in call.data["entity_id"]:
                    hass.states.async_set(e, call.data["value"])
        return handler
    for svc in [PHONE, PARTNER, "noonlight.create_alarm", "noonlight.cancel_alarm",
                "input_text.set_value", "switch.turn_on", "switch.turn_off", "logbook.log",
                "persistent_notification.create", "persistent_notification.dismiss",
                "tts.speak", "media_player.volume_set", "light.turn_on"]:
        d, s = svc.split(".")
        hass.services.async_register(d, s, rec(svc))
    hass.bus.async_listen("alarmo_failed_to_arm", lambda e: events.append(dict(e.data)))

    for eid, dc, name in [(FRONT, "door", "Front Door"), (BACK, "door", "Back Door"),
                          (WINDOW, "window", "Office Window"), (MOTION, "motion", "Living Room Motion"),
                          (SMOKE, "smoke", "Hallway Smoke"), (CO, "carbon_monoxide", "Hallway CO")]:
        hass.states.async_set(eid, "off", {"device_class": dc, "friendly_name": name})
    hass.states.async_set(MODE, "Live", {"options": ["Off", "Local", "Test", "Live"]})
    hass.states.async_set("input_text.noonlight_last_alarm_id", "")
    hass.states.async_set(SIREN, "off")

    import custom_components.alarmo as A
    import custom_components.alarmo.config_flow as AF
    async def noop(*a, **k):
        return None
    A.async_register_panel = A.async_register_card = A.async_register_websockets = noop
    A.async_unregister_panel = lambda *a, **k: None
    A.async_get_clientsession = lambda *a, **k: None
    entry = ce.ConfigEntry(data={}, domain="alarmo", title="Alarmo", version=AF.AlarmoConfigFlow.VERSION,
                           minor_version=1, source="user", options={}, unique_id=None,
                           discovery_keys={}, subentries_data=None)
    await hass.config_entries.async_add(entry)
    await hass.async_block_till_done()
    check(f"real Alarmo loads ({source})", hass.states.get(PANEL), hass.states.async_all("alarm_control_panel"))
    if not hass.states.get(PANEL):
        return

    assert await async_setup_component(hass, "automation", {"automation": example_automations()})
    await asyncio.sleep(0.5)

    # never hass.async_block_till_done() from here: the tracker legitimately waits up to an hour
    st = lambda: hass.states.get(PANEL).state
    named = lambda n: [c[1] for c in calls if c[0] == n]
    pushes = lambda: named(PHONE)
    def set_sensor(eid, state):
        hass.states.async_set(eid, state, hass.states.get(eid).attributes)
    async def panel(action, code=CODE):
        await hass.services.async_call("alarm_control_panel", action, {"entity_id": PANEL, "code": code},
                                       blocking=True)
        await asyncio.sleep(0.4)
    async def press(prefix):
        for p in reversed(pushes()):
            for a in p.get("data", {}).get("actions", []):
                if a["action"].startswith(prefix):
                    hass.bus.async_fire("mobile_app_notification_action", {"action": a["action"]})
                    await asyncio.sleep(1)
                    return a["action"]
    def reset():
        calls.clear(); events.clear()
    async def settle():
        for e in (FRONT, BACK, WINDOW, MOTION):
            set_sensor(e, "off")
        if st() != "disarmed":
            await panel("alarm_disarm")
        await asyncio.sleep(5)        # let any countdown / tracker wait finish

    await panel("alarm_arm_away", code="9999")
    check("wrong code does not arm", st() == "disarmed", st())
    await panel("alarm_arm_away")
    check("arm away with the code", st() == "armed_away", st())

    if entry_time:
        reset(); set_sensor(FRONT, "on"); await asyncio.sleep(1)
        check(f"entry time {entry_time} s: Alarmo sits in 'pending'", st() == "pending", st())
        check("...with no push yet (why entry time should be 0)", not pushes(), pushes())
        await asyncio.sleep(entry_time + 1)
        check("after the entry time: triggered and the countdown push", st() == "triggered" and pushes(), st())
        await settle()
        return

    # door while armed away; keypad disarm during the countdown
    reset(); set_sensor(FRONT, "on"); await asyncio.sleep(1)
    p = pushes()
    check("front door trips armed_away", st() == "triggered", st())
    check("push title 'Police alarm: Front Door opened (armed away)'",
          p and p[0]["title"] == "Police alarm: Front Door opened (armed away)", p[:1])
    check("push is critical on iOS and alarm_stream on Android",
          p and p[0]["data"]["push"]["interruption-level"] == "critical"
          and p[0]["data"]["channel"] == "alarm_stream", p[:1])
    check("buttons: Disarm (needs unlock), Cancel, Dispatch now",
          p and [a["title"] for a in p[0]["data"]["actions"]] == ["Disarm", "Cancel - I'm safe", "Dispatch now"]
          and p[0]["data"]["actions"][0]["authenticationRequired"] is True, p[:1])
    check("camera snapshot and tap-to-open on both platforms",
          p and p[0]["data"].get("image") == "/api/camera_proxy/camera.test"
          and p[0]["data"].get("url") == p[0]["data"].get("clickAction") == "/lovelace/security", p[:1])
    check("siren on when the countdown starts", named("switch.turn_on"), calls)
    set_sensor(FRONT, "off"); await panel("alarm_disarm"); await asyncio.sleep(1)
    check("keypad disarm during the countdown: Noonlight not called",
          st() == "disarmed" and not named("noonlight.create_alarm"), calls)
    check("...siren off and a 'disarmed' push",
          named("switch.turn_off") and any("disarmed" in x.get("title", "") for x in pushes()), pushes())
    await settle()

    # Disarm button: the panel code from secrets is accepted by Alarmo
    await panel("alarm_arm_home"); reset()
    set_sensor(WINDOW, "on"); await asyncio.sleep(1)
    check("window trips armed_home, named in the push",
          st() == "triggered" and pushes() and "Office Window opened (armed home)" in pushes()[0]["title"], pushes()[:1])
    await press("NOONLIGHT_DISARM_"); await asyncio.sleep(1)
    check("Disarm button disarms Alarmo with the code", st() == "disarmed", st())
    check("...and Noonlight is not called", not named("noonlight.create_alarm"), calls)
    await settle()

    # Cancel button: Noonlight not called, Alarmo stays triggered
    await panel("alarm_arm_home"); reset()
    set_sensor(BACK, "on"); await asyncio.sleep(1)
    await press("NOONLIGHT_PRECANCEL_"); await asyncio.sleep(1)
    check("Cancel button: Noonlight not called, push says still armed",
          not named("noonlight.create_alarm") and any("still armed" in x.get("message", "") for x in pushes()), pushes())
    await settle()

    # nobody answers: one dispatch for three sensors, tracker, keypad disarm cancels Noonlight
    await panel("alarm_arm_away"); reset()
    set_sensor(BACK, "on"); await asyncio.sleep(0.5)
    set_sensor(FRONT, "on"); await asyncio.sleep(0.5)
    set_sensor(WINDOW, "on"); await asyncio.sleep(6)
    ca = named("noonlight.create_alarm")
    check("countdown ends: create_alarm exactly once for three sensors", len(ca) == 1, ca)
    check("alarm cause names the first sensor",
          ca and ca[0]["alarm_cause"] == "Police alarm: Back Door opened (armed away)", ca)
    check("Live: production endpoint, no sandbox token",
          ca and ca[0]["api_endpoint"] == "https://api.noonlight.com/dispatch/v1"
          and "server_token_override" not in ca[0], ca)
    check("tracker: ACTIVE push, partner told, alarm ID saved",
          any("ACTIVE" in x.get("title", "") for x in pushes()) and named(PARTNER)
          and hass.states.get("input_text.noonlight_last_alarm_id").state == "NL1", pushes())
    for e in (BACK, FRONT, WINDOW):
        set_sensor(e, "off")
    await panel("alarm_disarm"); await asyncio.sleep(2)
    cc = named("noonlight.cancel_alarm")
    check("keypad disarm after dispatch cancels Noonlight once", len(cc) == 1 and cc[0]["alarm_id"] == "NL1", cc)
    await settle()

    # Test mode goes to the sandbox with the token from secrets
    hass.states.async_set(MODE, "Test", {"options": ["Off", "Local", "Test", "Live"]})
    await panel("alarm_arm_home"); reset()
    set_sensor(FRONT, "on"); await asyncio.sleep(6)
    ca = named("noonlight.create_alarm")
    check("Test: sandbox endpoint with the sandbox token",
          len(ca) == 1 and "api-sandbox" in ca[0]["api_endpoint"] and ca[0]["server_token_override"] == "SBTOKEN", ca)
    await settle()

    # Off mode: dry run only
    hass.states.async_set(MODE, "Off", {"options": ["Off", "Local", "Test", "Live"]})
    await panel("alarm_arm_home"); reset()
    set_sensor(FRONT, "on"); await asyncio.sleep(6)
    check("Off: DRY RUN push, Noonlight never called",
          not named("noonlight.create_alarm") and any("DRY RUN" in x.get("title", "") for x in pushes()), pushes())
    await settle()
    hass.states.async_set(MODE, "Live", {"options": ["Off", "Local", "Test", "Live"]})

    # motion only counts in away; sensor dropouts don't trip
    await panel("alarm_arm_home"); reset()
    set_sensor(MOTION, "on"); await asyncio.sleep(1)
    check("motion ignored in armed_home", st() == "armed_home" and not pushes(), (st(), pushes()))
    set_sensor(MOTION, "off")
    set_sensor(FRONT, "unavailable"); await asyncio.sleep(1)
    set_sensor(FRONT, "off"); await asyncio.sleep(1)
    check("sensor drops out and comes back closed: no alarm", st() == "armed_home" and not pushes(), (st(), pushes()))
    await settle()

    # arming with a door open: refused, and the example automation tells the phone
    reset(); set_sensor(BACK, "on"); await asyncio.sleep(0.5)
    await panel("alarm_arm_away"); await asyncio.sleep(1)
    check("arming with the back door open is refused", st() == "disarmed", st())
    check("...alarmo_failed_to_arm lists the door",
          events and events[0].get("reason") == "open_sensors" and BACK in events[0].get("sensors", []), events)
    check("...and the phone gets 'Alarm NOT armed - Still open: Back Door'",
          any(x.get("title") == "Alarm NOT armed" and "Back Door" in x.get("message", "") for x in pushes()), pushes())
    set_sensor(BACK, "off"); await asyncio.sleep(0.5)
    reset(); await panel("alarm_arm_away", code="0000"); await asyncio.sleep(1)
    check("wrong code: phone told 'Wrong or missing code'",
          any("Wrong or missing code" in x.get("message", "") for x in pushes()), (events, pushes()))
    await settle()

    # fire runs while disarmed and a disarm never cancels it
    reset(); set_sensor(CO, "on"); await asyncio.sleep(1)
    check("CO with Alarmo disarmed: Fire countdown push",
          any(x.get("title", "").startswith("Fire alarm") for x in pushes()), pushes())
    await asyncio.sleep(4)
    check("Fire countdown ends: create_alarm service=fire",
          any(c["service"] == "fire" for c in named("noonlight.create_alarm")), calls)
    await panel("alarm_arm_home"); await panel("alarm_disarm"); await asyncio.sleep(1)
    check("disarming during a fire alarm does not cancel it", not named("noonlight.cancel_alarm"), calls)


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "--entry-time":
        asyncio.run(run(int(sys.argv[2])))
    else:
        asyncio.run(run(0))
        print("-- entry time 3 s (a fresh Home Assistant) --", flush=True)
        r = subprocess.run([sys.executable, __file__, "--entry-time", "3"], capture_output=True, text=True)
        print(r.stdout, end="", flush=True)
        results.extend(l.startswith("PASS ") for l in r.stdout.splitlines() if l.startswith(("PASS ", "FAIL ")))
        if r.returncode:
            results.append(False)
            print(r.stderr[-2000:], flush=True)
    if len(sys.argv) == 1:
        print(f"\n{sum(results)}/{len(results)} passed", flush=True)
    os._exit(0 if all(results) else 1)   # skip HA shutdown: the tracker waits up to an hour


if __name__ == "__main__":
    main()
