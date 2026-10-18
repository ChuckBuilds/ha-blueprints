"""Runtime check for the presence-activated lights blueprint.

Two sensors, 2 s hold time, a recorded light.turn_on / turn_off. Covers: lights
stay on while either sensor sees you, go off only after the LAST sensor has
been clear for the hold time, and a reload (dropped `for:` timer) still turns
them off.

    pip install homeassistant
    python tests/presence_lights_test.py        # ~15 s, exits 1 on any FAIL
"""
import asyncio, json, logging, shutil, sys, tempfile
from pathlib import Path
from homeassistant import config_entries, core, loader
from homeassistant.setup import async_setup_component
from homeassistant.helpers import (area_registry, category_registry, device_registry, entity_registry,
                                   floor_registry, issue_registry, label_registry)

logging.basicConfig(level=logging.CRITICAL)
REPO = Path(__file__).resolve().parent.parent
CFG = tempfile.mkdtemp(prefix="lights-bp-test-")
shutil.copytree(REPO / "blueprints" / "automation", Path(CFG) / "blueprints" / "automation" / "ChuckBuilds")
A, B, L = "binary_sensor.mmwave", "binary_sensor.pir", "light.room"
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
            calls.append(name)
            hass.states.async_set(L, "on" if name.endswith("turn_on") else "off")
        return handler

    for s in ("turn_on", "turn_off"):
        hass.services.async_register("light", s, rec(f"light.{s}"))
    for e in (A, B):
        hass.states.async_set(e, "off")
    hass.states.async_set(L, "off")
    autos = [{"id": "room", "alias": "room", "use_blueprint": {"path": "ChuckBuilds/presence_lights.yaml", "input": {
        "presence_sensors": [A, B], "lights": {"entity_id": L},
        "no_presence_wait": {"hours": 0, "minutes": 0, "seconds": 2}}}}]
    # automation.reload reads configuration.yaml; JSON is valid YAML
    (Path(CFG) / "configuration.yaml").write_text(json.dumps({"automation": autos}))
    assert await async_setup_component(hass, "automation", {"automation": autos})
    await asyncio.sleep(0.5)
    ok = []

    def check(name, cond):
        ok.append(bool(cond))
        print(("PASS " if cond else "FAIL ") + name + ("" if cond else f"  -> {calls}"))

    hass.states.async_set(A, "on"); await asyncio.sleep(0.3)
    check("presence turns the light on", hass.states.get(L).state == "on")
    hass.states.async_set(B, "on"); await asyncio.sleep(1)
    hass.states.async_set(A, "off"); await asyncio.sleep(1.5)
    hass.states.async_set(B, "off"); await asyncio.sleep(1)
    check("A clear for the hold time, B only just clear -> still on", hass.states.get(L).state == "on")
    await asyncio.sleep(1.5)
    check("last sensor clear for the hold time -> off", hass.states.get(L).state == "off")

    # Reload while a hold timer is pending: the `for:` is dropped.
    hass.states.async_set(A, "on"); await asyncio.sleep(0.3)
    hass.states.async_set(A, "off"); await asyncio.sleep(0.5)
    # HA only rebuilds changed automations, so change the alias to force it
    autos[0]["alias"] = "room renamed"
    (Path(CFG) / "configuration.yaml").write_text(json.dumps({"automation": autos}))
    await hass.services.async_call("automation", "reload", blocking=True)
    await asyncio.sleep(3)
    check("reload mid-hold -> re-check still turns it off", hass.states.get(L).state == "off")

    await hass.async_stop(force=True)
    print(f"\n{sum(ok)}/{len(ok)} passed")
    sys.exit(0 if all(ok) else 1)


asyncio.run(main())
