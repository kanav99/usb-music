#!/bin/bash
# teardown_audio_gadget.sh

GADGET_DIR=/sys/kernel/config/usb_gadget/audio_relay

if [ ! -d "$GADGET_DIR" ]; then
    echo "No gadget found, nothing to do."
    exit 0
fi

echo "=== Current gadget state ==="
cat "$GADGET_DIR/UDC" 2>/dev/null && echo "(above is UDC)" || echo "(UDC empty)"
ls "$GADGET_DIR/configs/" 2>/dev/null
ls "$GADGET_DIR/functions/" 2>/dev/null

echo "=== Unbinding from UDC ==="
echo "" > "$GADGET_DIR/UDC"
sleep 0.5

echo "=== Removing symlinks ==="
for link in "$GADGET_DIR"/configs/c.1/*; do
    [ -L "$link" ] && echo "  rm $link" && rm "$link"
done

echo "=== Removing config strings ==="
rmdir "$GADGET_DIR/configs/c.1/strings/0x409" && echo "  done" || echo "  FAILED: $?"

echo "=== Removing config ==="
rmdir "$GADGET_DIR/configs/c.1" && echo "  done" || echo "  FAILED: $?"

echo "=== Removing functions ==="
rmdir "$GADGET_DIR/functions/uac2.0" && echo "  done" || echo "  FAILED: $?"

echo "=== Removing gadget strings ==="
rmdir "$GADGET_DIR/strings/0x409" && echo "  done" || echo "  FAILED: $?"

echo "=== Removing gadget root ==="
rmdir "$GADGET_DIR" && echo "  done" || echo "  FAILED: $?"

echo ""
echo "=== Remaining (should be empty) ==="
ls "$GADGET_DIR" 2>/dev/null || echo "Directory gone — teardown successful."
