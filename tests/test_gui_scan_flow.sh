#!/usr/bin/env bash

# Tara/başlat akışı: düğmeler gerçekten çalışıyor mu, hatalar arayüzü
# kilitliyor mu? Pencere açar; customtkinter veya görüntü yoksa atlar.

source "$(dirname "$(readlink -f "$0")")/lib/testlib.sh"

tests_init "$(basename "$0")"

GUI_DIR="$REPO_DIR/gui"
PYTHON=${CAPCAP_TEST_PYTHON:-python3}

if ! "$PYTHON" -c "import customtkinter" &>/dev/null; then
  echo "  [SKIP] customtkinter yok; tarama akışı testi atlandı"
  finish_tests
  exit $?
fi

cd "$GUI_DIR" || exit 1
"$PYTHON" "$REPO_DIR/tests/test_gui_scan_flow.py"
status=$?

if [ "$status" -ne 0 ]; then
  fail "Tarama akışı testi başarısız"
else
  pass "Tarama akışı testi geçti"
fi

finish_tests

# FLUXSCRIPT END
