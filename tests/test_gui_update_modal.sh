#!/usr/bin/env bash

# Güncelleme modalı testi; pencereyi gerçekten açar. customtkinter veya
# görüntü sunucusu yoksa atlar.

source "$(dirname "$(readlink -f "$0")")/lib/testlib.sh"

tests_init "$(basename "$0")"

GUI_DIR="$REPO_DIR/gui"
PYTHON=${CAPCAP_TEST_PYTHON:-python3}

if ! "$PYTHON" -c "import customtkinter" &>/dev/null; then
  echo "  [SKIP] customtkinter yok; güncelleme modalı testi atlandı"
  finish_tests
  exit $?
fi

cd "$GUI_DIR" || exit 1
"$PYTHON" "$REPO_DIR/tests/test_gui_update_modal.py"
status=$?

if [ "$status" -ne 0 ]; then
  fail "Güncelleme modalı testi başarısız"
else
  pass "Güncelleme modalı testi geçti"
fi

finish_tests

# CAPWIFI END
