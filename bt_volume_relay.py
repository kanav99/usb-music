#!/usr/bin/env python3
"""
Watches the PulseAudio volume of the active Bluetooth headset sink.
Headset volume buttons already sync to this value via BlueZ's AVRCP
absolute-volume support — this script just detects that change and
relays it onward to the laptop as a USB HID consumer-control keypress.
"""

import subprocess
import re
import time
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s INFO %(message)s")
log = logging.getLogger("bt-volume-relay")

PULSE_USER  = "kanav"
PULSE_UID   = 1000
HIDG_DEVICE = "/dev/hidg0"
SERVER      = f"unix:/run/user/{PULSE_UID}/pulse/native"

KEY_VOL_UP   = 0x20
KEY_VOL_DOWN = 0x40

POLL_INTERVAL = 0.3   # seconds

_last_volume = {}   # sink_name -> last seen volume percent


def send_key(bitmask):
    try:
        with open(HIDG_DEVICE, "wb") as f:
            f.write(bytes([bitmask]))
        time.sleep(0.05)
        with open(HIDG_DEVICE, "wb") as f:
            f.write(bytes([0x00]))
    except OSError as e:
        log.error(f"Failed to write to {HIDG_DEVICE}: {e}")


def pactl(*args):
    result = subprocess.run(
        ["sudo", "-u", PULSE_USER, "pactl", f"--server={SERVER}"] + list(args),
        capture_output=True, text=True
    )
    return result.stdout, result.returncode


def get_bluez_sink_volumes():
    """Returns {sink_name: volume_percent} for all connected bluez sinks."""
    out, rc = pactl("list", "sinks")
    if rc != 0:
        return {}
    volumes = {}
    current_name = None
    for line in out.splitlines():
        line = line.strip()
        m = re.match(r"Name:\s+(bluez_sink\.\S+)", line)
        if m:
            current_name = m.group(1)
            continue
        if current_name and line.startswith("Volume:"):
            pct_match = re.search(r"(\d+)%", line)
            if pct_match:
                volumes[current_name] = int(pct_match.group(1))
            current_name = None
    return volumes


def poll_loop():
    log.info("Watching Bluetooth sink volumes for button-press changes...")
    while True:
        volumes = get_bluez_sink_volumes()
        for sink_name, pct in volumes.items():
            prev = _last_volume.get(sink_name)
            if prev is not None and pct != prev:
                if pct > prev:
                    log.info(f"{sink_name}: {prev}% -> {pct}% (volume up)")
                    send_key(KEY_VOL_UP)
                else:
                    log.info(f"{sink_name}: {prev}% -> {pct}% (volume down)")
                    send_key(KEY_VOL_DOWN)
            _last_volume[sink_name] = pct
        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    poll_loop()