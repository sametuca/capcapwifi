#!/usr/bin/env python3
"""capcap.status satır ayrıştırıcısı – görüntü gerektirmez.

Değerlerdeki boşluklar (SSID, "Handshake Snooper" içeren yollar, saldırı
adları) kaybolmamalı; GUI bunları dosya açmak ve göstermek için kullanıyor.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "gui"))

from controller import (  # noqa: E402
    CapCapWifiController,
    parse_status_line,
)

failures = []


def check(label, ok, detail=""):
    print(("  [OK] " if ok else "  [FAIL] ") + label +
          (f"  -> {detail}" if detail and not ok else ""))
    if not ok:
        failures.append(label)


TS = "[2026-10-31T12:00:00] "

ev = parse_status_line(TS + "HANDSHAKE_CAPTURED path=/root/capcap/attacks/"
                       "Handshake Snooper/handshakes/Ev Wifi-AA:BB:CC:DD:EE:01.cap")
check("event type parsed", ev and ev.get("type") == "HANDSHAKE_CAPTURED", str(ev))
check("path keeps its spaces",
      ev and ev.get("path") == "/root/capcap/attacks/Handshake Snooper/"
      "handshakes/Ev Wifi-AA:BB:CC:DD:EE:01.cap", str(ev))

ev = parse_status_line(TS + "TARGET_SELECTED ssid=My Home Wifi "
                       "bssid=AA:BB:CC:DD:EE:01 channel=6")
check("ssid keeps its spaces", ev and ev.get("ssid") == "My Home Wifi", str(ev))
check("following keys still parse",
      ev and ev.get("bssid") == "AA:BB:CC:DD:EE:01" and ev.get("channel") == "6",
      str(ev))

ev = parse_status_line(TS + "ATTACK_STARTED attack=Captive Portal")
check("attack name keeps its space",
      ev and ev.get("attack") == "Captive Portal", str(ev))

ev = parse_status_line(TS + "DEP_MISSING tools=aircrack-ng bc mdk4")
check("tool list keeps its spaces",
      ev and ev.get("tools") == "aircrack-ng bc mdk4", str(ev))

ev = parse_status_line(TS + "RESULT password=my secret pass ssid=Ev Wifi")
check("password keeps its spaces",
      ev and ev.get("password") == "my secret pass", str(ev))

ev = parse_status_line(TS + "RESULT none")
check("bare event parses", ev == {"type": "RESULT"}, str(ev))
check("unrelated text is ignored", parse_status_line("plain log line") is None)
check("empty line is ignored", parse_status_line("") is None)

# The same capture arrives through the flag file, the status event and the
# final RESULT line; the user must see it once.
ctrl = CapCapWifiController()
shown = []
ctrl.on_credential = shown.append
ctrl._handle_result({"type": "RESULT", "password": "sifre123",
                     "ssid": "Ev", "bssid": "AA:BB:CC:DD:EE:01"})
ctrl._handle_result({"type": "RESULT", "password": "sifre123",
                     "ssid": "Ev", "bssid": "AA:BB:CC:DD:EE:01"})
check("duplicate credential is shown once", len(shown) == 1, str(len(shown)))

handshakes = []
ctrl.on_handshake = handshakes.append
ctrl._handle_handshake_captured("/tmp/nope.cap")
ctrl._handle_handshake_captured("/tmp/nope.cap")
check("duplicate handshake is shown once", len(handshakes) == 1,
      str(len(handshakes)))

if failures:
    print(f"\nGUI status parser FAILED: {failures}")
    sys.exit(1)
print("\nGUI status parser OK")
