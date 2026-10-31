#!/usr/bin/env bash
# GUI palette + button contrast: WCAG AA checks (no display, no customtkinter).

SCRIPT_DIR=$(dirname "$(readlink -f "$0")")
exec python3 "$SCRIPT_DIR/test_gui_theme.py"
