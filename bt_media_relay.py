#!/usr/bin/env python3
"""
Registers a virtual AVRCP "media player" with BlueZ. When headset buttons
(play/pause/next/previous) are pressed, BlueZ calls our Play/Pause/Next/
Previous methods — we translate those into USB HID consumer-control
keypresses sent to the laptop.
"""

import dbus
import dbus.service
import dbus.mainloop.glib
from gi.repository import GLib
import logging
import time

logging.basicConfig(level=logging.INFO, format="%(asctime)s INFO %(message)s")
log = logging.getLogger("bt-media-relay")

HIDG_DEVICE = "/dev/hidg0"

# Bit positions — must match the report descriptor order in setup_audio_gadget.sh
KEY_NEXT       = 0x01
KEY_PREVIOUS   = 0x02
KEY_STOP       = 0x04
KEY_PLAY_PAUSE = 0x08
KEY_MUTE       = 0x10
KEY_VOL_UP     = 0x20
KEY_VOL_DOWN   = 0x40


def send_key(bitmask):
    try:
        with open(HIDG_DEVICE, "wb") as f:
            f.write(bytes([bitmask]))
        time.sleep(0.05)
        with open(HIDG_DEVICE, "wb") as f:
            f.write(bytes([0x00]))
    except OSError as e:
        log.error(f"Failed to write to {HIDG_DEVICE}: {e}")


class MediaPlayer(dbus.service.Object):
    """Minimal AVRCP target player — just enough to receive button events."""

    PLAYER_PATH = "/relay/player0"

    def __init__(self, bus):
        dbus.service.Object.__init__(self, bus, self.PLAYER_PATH)
        self._props = {
            "PlaybackStatus": "Paused",
            "Rate": dbus.Double(1.0),
            "Metadata": dbus.Dictionary({}, signature="sv"),
            "Position": dbus.Int64(0),
            "MinimumRate": dbus.Double(1.0),
            "MaximumRate": dbus.Double(1.0),
            "CanGoNext": True,
            "CanGoPrevious": True,
            "CanPlay": True,
            "CanPause": True,
            "CanSeek": False,
            "CanControl": True,
        }

    def _set_status(self, status):
        self._props["PlaybackStatus"] = status
        self.PropertiesChanged("org.bluez.MediaPlayer1",
                                {"PlaybackStatus": status}, [])

    # ── org.bluez.MediaPlayer1 transport controls ──────────────────────────
    @dbus.service.method("org.bluez.MediaPlayer1")
    def Play(self):
        log.info("Play() <- headset")
        self._set_status("Playing")
        send_key(KEY_PLAY_PAUSE)

    @dbus.service.method("org.bluez.MediaPlayer1")
    def Pause(self):
        log.info("Pause() <- headset")
        self._set_status("Paused")
        send_key(KEY_PLAY_PAUSE)

    @dbus.service.method("org.bluez.MediaPlayer1")
    def Next(self):
        log.info("Next() <- headset")
        send_key(KEY_NEXT)

    @dbus.service.method("org.bluez.MediaPlayer1")
    def Previous(self):
        log.info("Previous() <- headset")
        send_key(KEY_PREVIOUS)

    @dbus.service.method("org.bluez.MediaPlayer1")
    def Stop(self):
        log.info("Stop() <- headset")
        self._set_status("Stopped")
        send_key(KEY_STOP)

    @dbus.service.method("org.bluez.MediaPlayer1")
    def Rewind(self):
        log.info("Rewind() <- headset (no HID mapping)")

    @dbus.service.method("org.bluez.MediaPlayer1")
    def FastForward(self):
        log.info("FastForward() <- headset (no HID mapping)")

    # ── org.freedesktop.DBus.Properties ────────────────────────────────────
    @dbus.service.method("org.freedesktop.DBus.Properties",
                          in_signature="ss", out_signature="v")
    def Get(self, interface, prop):
        return self._props[prop]

    @dbus.service.method("org.freedesktop.DBus.Properties",
                          in_signature="s", out_signature="a{sv}")
    def GetAll(self, interface):
        return dbus.Dictionary(self._props, signature="sv")

    @dbus.service.method("org.freedesktop.DBus.Properties", in_signature="ssv")
    def Set(self, interface, prop, value):
        self._props[prop] = value

    @dbus.service.signal("org.freedesktop.DBus.Properties", signature="sa{sv}as")
    def PropertiesChanged(self, interface, changed, invalidated):
        pass


def register_player(bus):
    player = MediaPlayer(bus)
    media = dbus.Interface(
        bus.get_object("org.bluez", "/org/bluez/hci0"),
        "org.bluez.Media1"
    )
    media.RegisterPlayer(player.PLAYER_PATH,
                          dbus.Dictionary(player._props, signature="sv"))
    log.info("Registered virtual AVRCP player with BlueZ.")
    return player


def main():
    dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
    bus = dbus.SystemBus()
    register_player(bus)
    log.info("Listening for AVRCP transport commands from headset...")
    GLib.MainLoop().run()


if __name__ == "__main__":
    main()