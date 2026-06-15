#!/bin/bash
# Reconnect trusted BT headset at boot
HEADSET_MAC="07:01:69:96:E4:3B"   # ← replace with your headset MAC

MAX_RETRIES=10
RETRY_INTERVAL=3

for i in $(seq 1 $MAX_RETRIES); do
    echo "Attempt $i: connecting to $HEADSET_MAC..."
    if bluetoothctl connect "$HEADSET_MAC" 2>&1 | grep -q "Connection successful"; then
        echo "Connected to headset. Trying to load audio loopback module..."
        /usr/sbin/runuser -u kanav pactl load-module module-loopback source=alsa_input.platform-3f980000.usb.stereo-fallback sink=bluez_sink.07_01_69_96_E4_3B.a2dp_sink latency_msec=100
        exit 0
    fi
    sleep $RETRY_INTERVAL
done

echo "WARNING: Could not connect to headset after $MAX_RETRIES attempts."
exit 1
