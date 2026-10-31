#!/usr/bin/env bash
# GUI language layer: key parity, placeholders, persistence (no display).

SCRIPT_DIR=$(dirname "$(readlink -f "$0")")
exec python3 "$SCRIPT_DIR/test_gui_i18n.py"
