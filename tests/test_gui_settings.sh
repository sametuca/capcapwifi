#!/usr/bin/env bash
# AttackSettings: hedef/saldırı/portal kararlarının motora çevrilmesi.

SCRIPT_DIR=$(dirname "$(readlink -f "$0")")
exec python3 "$SCRIPT_DIR/test_gui_settings.py"
