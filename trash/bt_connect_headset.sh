#!/bin/bash
# Reconnect trusted BT headset at boot
HEADSET_MAC="07:01:69:96:E4:3B"   # ← replace with your headset MAC
PULSE_USER="kanav"
PULSE_UID=1000   # from id -u kanav

MAX_RETRIES=10
RETRY_INTERVAL=3

# Wait for PulseAudio to be ready
for i in $(seq 1 $MAX_RETRIES); do
    if sudo -u "$PULSE_USER" \
            XDG_RUNTIME_DIR=/run/user/$PULSE_UID \
            pactl info > /dev/null 2>&1; then
        echo "PulseAudio is up."
        break
    fi
    echo "Waiting for PulseAudio... ($i/$MAX_RETRIES)"
    sleep $RETRY_INTERVAL
done

# Connect headset
for i in $(seq 1 $MAX_RETRIES); do
    echo "Attempt $i: connecting to $HEADSET_MAC..."
    if bluetoothctl connect "$HEADSET_MAC" 2>&1 | grep -q "Connection successful"; then
        echo "Headset connected."
        break
    fi
    sleep $RETRY_INTERVAL
done

# Wait for BT sink to appear in PulseAudio
for i in $(seq 1 $MAX_RETRIES); do
    if sudo -u "$PULSE_USER" \
            XDG_RUNTIME_DIR=/run/user/$PULSE_UID \
            pactl list sinks short 2>/dev/null | grep -q "bluez"; then
        echo "BT sink ready."
        break
    fi
    echo "Waiting for BT sink... ($i/$MAX_RETRIES)"
    sleep $RETRY_INTERVAL
done

# Load loopback
sudo -u "$PULSE_USER" \
    XDG_RUNTIME_DIR=/run/user/$PULSE_UID \
    pactl load-module module-alsa-source \
        device=hw:CARD=UAC2Gadget,DEV=0 \
        rate=48000 channels=2 tsched=0

sudo -u "$PULSE_USER" \
    XDG_RUNTIME_DIR=/run/user/$PULSE_UID \
    pactl load-module module-loopback \
        source=alsa_input.platform-3f980000.usb.stereo-fallback \
        sink=bluez_sink.07_01_69_96_E4_3B.a2dp_sink \
        latency_msec=100

echo "Audio relay active."