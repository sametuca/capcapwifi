#!/usr/bin/env bash
# GUI status event parser: spaces inside SSIDs, paths and passwords.

SCRIPT_DIR=$(dirname "$(readlink -f "$0")")
exec python3 "$SCRIPT_DIR/test_gui_status.py"
