#!/usr/bin/env python3
"""Shared generator for the self-capturing captive portal families.

CapWifi copies a portal directory verbatim into the lighttpd document root, so
every language has to exist on disk as its own ``<Family>_<code>.portal``
directory. Keeping several copies of the same markup in sync by hand does not
survive a design change, so the portal families are generated from
``scripts/<family>_portal/`` and the generated directories are committed.

The family wrappers (``build_instagram_portals.py`` and
``build_wifi_portals.py``) only supply their source directory, output prefix and
template list; everything else lives here.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Mapping, Sequence

REPO_DIR = Path(__file__).resolve().parent.parent

PLACEHOLDER = re.compile(r"\{\{([a-z_]+)\}\}")


def load_languages(source_dir: Path) -> list[dict]:
    raw = (source_dir / "languages.json").read_text(encoding="utf-8")
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


def build_portal(
    language: dict,
    templates: Mapping[str, str],
    static_files: Mapping[str, Path],
) -> dict[str, str]:
    strings = language["strings"]
    values = {"lang": escape(language["html_lang"])}
    for key, value in strings.items():
        values[key] = escape(value)

    portal: dict[str, str] = {}
    for name, template in templates.items():
        portal[name] = render(template, values, name)
    for name, source in static_files.items():
        portal[name] = source.read_text(encoding="utf-8")
    return portal


def write_text(path: Path, content: str) -> None:
    # Path.write_text() only grew a newline argument in Python 3.10; the
    # portals must stay LF regardless of the host.
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(content)


def run_family(
    *,
    label: str,
    source_dir: Path,
    sites_dir: Path,
    prefix: str,
    templates: Sequence[str],
    static_files: Mapping[str, Path],
    check: bool,
) -> int:
    languages = load_languages(source_dir)
    rendered_templates = {
        name: (source_dir / f"{name}.tmpl").read_text(encoding="utf-8")
        for name in templates
    }

    stale: list[str] = []
    written = 0

    for language in languages:
        code = str(language["code"])
        target = sites_dir / f"{prefix}_{code}.portal"
        portal = build_portal(language, rendered_templates, static_files)

        if check:
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

    if check:
        if stale:
            print(f"{label} portals are out of date:", file=sys.stderr)
            for line in stale:
                print(f"  {line}", file=sys.stderr)
            print(f"Run scripts/build_{prefix.lower()}_portals.py to regenerate them.",
                  file=sys.stderr)
            return 1
        print(f"{label} portals are up to date ({len(languages)} languages).")
        return 0

    print(f"Built {len(languages)} {label} portal(s), {written} file(s) updated.")
    return 0
