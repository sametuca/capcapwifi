#!/usr/bin/env bash

# ============================================================ #
# ================== < ShellCheck Gate > ===================== #
# ============================================================ #
# Lints every shell script in the tree against a committed baseline.
#
# The baseline (tests/shellcheck_baseline.txt) records the findings that
# already exist, as "<path>:<code>" pairs. Line numbers are deliberately
# not part of the key: they shift whenever anything above them changes, and
# a key that moves is not a new defect. The gate fails only when a finding
# appears that the baseline does not know about, so the existing backlog is
# visible and frozen while new code stays clean.
#
# Usage:
#   scripts/run_shellcheck.sh                  # check (fails on new findings)
#   scripts/run_shellcheck.sh --update-baseline # accept current findings
#
# Environment:
#   SHELLCHECK_SEVERITY  severity to report (default: warning)
#   SHELLCHECK           shellcheck binary (default: shellcheck)

set -uo pipefail

SCRIPT_DIR=$(dirname "$(readlink -f "$0")")
REPO_DIR=$(dirname "$SCRIPT_DIR")
BASELINE="$REPO_DIR/tests/shellcheck_baseline.txt"
SEVERITY=${SHELLCHECK_SEVERITY:-warning}
SHELLCHECK=${SHELLCHECK:-shellcheck}

if ! command -v "$SHELLCHECK" >/dev/null 2>&1; then
  echo "shellcheck not found; install it or set SHELLCHECK." >&2
  exit 2
fi

__raw_output=$(mktemp "${TMPDIR:-/tmp}/capcap-shellcheck.XXXXXX")
__current_keys=$(mktemp "${TMPDIR:-/tmp}/capcap-shellcheck-keys.XXXXXX")
trap 'rm -f "$__raw_output" "$__current_keys"' EXIT

# Full report, kept for the failure message.
find "$REPO_DIR" -path "$REPO_DIR/.git" -prune -o \
  -type f -name '*.sh' -print0 |
  xargs -0 -r "$SHELLCHECK" --severity="$SEVERITY" -f gcc 2>/dev/null \
    >"$__raw_output" || true

# "<path>:<code>" keys, repo-relative and stable.
sed -E 's/^([^:]+):[0-9]+:[0-9]+: .*\[(SC[0-9]+)\]$/\1:\2/' "$__raw_output" |
  sed "s|^$REPO_DIR/||" |
  grep -E '\.sh:SC[0-9]+$' |
  sort -u >"$__current_keys" || true

if [ "${1:-}" = "--update-baseline" ]; then
  cp "$__current_keys" "$BASELINE"
  echo "Wrote $(wc -l <"$BASELINE" | tr -d ' ') finding key(s) to ${BASELINE#"$REPO_DIR/"}."
  exit 0
fi

if [ ! -f "$BASELINE" ]; then
  echo "Baseline missing: ${BASELINE#"$REPO_DIR/"}" >&2
  echo "Run: scripts/run_shellcheck.sh --update-baseline" >&2
  exit 2
fi

__known=$(mktemp "${TMPDIR:-/tmp}/capcap-shellcheck-known.XXXXXX")
__new=$(mktemp "${TMPDIR:-/tmp}/capcap-shellcheck-new.XXXXXX")
trap 'rm -f "$__raw_output" "$__current_keys" "$__known" "$__new"' EXIT

sort -u "$BASELINE" >"$__known"
comm -23 "$__current_keys" "$__known" >"$__new"

if [ -s "$__new" ]; then
  echo "New ShellCheck findings (not in the baseline):"
  echo
  while IFS= read -r key; do
    [[ -n "$key" ]] || continue
    printf '  %s\n' "$key"
    grep -F "${key%:*}" "$__raw_output" 2>/dev/null |
      grep -F "${key##*:}" |
      sed -E 's/^[^:]+://; s/^/      /' || true
  done <"$__new"
  echo
  echo "Fix these, or accept them deliberately with:"
  echo "  scripts/run_shellcheck.sh --update-baseline"
  exit 1
fi

# Fixed findings are good news; report them without failing the build.
__stale=$(comm -13 "$__current_keys" "$__known" | wc -l | tr -d ' ')
if [ "$__stale" -gt 0 ]; then
  echo "Note: $__stale baseline entr(y/ies) no longer reproduce."
  echo "Run scripts/run_shellcheck.sh --update-baseline to shrink the baseline."
fi

echo "ShellCheck clean against the baseline ($(wc -l <"$__known" | tr -d ' ') known finding key(s))."

# FLUXSCRIPT END
