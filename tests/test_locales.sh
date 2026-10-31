#!/usr/bin/env bash

source "$(dirname "$(readlink -f "$0")")/lib/testlib.sh"

tests_init "$(basename "$0")"
shopt -s nullglob

check_required_variables() {
  local locale_file=$1
  shift

  if (
    source "$locale_file"
    for required_name in "$@"; do
      [ -n "${!required_name-}" ] || exit 1
    done
  ); then
    pass "$(basename "$locale_file") loads required strings"
  else
    fail "$(basename "$locale_file") is missing required strings"
  fi
}

echo "=== Locale Syntax and Loading Test Suite ==="
echo

for locale_file in "$REPO_DIR"/language/*.sh; do
  if bash -n "$locale_file"; then
    pass "$(basename "$locale_file") passes bash -n"
  else
    fail "$(basename "$locale_file") fails bash -n"
  fi

  check_required_variables \
    "$locale_file" \
    CAPCAPInterfaceQuery \
    CAPCAPAttackQuery \
    CAPCAPCleanupSuccessNotice
done

for locale_file in "$REPO_DIR"/attacks/Captive\ Portal/language/*.sh; do
  if bash -n "$locale_file"; then
    pass "Captive Portal $(basename "$locale_file") passes bash -n"
  else
    fail "Captive Portal $(basename "$locale_file") fails bash -n"
  fi

  check_required_variables \
    "$locale_file" \
    CaptivePortalJammerInterfaceQuery \
    CaptivePortalAPServiceQuery \
    CaptivePortalConnectivityQuery
done

for locale_file in "$REPO_DIR"/attacks/Handshake\ Snooper/language/*.sh; do
  if bash -n "$locale_file"; then
    pass "Handshake Snooper $(basename "$locale_file") passes bash -n"
  else
    fail "Handshake Snooper $(basename "$locale_file") fails bash -n"
  fi

  check_required_variables \
    "$locale_file" \
    HandshakeSnooperJammerInterfaceQuery \
    HandshakeSnooperMethodQuery \
    HandshakeSnooperArbiterSuccededNotice
done

# English is sourced first and the selected locale only overrides what it
# defines, so every string these screens use has to exist in en.sh or the
# screen renders blanks.
check_required_variables \
  "$REPO_DIR/language/en.sh" \
  CAPCAPTargetListTitle \
  CAPCAPTargetListLegendClients \
  CAPCAPTargetListLegendHandshake \
  CAPCAPTargetListLegendDFS \
  CAPCAPTargetListColumns \
  CAPCAPTargetListFilteredNotice \
  CAPCAPTargetListEmptyFiltered \
  CAPCAPTargetListEmptyNone \
  CAPCAPDeauthMethodUsing \
  CAPCAPDeauthMethodOverrideTip \
  CAPCAPDeauthMethodUnknown

check_required_variables \
  "$REPO_DIR/attacks/Captive Portal/language/en.sh" \
  CaptivePortalVerificationMethodNoneOption \
  CaptivePortalVerificationMethodNoneNotice

finish_tests

# FLUXSCRIPT END
