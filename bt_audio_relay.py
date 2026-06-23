#!/usr/bin/env python3
"""
Watches for Bluetooth headset connect/disconnect events via D-Bus
and loads/unloads PulseAudio loopback routing accordingly.
"""

import subprocess
import logging
import os
import dbus
import dbus.mainloop.glib
from gi.repository import GLib

# ── Config ────────────────────────────────────────────────────────────────────
HEADSET_MAC   = "07:01:69:96:E4:3B"
PULSE_USER    = "kanav"
PULSE_UID     = 1000   # from: id -u kanav
ALSA_DEVICE   = "hw:CARD=UAC2Gadget,DEV=0"
ALSA_SOURCE   = "alsa_input.platform-3f980000.usb.stereo-fallback"
BT_SINK       = f"bluez_sink.{HEADSET_MAC.replace(':', '_')}.a2dp_sink"
LATENCY_MS    = 100

HEADSET_DBUS_PATH = "/org/bluez/hci0/dev_" + HEADSET_MAC.replace(":", "_")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s"
)
log = logging.getLogger("bt-audio-relay")

# Track loaded module IDs so we can unload them cleanly
loaded_modules = {}


def pactl(*args):
    """Run a pactl command as the PulseAudio user."""
    env = os.environ.copy()
    env["XDG_RUNTIME_DIR"] = f"/run/user/{PULSE_UID}"
    result = subprocess.run(
        ["sudo", "-u", PULSE_USER, "pactl"] + list(args),
        env=env,
        capture_output=True,
        text=True
    )
    return result.stdout.strip(), result.returncode


def load_audio():
    log.info("Headset connected — loading audio routing...")

    # Load ALSA source (idempotent check)
    out, rc = pactl("load-module", "module-alsa-source",
                    f"device={ALSA_DEVICE}",
                    "rate=48000", "channels=2", "tsched=0")
    if rc != 0:
        log.error(f"Failed to load module-alsa-source: {out}")
        return
    loaded_modules["alsa_source"] = out.strip()
    log.info(f"Loaded module-alsa-source (id {loaded_modules['alsa_source']})")

    # Small delay for BT sink to register in PulseAudio
    GLib.timeout_add(2000, load_loopback)


def load_loopback():
    out, rc = pactl("load-module", "module-loopback",
                    f"source={ALSA_SOURCE}",
                    f"sink={BT_SINK}",
                    f"latency_msec={LATENCY_MS}")
    if rc != 0:
        log.error(f"Failed to load module-loopback: {out}")
    else:
        loaded_modules["loopback"] = out.strip()
        log.info(f"Loaded module-loopback (id {loaded_modules['loopback']})")
    return False  # don't repeat the timeout


def unload_audio():
    log.info("Headset disconnected — unloading audio routing...")
    for name in ("loopback", "alsa_source"):
        mod_id = loaded_modules.pop(name, None)
        if mod_id:
            _, rc = pactl("unload-module", mod_id)
            if rc == 0:
                log.info(f"Unloaded {name} (id {mod_id})")
            else:
                log.warning(f"Failed to unload {name} (id {mod_id})")


def on_properties_changed(interface, changed, invalidated, path):
    if interface != "org.bluez.Device1":
        return
    if path.lower() != HEADSET_DBUS_PATH.lower():
        return
    if "Connected" not in changed:
        return

    if changed["Connected"]:
        load_audio()
    else:
        unload_audio()


def main():
    dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
    bus = dbus.SystemBus()

    bus.add_signal_receiver(
        on_properties_changed,
        signal_name="PropertiesChanged",
        dbus_interface="org.freedesktop.DBus.Properties",
        path_keyword="path"
    )

    log.info(f"Watching for headset {HEADSET_MAC} connect/disconnect events...")

    # Check if already connected at startup
    try:
        obj  = bus.get_object("org.bluez", HEADSET_DBUS_PATH)
        props = dbus.Interface(obj, "org.freedesktop.DBus.Properties")
        if props.Get("org.bluez.Device1", "Connected"):
            log.info("Headset already connected at startup.")
            load_audio()
    except dbus.DBusException:
        log.info("Headset not currently connected.")

    GLib.MainLoop().run()


if __name__ == "__main__":
    main()