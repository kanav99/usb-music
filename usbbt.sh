#!/bin/bash
# setup_audio_gadget.sh

GADGET_DIR=/sys/kernel/config/usb_gadget/audio_relay

modprobe libcomposite

# ── Teardown (errors expected and ignored here) ───────────────────────────────
if [ -d "$GADGET_DIR" ]; then
    echo "Tearing down existing gadget..."
    echo "" > "$GADGET_DIR/UDC" 2>/dev/null || true   # may say "No such device" — fine
    for link in "$GADGET_DIR"/configs/c.1/*; do
        [ -L "$link" ] && rm "$link"
    done
    rmdir "$GADGET_DIR/configs/c.1/strings/0x409" 2>/dev/null || true
    rmdir "$GADGET_DIR/configs/c.1"                2>/dev/null || true
    rmdir "$GADGET_DIR/functions/uac2.0"           2>/dev/null || true
    rmdir "$GADGET_DIR/strings/0x409"              2>/dev/null || true
    rmdir "$GADGET_DIR"                            2>/dev/null || true
    sleep 0.5
fi

# ── From here, fail loudly on any error ───────────────────────────────────────
set -e

mkdir -p "$GADGET_DIR"
cd "$GADGET_DIR"

echo 0x1d6b > idVendor
echo 0x0104 > idProduct
echo 0x0100 > bcdDevice
echo 0x0200 > bcdUSB

mkdir -p strings/0x409
echo "deadbeef12345678" > strings/0x409/serialnumber
echo "BT Audio Relay"   > strings/0x409/manufacturer
echo "BT Headset Relay" > strings/0x409/product

mkdir -p functions/uac2.0
echo 3     > functions/uac2.0/c_chmask   # capture: stereo (laptop → Pi)
echo 48000 > functions/uac2.0/c_srate
echo 2     > functions/uac2.0/c_ssize    # bytes, not bits

echo 1     > functions/uac2.0/p_chmask   # playback: mono minimum (Pi → laptop)
echo 48000 > functions/uac2.0/p_srate
echo 2     > functions/uac2.0/p_ssize

mkdir -p configs/c.1/strings/0x409
echo "Audio Relay Config" > configs/c.1/strings/0x409/configuration
echo 250                  > configs/c.1/MaxPower

ln -s functions/uac2.0 configs/c.1/

UDC_NAME=$(ls /sys/class/udc | head -n1)
if [ -z "$UDC_NAME" ]; then
    echo "ERROR: No UDC found. Is dwc2 loaded and USB data cable connected?" >&2
    exit 1
fi

echo "$UDC_NAME" > UDC
echo "Gadget active on $UDC_NAME — verify with: arecord -l"