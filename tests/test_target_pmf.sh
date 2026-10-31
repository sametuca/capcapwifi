#!/usr/bin/env bash

source "$(dirname "$(readlink -f "$0")")/lib/testlib.sh"

tests_init "$(basename "$0")"

PYTHON=${CAPCAP_TEST_PYTHON:-python3}

"$PYTHON" "$REPO_DIR/tests/test_target_pmf.py"
status=$?

if [ "$status" -ne 0 ]; then
  fail "PMF detection test failed"
else
  pass "PMF detection test passed"
fi

finish_tests

# FLUXSCRIPT END
