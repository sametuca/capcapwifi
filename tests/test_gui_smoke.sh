#!/usr/bin/env bash

# Açar-ve-kapat GUI duman testi; python3'ün customtkinter bulabildiği bir
# ortamda çalışır. Modül yoksa veya görüntü sunucusu yoksa atlar.

source "$(dirname "$(readlink -f "$0")")/lib/testlib.sh"

tests_init "$(basename "$0")"

GUI_DIR="$REPO_DIR/gui"
PYTHON=${CAPCAP_TEST_PYTHON:-python3}

if ! "$PYTHON" -c "import customtkinter" &>/dev/null; then
  echo "  [SKIP] customtkinter yok; GUI duman testi atlandı"
  finish_tests
  exit $?
fi

cd "$GUI_DIR" || exit 1
"$PYTHON" "$REPO_DIR/tests/test_gui_smoke.py"
status=$?

if [ "$status" -ne 0 ]; then
  fail "GUI smoke test failed"
else
  pass "GUI smoke test passed"
fi

finish_tests

# CAPWIFI END
