#!/usr/bin/env bash

source "$(dirname "$(readlink -f "$0")")/lib/testlib.sh"

tests_init "$(basename "$0")"

CLEANUP="$REPO_DIR/scripts/cleanup.sh"
WINDOW_UTILS="$REPO_DIR/lib/WindowUtils.sh"

echo "=== cleanup.sh Test Suite ==="
echo

# cleanup.sh needs root and touches the real system (interfaces, iptables,
# sysctl), so it is inspected instead of executed. The point of these checks is
# that the patterns it greps for still match the names the engine creates: a
# rename that updates one side and not the other silently turns the recovery
# script into a no-op.

# The engine names its tmux session CAPWIFI, falling back to CAPCAP_<pid> when
# that name is already taken by an unrelated session.
engine_sessions=$(grep -oE '_sessionName="[A-Z_]+"' "$WINDOW_UTILS" |
	sed 's/_sessionName="//; s/"$//' | sort -u | tr '\n' ' ')

# Pull the exact ERE the script hands to grep, then run it the same way the
# script does: over the output of `tmux ls`.
session_regex=$(grep -oE "grep -oE '\^\(.*\):'" "$CLEANUP" |
	sed "s/^grep -oE '//; s/'$//")

echo "Test 1: the session matcher finds the engine's session names"
echo "    engine names: ${engine_sessions:-<none>}"

if [ -z "$session_regex" ]; then
	fail "Could not extract the tmux session matcher from cleanup.sh"
else
	echo "    matcher:      $session_regex"
	found=$(printf '%s\n' \
		"CAPWIFI: 1 windows (created Sat Nov  1 01:00:00 2026)" \
		"CAPCAP_4242: 1 windows (created Sat Nov  1 01:00:00 2026)" |
		grep -oE "$session_regex" | tr '\n' ' ')

	if [ "$(echo "$found" | wc -w)" -eq 2 ]; then
		pass "CAPWIFI and CAPCAP_<pid> sessions are both matched"
	else
		fail "matcher only found: ${found:-<nothing>}"
	fi
fi

echo "Test 2: the session matcher leaves unrelated sessions alone"
if printf '%s\n' "other: 1 windows (created now)" "CAPWIFI2: 1 windows (created now)" |
	grep -qE "$session_regex" 2>/dev/null; then
	fail "matcher also catches unrelated sessions"
else
	pass "unrelated tmux sessions are not killed"
fi

echo "Test 3: processes are matched under the current and pre-rename names"
if grep -q 'pkill -SIGINT -f "capwifi\.sh"' "$CLEANUP"; then
	pass "current capwifi.sh processes are cleaned up"
else
	fail "cleanup.sh does not match capwifi.sh"
fi
if grep -q 'pkill -SIGINT -f "capcapwifi\.sh"' "$CLEANUP"; then
	pass "pre-rename capcapwifi.sh processes are cleaned up too"
else
	fail "cleanup.sh only matches capwifi.sh; an in-place upgrade leaks processes"
fi

echo "Test 4: interface prefix matches what the engine assigns"
engine_prefixes=$(grep -oE 'capcap_next_assignable_interface [a-z]+' "$REPO_DIR/capwifi.sh" |
	grep -oE '[a-z]+$' | sort -u)
cleanup_prefix=$(grep -oE "grep -oE '[a-z]+\[\^ :@\]\+'" "$CLEANUP" |
	grep -oE "'[a-z]+" | tr -d "'")
echo "    engine:  $(echo "$engine_prefixes" | tr '\n' ' ')"
echo "    cleanup: ${cleanup_prefix:-<none>}"

if [ -z "$cleanup_prefix" ]; then
	fail "Could not find the interface prefix in cleanup.sh"
elif echo "$engine_prefixes" | grep -qx "$cleanup_prefix"; then
	pass "cleanup.sh restores interfaces under the engine's prefix ($cleanup_prefix)"
else
	fail "cleanup.sh looks for prefix '$cleanup_prefix' but the engine assigns '$engine_prefixes'"
fi

echo "Test 5: the workspace path still matches the engine's default"
engine_workspace=$(grep -oE 'CAPCAPWorkspacePath:-/tmp/[a-z]+' "$REPO_DIR/capwifi.sh" |
	sed 's/.*:-//' | head -1)
if [ -n "$engine_workspace" ] && grep -q "$engine_workspace" "$CLEANUP"; then
	pass "cleanup.sh removes the engine's workspace ($engine_workspace)"
else
	fail "cleanup.sh removes a different workspace than the engine uses"
fi

finish_tests

# CAPWIFI END
