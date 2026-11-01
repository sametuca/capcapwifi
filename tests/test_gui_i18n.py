#!/usr/bin/env python3
"""Static checks for the GUI language layer (no display needed).

Verifies that English and Turkish define exactly the same keys, that every
placeholder matches between the two, that no widget asks for a key that does
not exist, and that switching language changes the visible strings.
"""
import json
import os
import re
import string
import sys
import tempfile
from pathlib import Path

GUI_DIR = Path(__file__).resolve().parent.parent / "gui"
sys.path.insert(0, str(GUI_DIR))

import i18n  # noqa: E402

failures = 0


def check(label: str, ok: bool, detail: str = "") -> None:
    global failures
    if ok:
        print(f"  [OK] {label}")
    else:
        failures += 1
        print(f"  [FAIL] {label}" + (f"  ->  {detail}" if detail else ""))


def placeholders(text: str) -> set:
    return {field for _literal, field, _spec, _conv
            in string.Formatter().parse(text) if field}


en, tr = i18n.EN, i18n.TR
check("same number of English and Turkish keys", len(en) == len(tr),
      f"en={len(en)} tr={len(tr)}")

missing = sorted(set(en) - set(tr))
extra = sorted(set(tr) - set(en))
check("no key is missing from Turkish", not missing, ", ".join(missing))
check("Turkish has no extra keys", not extra, ", ".join(extra))

empty = sorted(k for k in en if not en[k].strip())
empty += sorted(k for k in tr if not tr[k].strip())
check("no empty strings", not empty, ", ".join(empty))

mismatched = sorted(
    key for key in en
    if key in tr and placeholders(en[key]) != placeholders(tr[key])
)
check("placeholders match between languages", not mismatched,
      ", ".join(mismatched))

# Every t("literal") call in the GUI must resolve. Keys built with f-strings
# (state.*, band.*, purpose.*, attack.*, step.*) are covered by the parity and
# by the dynamic-prefix list below.
literal_keys = set()
for path in GUI_DIR.glob("*.py"):
    for match in re.finditer(r'\bt\(\s*["\']([^"\']+)["\']', path.read_text()):
        literal_keys.add(match.group(1))

unknown = sorted(literal_keys - set(en))
check("all literal t() keys exist", not unknown, ", ".join(unknown))

dynamic_keys = {
    f"state.{name}" for name in (
        "IDLE", "INSTALLING", "STARTING", "SCANNING", "RUNNING",
        "HANDSHAKE_CAPTURED", "CREDENTIALS_FOUND", "STOPPED", "ERROR",
    )
}
dynamic_keys |= {f"band.{code}" for code in ("bg", "a", "abg")}
dynamic_keys |= {
    f"purpose.{tool}" for tool in (
        "aircrack-ng", "airmon-ng", "hostapd", "lighttpd", "php-cgi",
        "kea-dhcp4", "dnsspoof", "mdk4", "iw", "xterm", "tmux", "cowpatty",
        "pyrit",
    )
}
for attack in ("captive_portal", "handshake_snooper"):
    dynamic_keys |= {
        f"attack.{attack}.{suffix}" for suffix in ("label", "summary", "need", "next")
    }
dynamic_keys |= {f"step.{key}" for key in
                 ("adapter", "scan", "target", "attack", "result")}

missing_dynamic = sorted(key for key in dynamic_keys if key not in en)
missing_dynamic += sorted(
    key for key in dynamic_keys if key not in tr
)
check("dynamic keys exist in both languages", not missing_dynamic,
      ", ".join(missing_dynamic))

# Switching language must actually change the rendered strings.
i18n.set_language("en")
english_label = i18n.t("app.btn.scan")
i18n.set_language("tr")
turkish_label = i18n.t("app.btn.scan")
check("switching language changes strings",
      english_label != turkish_label,
      f"{english_label!r} == {turkish_label!r}")

from models import AttackType  # noqa: E402  (imports i18n too)

i18n.set_language("tr")
tr_label = AttackType.CAPTIVE_PORTAL.label
i18n.set_language("en")
en_label = AttackType.CAPTIVE_PORTAL.label
check("model labels follow the language", tr_label != en_label)
check("English label is the English table value",
      en_label == i18n.EN["attack.captive_portal.label"])

check("unknown keys fall back to the key itself",
      i18n.t("does.not.exist") == "does.not.exist")
check("missing format arguments do not raise",
      i18n.t("networks.count") == i18n.EN["networks.count"])

# Preference persistence, isolated from the real HOME.
with tempfile.TemporaryDirectory() as tmp:
    original_dir, original_file = i18n.CONFIG_DIR, i18n.CONFIG_FILE
    original_legacy = i18n.LEGACY_CONFIG_DIR, i18n.LEGACY_CONFIG_FILE
    original_env = os.environ.pop("CAPCAP_GUI_LANG", None)
    try:
        i18n.CONFIG_DIR = Path(tmp) / "capwifi"
        i18n.CONFIG_FILE = i18n.CONFIG_DIR / "gui.json"
        i18n.LEGACY_CONFIG_DIR = Path(tmp) / "capcapwifi"
        i18n.LEGACY_CONFIG_FILE = i18n.LEGACY_CONFIG_DIR / "gui.json"

        # Model an install upgraded in place: the old build left its settings
        # in ~/.config/capcapwifi and the new build has not written anything.
        i18n.LEGACY_CONFIG_DIR.mkdir(parents=True)
        i18n.LEGACY_CONFIG_FILE.write_text(
            json.dumps({"language": "tr"}), encoding="utf-8")
        check("settings from the pre-rename build are still read",
              i18n.detect_language() == "tr")

        i18n.save_language("tr")
        check("writing after an upgrade uses the new location",
              i18n.CONFIG_FILE.is_file())
        check("the legacy file is left untouched",
              json.loads(i18n.LEGACY_CONFIG_FILE.read_text())["language"] == "tr")
        check("the new file wins over the legacy one",
              i18n.detect_language() == "tr")

        i18n.CONFIG_FILE.write_text(json.dumps({"language": "en"}), encoding="utf-8")
        check("a value in the new file overrides the legacy one",
              i18n.detect_language() == "en")
        i18n.CONFIG_FILE.unlink()

        i18n.save_language("tr")
        check("preference file is rewritten", i18n.CONFIG_FILE.is_file())
        check("saved preference is detected", i18n.detect_language() == "tr")

        os.environ["CAPCAP_GUI_LANG"] = "en"
        check("environment variable overrides the saved preference",
              i18n.detect_language() == "en")
        os.environ["CAPCAP_GUI_LANG"] = "xx"
        check("invalid environment override is ignored",
              i18n.detect_language() == "tr")
    finally:
        os.environ.pop("CAPCAP_GUI_LANG", None)
        if original_env is not None:
            os.environ["CAPCAP_GUI_LANG"] = original_env
        i18n.CONFIG_DIR, i18n.CONFIG_FILE = original_dir, original_file
        i18n.LEGACY_CONFIG_DIR, i18n.LEGACY_CONFIG_FILE = original_legacy
        i18n.set_language("en")

check("invalid language codes fall back to English",
      i18n.set_language("klingon") == "en")

if failures:
    print(f"\n{failures} check(s) failed.")
    sys.exit(1)
print("\nGUI i18n OK")
