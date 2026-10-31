#!/usr/bin/env bash
#
# `--install-deps` yüzeyi: GUI ilk açılışta eksik paketleri bununla kuruyor.
# Test gerçek kurulum yapmaz; bayrağın, fonksiyonun ve durum satırlarının
# yerinde olduğunu doğrular.

source "$(dirname "$(readlink -f "$0")")/lib/testlib.sh"

tests_init "$(basename "$0")"

MAIN="$REPO_DIR/capcapwifi.sh"
HELP="$REPO_DIR/lib/HelpUtils.sh"

echo "=== Install-Deps Mode Test Suite ==="
echo

assert_contains "$(cat "$MAIN")" "--install-deps" "CLI knows --install-deps"

if grep -q 'install-deps) CAPCAPInstallDeps=1;;' "$MAIN"; then
  pass "--install-deps sets the flag"
else
  fail "--install-deps sets the flag"
fi

if grep -q '^capcap_configure_dependencies() {' "$MAIN"; then
  pass "dependency installer is its own function"
else
  fail "dependency installer is its own function"
fi

# Startup must reuse the same function, otherwise the two paths can drift.
startup_body=$(awk '/^capcap_startup\(\) \{/{f=1} f{print} f&&/^\}/{exit}' "$MAIN")
assert_contains "$startup_body" "capcap_configure_dependencies" "startup reuses the installer"
assert_contains "$startup_body" "if ! capcap_configure_dependencies; then" "startup aborts when install fails"

# The installer must not `exit` by itself: startup needs to unwind, and the
# install-deps mode needs to report a status instead of dying mid-way.
deps_body=$(awk '/^capcap_configure_dependencies\(\) \{/{f=1} f{print} f&&/^\}/{exit}' "$MAIN")
if printf '%s\n' "$deps_body" | grep -Eq '^ *exit '; then
  fail "installer returns instead of exiting"
else
  pass "installer returns instead of exiting"
fi

for marker in DEP_CHECK DEP_MISSING DEP_OK DEP_FAILED; do
  assert_contains "$deps_body" "$marker" "installer emits $marker"
done

# Mode block: runs the installer, prints a final line, exits 0/7.
mode_body=$(awk '/CAPCAPInstallDeps" = "1"/{f=1} f{print} f&&/^fi$/{exit}' "$MAIN")
assert_contains "$mode_body" "capcap_configure_dependencies" "mode calls the installer"
assert_contains "$mode_body" "exit 0" "mode exits 0 on success"
assert_contains "$mode_body" "exit 7" "mode exits 7 on failure"

# Missing translations must not leave an empty line: English is sourced first.
assert_contains "$mode_body" 'language/en.sh' "mode falls back to English strings"

# Pre-parse: the mode needs no display, so it must skip the X11 check.
preparse=$(awk '/^for arg in "\$@"; do/{f=1} f{print} f&&/^done$/{exit}' "$MAIN")
assert_contains "$preparse" "--install-deps" "pre-parse knows --install-deps"
assert_contains "$(cat "$MAIN")" 'CAPCAPPreParseInstallDeps" ]' "install-deps skips the display check"

# Locales used by the mode.
for locale in en tur; do
  file="$REPO_DIR/language/$locale.sh"
  for key in CAPCAPInstallDepsNotice CAPCAPInstallDepsDone CAPCAPInstallDepsFailed; do
    if (
      # shellcheck source=/dev/null
      source "$file"
      [ -n "${!key-}" ]
    ); then
      pass "$locale.sh defines $key"
    else
      fail "$locale.sh defines $key"
    fi
  done
done

assert_contains "$(cat "$HELP")" "--install-deps" "help documents --install-deps"

# GUI tarafı: denetleyici kurulum çağrısını ve tamamlanma olayını taşımalı.
controller="$REPO_DIR/gui/controller.py"
assert_contains "$(cat "$controller")" "def install_dependencies" "GUI can trigger the installer"
assert_contains "$(cat "$controller")" "on_dependency_install" "GUI gets an install-complete callback"
assert_contains "$(cat "$controller")" '"--install-deps"' "GUI passes --install-deps"

finish_tests
