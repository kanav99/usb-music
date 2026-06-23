#!/bin/bash
# setup_audio_gadget.sh

GADGET_DIR=/sys/kernel/config/usb_gadget/audio_relay

modprobe libcomposite
modprobe usb_f_hid 2>/dev/null || true

# ── Teardown (errors expected and ignored here) ───────────────────────────────
if [ -d "$GADGET_DIR" ]; then
    echo "Tearing down existing gadget..."
    echo "" > "$GADGET_DIR/UDC" 2>/dev/null || true
    for link in "$GADGET_DIR"/configs/c.1/*; do
        [ -L "$link" ] && rm "$link"
    done
    rmdir "$GADGET_DIR/configs/c.1/strings/0x409" 2>/dev/null || true
    rmdir "$GADGET_DIR/configs/c.1"                2>/dev/null || true
    rmdir "$GADGET_DIR/functions/uac2.0"           2>/dev/null || true
    rmdir "$GADGET_DIR/functions/hid.usb0"         2>/dev/null || true
    rmdir "$GADGET_DIR/strings/0x409"              2>/dev/null || true
    rmdir "$GADGET_DIR"                            2>/dev/null || true
    sleep 0.5
fi

set -e

mkdir -p "$GADGET_DIR"
cd "$GADGET_DIR"

echo 0x1d6b > idVendor
echo 0x0104 > idProduct
echo 0x0100 > bcdDevice
echo 0x0200 > bcdUSB

# Composite device signaling (Interface Association Descriptor)
echo 0xEF > bDeviceClass
echo 0x02 > bDeviceSubClass
echo 0x01 > bDeviceProtocol

mkdir -p strings/0x409
echo "deadbeef12345678" > strings/0x409/serialnumber
echo "BT Audio Relay"   > strings/0x409/manufacturer
echo "BT Headset Relay" > strings/0x409/product

# ── Audio function (laptop → Pi → headset) ─────────────────────────────────────
mkdir -p functions/uac2.0
echo 3     > functions/uac2.0/c_chmask   # capture: stereo (laptop → Pi)
echo 48000 > functions/uac2.0/c_srate
echo 2     > functions/uac2.0/c_ssize
echo 1     > functions/uac2.0/p_chmask   # minimal playback endpoint
echo 48000 > functions/uac2.0/p_srate
echo 2     > functions/uac2.0/p_ssize

# ── HID function (headset buttons → Pi → laptop) ───────────────────────────────
mkdir -p functions/hid.usb0
echo 0 > functions/hid.usb0/protocol
echo 0 > functions/hid.usb0/subclass
echo 1 > functions/hid.usb0/report_length   # 1-byte bitmap report

# Consumer Control report descriptor — one bit per media key
echo -ne '\x05\x0C\x09\x01\xA1\x01\x15\x00\x25\x01\x75\x01\x95\x08\x09\xB5\x09\xB6\x09\xB7\x09\xCD\x09\xE2\x09\xE9\x09\xEA\x09\xB0\x81\x02\xC0' \
    > functions/hid.usb0/report_desc

mkdir -p configs/c.1/strings/0x409
echo "Audio Relay Config" > configs/c.1/strings/0x409/configuration
echo 250                  > configs/c.1/MaxPower

ln -s functions/uac2.0   configs/c.1/
ln -s functions/hid.usb0 configs/c.1/

UDC_NAME=$(ls /sys/class/udc | head -n1)
if [ -z "$UDC_NAME" ]; then
    echo "ERROR: No UDC found." >&2
    exit 1
fi

echo "$UDC_NAME" > UDC
echo "Gadget active on $UDC_NAME"
echo "Verify: arecord -l (audio), ls /dev/hidg* (HID)"