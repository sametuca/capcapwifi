#!/usr/bin/env python3
"""Build the Instagram captive portals from a single set of templates.

Fluxion copies a portal directory verbatim into the lighttpd document root, so
every language has to exist on disk as its own ``Instagram_<code>.portal``
directory. Keeping seven copies of the same markup in sync by hand does not
survive a design change, so the portals are generated here from
``scripts/instagram_portal/`` and the generated directories are committed.

Usage:
    scripts/build_instagram_portals.py            # write the portals
    scripts/build_instagram_portals.py --check    # exit 1 if they are stale

Adding a language means one entry in ``languages.json``; adding or changing the
markup means editing the templates and re-running this script.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

REPO_DIR = Path(__file__).resolve().parent.parent
SOURCE_DIR = REPO_DIR / "scripts" / "instagram_portal"
SITES_DIR = REPO_DIR / "attacks" / "Captive Portal" / "sites"

# Rendered per language.
TEMPLATES = ("index.html", "error.html", "final.html")
# Copied unchanged into every portal directory.
STATIC_FILES = ("submit.php",)

PLACEHOLDER = re.compile(r"\{\{([a-z_]+)\}\}")


def load_languages() -> list[dict]:
    raw = (SOURCE_DIR / "languages.json").read_text(encoding="utf-8")
    data = json.loads(raw)
    languages = data.get("languages")
    if not isinstance(languages, list) or not languages:
        raise SystemExit("languages.json: 'languages' must be a non-empty list")

    seen: set[str] = set()
    for entry in languages:
        for key in ("code", "html_lang", "strings"):
            if key not in entry:
                raise SystemExit(f"languages.json: entry {entry!r} is missing '{key}'")
        if entry["code"] in seen:
            raise SystemExit(f"languages.json: duplicate code '{entry['code']}'")
        seen.add(entry["code"])
    return languages


def escape(value: object) -> str:
    """Escape the characters that matter in text nodes and quoted attributes.

    html.escape() also rewrites apostrophes to &#x27;, which is noise in a text
    node and makes diffs of translated copy unreadable.
    """
    return (
        str(value)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def render(template: str, values: dict[str, str], name: str) -> str:
    missing: list[str] = []

    def substitute(match: re.Match[str]) -> str:
        key = match.group(1)
        if key not in values:
            missing.append(key)
            return match.group(0)
        return values[key]

    rendered = PLACEHOLDER.sub(substitute, template)
    if missing:
        raise SystemExit(f"{name}: unknown placeholder(s): {', '.join(sorted(set(missing)))}")
    if "{{" in rendered:
        raise SystemExit(f"{name}: unresolved placeholder left in the output")
    return rendered


def build_portal(language: dict, templates: dict[str, str]) -> dict[str, str]:
    strings = language["strings"]
    values = {"lang": escape(language["html_lang"])}
    for key, value in strings.items():
        values[key] = escape(value)

    portal: dict[str, str] = {}
    for name, template in templates.items():
        portal[name] = render(template, values, name)
    for name in STATIC_FILES:
        portal[name] = (SOURCE_DIR / name).read_text(encoding="utf-8")
    return portal


def portal_dir(code: str) -> Path:
    return SITES_DIR / f"Instagram_{code}.portal"


def write_text(path: Path, content: str) -> None:
    # Path.write_text() only grew a newline argument in Python 3.10; the
    # portals must stay LF regardless of the host.
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(content)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="do not write anything; fail if the committed portals differ",
    )
    args = parser.parse_args()

    languages = load_languages()
    templates = {
        name: (SOURCE_DIR / f"{name}.tmpl").read_text(encoding="utf-8")
        for name in TEMPLATES
    }

    stale: list[str] = []
    written = 0

    for language in languages:
        code = str(language["code"])
        target = portal_dir(code)
        portal = build_portal(language, templates)

        if args.check:
            for name, content in portal.items():
                path = target / name
                if not path.is_file():
                    stale.append(f"{path.relative_to(REPO_DIR)}: missing")
                elif path.read_text(encoding="utf-8") != content:
                    stale.append(f"{path.relative_to(REPO_DIR)}: out of date")
            continue

        target.mkdir(parents=True, exist_ok=True)
        for name, content in portal.items():
            path = target / name
            if path.is_file() and path.read_text(encoding="utf-8") == content:
                continue
            write_text(path, content)
            written += 1
        print(f"  {target.relative_to(REPO_DIR)}")

    if args.check:
        if stale:
            print("Instagram portals are out of date:", file=sys.stderr)
            for line in stale:
                print(f"  {line}", file=sys.stderr)
            print("Run scripts/build_instagram_portals.py to regenerate them.", file=sys.stderr)
            return 1
        print(f"Instagram portals are up to date ({len(languages)} languages).")
        return 0

    print(f"Built {len(languages)} portal(s), {written} file(s) updated.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
