#!/usr/bin/env bash

source "$(dirname "$(readlink -f "$0")")/lib/testlib.sh"

tests_init "$(basename "$0")"

echo "=== Instagram Portal Test Suite ==="
echo

SITES_DIR="$REPO_DIR/attacks/Captive Portal/sites"
PORTAL_SRC="$SITES_DIR/Instagram_tur.portal"
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
  if python3 "$REPO_DIR/scripts/build_instagram_portals.py" --check >/dev/null 2>&1; then
    pass "Committed portals match the templates"
  else
    fail "Committed portals match the templates (run scripts/build_instagram_portals.py)"
  fi
else
  echo "  SKIP: python3 not available, cannot verify generated portals"
fi

for language in tur en de es fr it pt-br; do
  if [ -f "$SITES_DIR/Instagram_$language.portal/index.html" ]; then
    pass "Portal Instagram_$language exists"
  else
    fail "Portal Instagram_$language exists"
  fi
done

# The workspace holds the credential log; the portal lives one level down, as
# it does under /tmp/fluxspace/captive_portal at runtime.
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

post_raw() {
  curl -s -o /dev/null -w '%{http_code} %{redirect_url}' "$@"
}

# ── Request handling ────────────────────────────────────────────────────────
reset_state

result=$(post_raw "$BASE/submit.php")
assert_equal "302 $BASE/index.html" "$result" "A GET is redirected to the login page"

result=$(post "")
assert_equal "302 $BASE/index.html" "$result" "An empty submission returns to the login page"
assert_equal 0 "$(count_lines "$LOG")" "An empty submission is not logged"

result=$(post 'username=ayse.demir&password=Summer2026!')
assert_equal "302 $BASE/error.html?u=ayse.demir" "$result" \
  "The first attempt shows the password error"
assert_equal 1 "$(count_lines "$LOG")" "The first attempt is logged once"

result=$(post 'username=ayse.demir&password=Summer2026!')
assert_equal "302 $BASE/error.html?u=ayse.demir" "$result" \
  "A repeated submission keeps the retry page"
assert_equal 1 "$(count_lines "$LOG")" "A repeated submission is not logged twice"

result=$(post 'username=ayse.demir&password=Summer2026!x')
assert_equal "302 $BASE/final.html" "$result" "The second distinct attempt shows the success page"

assert_equal 5 "$(awk -F'\t' 'NR==1 { print NF }' "$LOG")" \
  "A log line has five tab-separated fields"

# Tab, newline and other control characters must not split the record.
reset_state
post $'username=a\tb\nc\x00d&password=p' >/dev/null
assert_equal 5 "$(awk -F'\t' 'END { print NF }' "$LOG")" \
  "Control characters cannot break the log format"
assert_equal 1 "$(count_lines "$LOG")" "A submission with control characters stays one line"

# A field sent as an array must not reach the log as "Array".
reset_state
result=$(post 'username[]=array&password=x')
assert_equal "302 $BASE/error.html?u=" "$result" "An array in place of a field is rejected"
assert_equal "	x" "$(cut -f3,4 "$LOG" | tail -1)" "An array field is stored as empty"

head -c 9000 /dev/zero | tr '\0' 'a' >"$TEST_RUNTIME_DIR/large.txt"
result=$(post_raw --data-binary "@$TEST_RUNTIME_DIR/large.txt" "$BASE/submit.php")
assert_equal 413 "${result%% *}" "An oversized body is refused"

# ── Log rotation ────────────────────────────────────────────────────────────
reset_state
python3 -c "open('$LOG', 'w').write('old line\n' * 60000)"
size_before=$(wc -c <"$LOG" | tr -d ' ')
post 'username=rotator&password=1' >/dev/null
if [ -f "$LOG.1" ] && [ "$(wc -c <"$LOG" | tr -d ' ')" -lt "$size_before" ]; then
  pass "The log rotates once it exceeds the limit"
else
  fail "The log rotates once it exceeds the limit"
fi

python3 -c "open('$LOG', 'w').write('old line\n' * 60000)"
post 'username=rotator&password=2' >/dev/null
if [ -f "$LOG.2" ]; then
  pass "Rotation shifts older logs along"
else
  fail "Rotation shifts older logs along"
fi

# ── State file ──────────────────────────────────────────────────────────────
reset_state
echo 'not json' >"$STATE"
result=$(post 'username=corrupt&password=1')
assert_equal "302 $BASE/error.html?u=corrupt" "$result" \
  "A corrupt state file is treated as empty"

python3 - "$STATE" <<'PY'
import json, sys, time
stale = {"10.0.0.1": {"c": 1, "t": int(time.time()) - 7200, "u": "x", "d": 0},
         "10.0.0.2": {"c": 1, "t": int(time.time()), "u": "y", "d": 0}}
open(sys.argv[1], "w").write(json.dumps(stale))
PY
post 'username=prune&password=1' >/dev/null
if python3 -c "import json,sys; sys.exit(0 if '10.0.0.1' not in json.load(open('$STATE')) else 1)"; then
  pass "Stale state entries are pruned"
else
  fail "Stale state entries are pruned"
fi

finish_tests
