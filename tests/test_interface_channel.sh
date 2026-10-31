#!/usr/bin/env bash

source "$(dirname "$(readlink -f "$0")")/lib/testlib.sh"

tests_init "$(basename "$0")"

echo "=== Interface Channel Helper Test Suite ==="
echo

INTERFACE_LIB="$REPO_DIR/lib/InterfaceUtils.sh"
HANDSHAKE_ATTACK="$REPO_DIR/attacks/Handshake Snooper/attack.sh"
PORTAL_ATTACK="$REPO_DIR/attacks/Captive Portal/attack.sh"

# Pull interface_set_channel straight out of the library so the test tracks the
# real implementation instead of a copy that drifts.
channel_fn_source=$(
  awk '
    /^function interface_set_channel\(\) \{/ { capture=1 }
    capture { print }
    capture && /^\}/ { exit }
  ' "$INTERFACE_LIB"
)

if [ -z "$channel_fn_source" ]; then
  fail "interface_set_channel not found in lib/InterfaceUtils.sh"
  finish_tests
  exit $?
fi

pass "interface_set_channel is defined in the interface library"
eval "$channel_fn_source"

# Fake iw/iwconfig so the helper can be exercised without touching a radio.
BIN_DIR="$TEST_RUNTIME_DIR/bin"
mkdir -p "$BIN_DIR"

write_tool() {
  local name=$1 status=$2
  cat > "$BIN_DIR/$name" <<EOF
#!/usr/bin/env bash
echo "\$@" >> "$TEST_RUNTIME_DIR/$name.calls"
exit $status
EOF
  chmod +x "$BIN_DIR/$name"
}

reset_tools() {
  rm -f "$TEST_RUNTIME_DIR/iw.calls" "$TEST_RUNTIME_DIR/iwconfig.calls"
}

export InterfaceUtilsOutputDevice=/dev/null
export PATH="$BIN_DIR:$PATH"

echo "Test 1: iw is used when it accepts the channel"
reset_tools
write_tool iw 0
write_tool iwconfig 1
interface_set_channel wlan1mon 6
assert_exit_code 0 $? "returns 0 when iw succeeds"
assert_contains "$(cat "$TEST_RUNTIME_DIR/iw.calls")" "set channel 6" \
  "iw receives the channel"
if [ -f "$TEST_RUNTIME_DIR/iwconfig.calls" ]; then
  fail "iwconfig must not run after iw succeeds"
else
  pass "iwconfig is not called after iw succeeds"
fi

echo "Test 2: iwconfig is the fallback"
reset_tools
write_tool iw 1
write_tool iwconfig 0
interface_set_channel wlan1 11
assert_exit_code 0 $? "returns 0 when only iwconfig succeeds"
assert_contains "$(cat "$TEST_RUNTIME_DIR/iwconfig.calls")" "channel 11" \
  "iwconfig receives the channel"

echo "Test 3: failure is reported"
reset_tools
write_tool iw 1
write_tool iwconfig 1
interface_set_channel wlan1 6
assert_exit_code 2 $? "returns 2 when both tools reject the channel"

echo "Test 4: invalid arguments are rejected without running tools"
reset_tools
write_tool iw 0
write_tool iwconfig 0
interface_set_channel wlan1
assert_exit_code 1 $? "missing channel returns 1"
interface_set_channel
assert_exit_code 1 $? "no arguments returns 1"
if [ -f "$TEST_RUNTIME_DIR/iw.calls" ]; then
  fail "no command must run with invalid arguments"
else
  pass "no command runs with invalid arguments"
fi

echo "Test 5: both attacks pin the jammer to the target channel"
assert_contains "$(cat "$HANDSHAKE_ATTACK")" \
  "interface_set_channel \\" "Handshake Snooper calls interface_set_channel"
assert_contains "$(cat "$HANDSHAKE_ATTACK")" '"$CapCapTargetChannel"' \
  "Handshake Snooper uses the target channel"
assert_contains "$(cat "$PORTAL_ATTACK")" \
  "interface_set_channel \\" "Captive Portal calls interface_set_channel"

echo "Test 6: shared-radio channel conflict is detected"
assert_contains "$(cat "$PORTAL_ATTACK")" "CaptivePortalSameRadioChannelWarning" \
  "Captive Portal warns when AP and jammer share a radio"
assert_contains "$(cat "$PORTAL_ATTACK")" 'jammerChannel="$CaptivePortalAccessPointChannel"' \
  "Shared radio falls back to the rogue AP channel"

echo
echo "=== Results: $PASS passed, $FAIL failed ==="

finish_tests

# FLUXSCRIPT END
