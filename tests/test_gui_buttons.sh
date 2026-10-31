#!/usr/bin/env bash

# Düğmeler gerçek fare tıklamasına tepki veriyor mu? Pencere açar.
# customtkinter veya görüntü sunucusu yoksa atlar.

source "$(dirname "$(readlink -f "$0")")/lib/testlib.sh"

tests_init "$(basename "$0")"

GUI_DIR="$REPO_DIR/gui"
PYTHON=${CAPCAP_TEST_PYTHON:-python3}

if ! "$PYTHON" -c "import customtkinter" &>/dev/null; then
  echo "  [SKIP] customtkinter yok; düğme tıklama testi atlandı"
  finish_tests
  exit $?
fi

cd "$GUI_DIR" || exit 1
"$PYTHON" "$REPO_DIR/tests/test_gui_buttons.py"
status=$?

if [ "$status" -ne 0 ]; then
  fail "Düğme tıklama testi başarısız"
else
  pass "Düğme tıklama testi geçti"
fi

finish_tests

# CAPWIFI END
