#!/usr/bin/env python3
"""
Watches multiple Bluetooth headsets via D-Bus and routes USB gadget audio
to whichever connected headset has the highest priority.
"""

import subprocess
import logging
import dbus
import dbus.mainloop.glib
from gi.repository import GLib

# ── Config ────────────────────────────────────────────────────────────────────
PULSE_USER  = "kanav"
PULSE_UID   = 1000
ALSA_DEVICE = "hw:CARD=UAC2Gadget,DEV=0"
ALSA_SOURCE = "alsa_input.platform-3f980000.usb.stereo-fallback"
LATENCY_MS  = 100

# Ordered by priority — first entry wins when multiple are connected
HEADSETS = [
    {"name": "GID8",      "mac": "7C:96:D2:F8:59:B1"},
    {"name": "Speaker 01", "mac": "07:01:69:96:E4:3B"},
]

def mac_to_path(mac):
    return "/org/bluez/hci0/dev_" + mac.replace(":", "_")

def mac_to_sink(mac):
    return f"bluez_sink.{mac.replace(':', '_')}.a2dp_sink"

for h in HEADSETS:
    h["path"] = mac_to_path(h["mac"])
    h["sink"] = mac_to_sink(h["mac"])
    h["connected"] = False

PATH_TO_HEADSET = {h["path"].lower(): h for h in HEADSETS}

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("bt-audio-relay")

# ── State ─────────────────────────────────────────────────────────────────────
state = {
    "alsa_source_id": None,
    "loopback_id": None,
    "active_mac": None,
}


def pactl(*args):
    server = f"unix:/run/user/{PULSE_UID}/pulse/native"
    result = subprocess.run(
        ["sudo", "-u", PULSE_USER, "pactl", f"--server={server}"] + list(args),
        capture_output=True, text=True
    )
    if result.returncode != 0:
        log.error(f"pactl {' '.join(args)} -> stderr: {result.stderr.strip()}")
    return result.stdout.strip(), result.returncode


def ensure_alsa_source():
    if state["alsa_source_id"]:
        return True
    out, rc = pactl("load-module", "module-alsa-source",
                    f"device={ALSA_DEVICE}", "rate=48000", "channels=2", "tsched=0")
    if rc != 0:
        return False
    state["alsa_source_id"] = out
    log.info(f"Loaded module-alsa-source (id {out})")
    return True


def unload_alsa_source():
    if state["alsa_source_id"]:
        pactl("unload-module", state["alsa_source_id"])
        log.info(f"Unloaded module-alsa-source (id {state['alsa_source_id']})")
        state["alsa_source_id"] = None


def unload_loopback():
    if state["loopback_id"]:
        pactl("unload-module", state["loopback_id"])
        log.info(f"Unloaded module-loopback (id {state['loopback_id']})")
        state["loopback_id"] = None
        state["active_mac"] = None


def route_to(headset):
    """Switch active routing to the given headset dict."""
    unload_loopback()  # drop old route first, if any

    if not ensure_alsa_source():
        log.error("Could not ensure alsa source — aborting route switch.")
        return

    out, rc = pactl("load-module", "module-loopback",
                    f"source={ALSA_SOURCE}", f"sink={headset['sink']}",
                    f"latency_msec={LATENCY_MS}")
    if rc != 0:
        return
    state["loopback_id"] = out
    state["active_mac"] = headset["mac"]
    log.info(f"Routing audio -> {headset['name']} ({headset['mac']})")


def reconcile():
    """Pick the highest-priority connected headset and route to it."""
    desired = next((h for h in HEADSETS if h["connected"]), None)

    if desired is None:
        log.info("No headsets connected — tearing down audio routing.")
        unload_loopback()
        unload_alsa_source()
        return

    if state["active_mac"] == desired["mac"]:
        return  # already correct

    # Give the newly connected BT sink a moment to register in PulseAudio
    GLib.timeout_add(2000, lambda: (route_to(desired), False)[1])


def on_properties_changed(interface, changed, invalidated, path):
    if interface != "org.bluez.Device1" or "Connected" not in changed:
        return
    headset = PATH_TO_HEADSET.get(path.lower())
    if not headset:
        return

    headset["connected"] = bool(changed["Connected"])
    log.info(f"{headset['name']} ({headset['mac']}) connected={headset['connected']}")
    reconcile()


def check_initial_state(bus):
    for h in HEADSETS:
        try:
            obj = bus.get_object("org.bluez", h["path"])
            props = dbus.Interface(obj, "org.freedesktop.DBus.Properties")
            h["connected"] = bool(props.Get("org.bluez.Device1", "Connected"))
            log.info(f"{h['name']} initial connected={h['connected']}")
        except dbus.DBusException:
            h["connected"] = False
    reconcile()


def main():
    dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
    bus = dbus.SystemBus()

    bus.add_signal_receiver(
        on_properties_changed,
        signal_name="PropertiesChanged",
        dbus_interface="org.freedesktop.DBus.Properties",
        path_keyword="path"
    )

    log.info("Watching headsets: " + ", ".join(f"{h['name']}({h['mac']})" for h in HEADSETS))
    check_initial_state(bus)
    GLib.MainLoop().run()


if __name__ == "__main__":
    main()