#!/usr/bin/env python3
"""WPA3/PMF algılama testi.

PMF kullanan ağlarda deauth çerçeveleri istemci tarafından atılır; arayüzün
bunu önceden söylemesi, kullanıcının "neden telefon düşmüyor" diye saatlerce
denemesini engeller.
"""
import os
import sys

GUI_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "gui"))
sys.path.insert(0, GUI_DIR)

import i18n  # noqa: E402
from models import TargetCandidate  # noqa: E402


def candidate(enc):
    return TargetCandidate(
        bssid="AA:BB:CC:DD:EE:FF", channel="6", power=-40, clients=1,
        quality="70", enc=enc, vendor="Test", essid="TestNet",
    )


checks = [
    ("WPA2", False),
    ("WPA2 WPA3", True),
    ("WPA3", True),
    ("SAE", True),
    ("802.11W", True),
    ("OPN", False),
    ("", False),
]

failures = 0
for enc, expected in checks:
    actual = candidate(enc).uses_pmf
    if actual != expected:
        print(f"  [FAIL] enc={enc!r}: beklenen {expected}, gelen {actual}")
        failures += 1
    else:
        print(f"  [OK] enc={enc!r} -> uses_pmf={actual}")

for lang, key in (("en", "log.pmf_target"), ("tr", "log.pmf_target"),
                  ("en", "hint.pmf_target"), ("tr", "hint.pmf_target")):
    i18n.set_language(lang)
    text = i18n.t(key, ssid="TestNet")
    if not text or text == key:
        print(f"  [FAIL] {lang}: {key} eksik")
        failures += 1
    else:
        print(f"  [OK] {lang}: {key}")

if failures:
    print(f"\nPMF test FAILED ({failures})")
    sys.exit(1)

print("\nPMF test OK")
