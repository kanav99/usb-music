#!/usr/bin/env python3
"""
Event-driven: uses a single long-lived `pactl subscribe` connection instead
of polling, so there's zero background CPU/process churn at idle. This
avoids interfering with time-sensitive Bluetooth operations like multipoint
source switching.
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
STEP_PERCENT = 100 / 16
MAX_STEPS_PER_EVENT = 8

_last_volume = {}
_index_to_name = {}


def send_key(bitmask):
    try:
        with open(HIDG_DEVICE, "wb") as f:
            f.write(bytes([bitmask]))
        time.sleep(0.03)
        with open(HIDG_DEVICE, "wb") as f:
            f.write(bytes([0x00]))
        time.sleep(0.03)
    except OSError as e:
        log.error(f"Failed to write to {HIDG_DEVICE}: {e}")


def pactl(*args):
    result = subprocess.run(
        ["sudo", "-u", PULSE_USER, "pactl", f"--server={SERVER}"] + list(args),
        capture_output=True, text=True
    )
    return result.stdout, result.returncode


def refresh_sink_index_map():
    out, rc = pactl("list", "short", "sinks")
    if rc != 0:
        return
    _index_to_name.clear()
    for line in out.splitlines():
        parts = line.split("\t")
        if len(parts) >= 2 and parts[1].startswith("bluez_sink."):
            _index_to_name[parts[0]] = parts[1]


def get_sink_volume_percent(sink_name):
    out, rc = pactl("get-sink-volume", sink_name)
    if rc != 0:
        return None
    m = re.search(r"(\d+)%", out)
    return int(m.group(1)) if m else None


def handle_sink_change(sink_index):
    sink_name = _index_to_name.get(sink_index)
    if not sink_name:
        return

    pct = get_sink_volume_percent(sink_name)
    if pct is None:
        return

    prev = _last_volume.get(sink_name)
    _last_volume[sink_name] = pct

    if prev is None or pct == prev:
        return

    delta = pct - prev
    steps = max(1, min(round(abs(delta) / STEP_PERCENT), MAX_STEPS_PER_EVENT))
    key = KEY_VOL_UP if delta > 0 else KEY_VOL_DOWN
    log.info(f"{sink_name}: {prev}% -> {pct}% (Δ{delta:+d}%) -> sending {steps} key(s)")
    for _ in range(steps):
        send_key(key)


def main():
    log.info("Building initial bluez sink index map...")
    refresh_sink_index_map()
    for name in _index_to_name.values():
        pct = get_sink_volume_percent(name)
        if pct is not None:
            _last_volume[name] = pct
            log.info(f"Baseline {name}: {pct}%")

    log.info("Subscribing to PulseAudio events (single persistent connection)...")
    proc = subprocess.Popen(
        ["sudo", "-u", PULSE_USER, "pactl", f"--server={SERVER}", "subscribe"],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        bufsize=1,
        universal_newlines=True,
    )

    sink_event_re = re.compile(r"Event '(\w+)' on sink #(\d+)")

    for line in proc.stdout:
        m = sink_event_re.search(line)
        if not m:
            continue
        event_type, sink_index = m.group(1), m.group(2)
        if event_type in ("new", "remove"):
            refresh_sink_index_map()
        elif event_type == "change":
            handle_sink_change(sink_index)


if __name__ == "__main__":
    main()