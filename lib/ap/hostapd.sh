#!/usr/bin/env bash

# ================================================================
# Configuration Section
# ================================================================
APServiceConfigDirectory=$CAPCAPWorkspacePath
# ================================================================

#if [ "$APServiceVersion" ]; then return 0; fi
#readonly APServiceVersion="1.0"

function ap_service_stop() {
  if [ "$APServiceXtermPID" ]; then
    kill $APServiceXtermPID &>> $CAPCAPOutputDevice
  fi

  if [ "$APServicePID" ]; then
    kill $APServicePID &>> $CAPCAPOutputDevice
  fi

  APServiceXtermPID=""
  APServicePID=""
}

function ap_service_reset() {
  ap_service_stop

  # Restore original regulatory domain if we changed it.
  if [ "$APServiceOrigRegDomain" ]; then
    local __iw=$(command -v iw 2>/dev/null || echo /usr/sbin/iw)
    if [ -x "$__iw" ]; then
      "$__iw" reg set "$APServiceOrigRegDomain" 2>/dev/null
    fi
    APServiceOrigRegDomain=""
  fi

  # Reset MAC address to original.
  if [ "$APServiceInterface" ]; then
    ip link set "$APServiceInterface" down 2>/dev/null
    sleep 0.25

    macchanger -p "$APServiceInterface" &>> $CAPCAPOutputDevice
    sleep 0.25

    ip link set "$APServiceInterface" up 2>/dev/null
    sleep 0.25
  fi

  APServiceAccessInterface=""

  APServiceChannel=""
  APServiceMAC=""
  APServiceSSID=""
  APServiceInterfaceAddress=""
  APServiceInterface=""

}

function ap_service_route() {
  echo "APService: No custom routes for hostapd" >> $CAPCAPOutputDevice
}

function ap_service_prep() {
  if [ ${#@} -lt 5 ]; then return 1; fi
  
  APServiceInterface=$1
  APServiceInterfaceAddress=$2
  APServiceSSID=$3
  APServiceMAC=$4
  APServiceChannel=$5
  
  ap_service_stop

  # Validate the inputs before they reach the config file. The SSID and BSSID
  # are attacker-influenced (they come from scanned beacons, and the MAC is
  # also used as a file name component), so both are treated as untrusted:
  # control characters are stripped, because a line-based hostapd config
  # cannot represent them and a newline would inject extra directives such as
  # "wpa=2" into the file.
  APServiceSSID=${APServiceSSID//[$'\r\n\t']/}

  if [[ ! "$APServiceMAC" =~ ^([0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}$ ]]; then
    echo "Invalid AP BSSID: '$APServiceMAC'" >> "$CAPCAPOutputDevice"
    return 1
  fi

  if [[ ! "$APServiceChannel" =~ ^[0-9]{1,4}$ ]]; then
    echo "Invalid AP channel: '$APServiceChannel'" >> "$CAPCAPOutputDevice"
    return 1
  fi

  # For 5GHz channels, set a permissive regulatory domain to allow
  # transmission (many adapters default to country 00 which marks
  # all 5GHz as no-IR/passive-scan only).
  if [ "$APServiceChannel" -gt 14 ] 2>/dev/null; then
    local __iw=$(command -v iw 2>/dev/null || echo /usr/sbin/iw)
    if [ -x "$__iw" ]; then
      APServiceOrigRegDomain=$("$__iw" reg get 2>/dev/null | grep -m1 "^country" | sed 's/country \([A-Z0-9]*\).*/\1/')
      "$__iw" reg set "${CAPCAPRegDomain:-US}" 2>/dev/null
      sleep 0.5
    fi
  fi

  # Prepare the hostapd config file.
  local __hwMode="g"
  local __extraConf=""
  if [ "$APServiceChannel" -gt 14 ] 2>/dev/null; then
    __hwMode="a"
    __extraConf="country_code=${CAPCAPRegDomain:-US}
ieee80211d=1"
  fi

  echo "\
interface=$APServiceInterface
driver=nl80211
ssid=$APServiceSSID
channel=$APServiceChannel
hw_mode=$__hwMode
$__extraConf" \
  > "$APServiceConfigDirectory/$APServiceMAC-hostapd.conf"

  # Spoof virtual interface MAC address.
  ip link set "$APServiceInterface" down 2>/dev/null
  sleep 0.5

  macchanger --mac="$APServiceMAC" "$APServiceInterface" &>> $CAPCAPOutputDevice
  sleep 0.5

  ip link set "$APServiceInterface" up 2>/dev/null
  sleep 0.5

  # HostAPD sets the virtual interface mode
  # to master, which is supported by kea-dhcp4.
  APServiceAccessInterface=$APServiceInterface
}

function ap_service_start() {
  ap_service_stop

  capcap_window_open APServiceXtermPID \
    "CAPWIFI AP Service [hostapd]" "$TOP" "#000000" "#FFFFFF" \
    "hostapd \"$APServiceConfigDirectory/$APServiceMAC-hostapd.conf\""

  # Wait till hostapd has started and its virtual interface is ready.
  # Bail if the window process has already exited (hostapd failed to start).
  local apWaitRetry=0
  while [ ! "$APServicePID" ]; do
    sleep 1
    APServicePID=$(pgrep -P $APServiceXtermPID 2>/dev/null)
    # If the window process itself is gone, hostapd failed — abort.
    if [ -n "$APServiceXtermPID" ] && ! kill -0 "$APServiceXtermPID" 2>/dev/null; then
      echo "hostapd window exited; AP service failed to start." >> $CAPCAPOutputDevice
      return 1
    fi
    apWaitRetry=$((apWaitRetry + 1))
    if [ $apWaitRetry -ge 15 ]; then
      echo "hostapd did not start within 15s; aborting." >> $CAPCAPOutputDevice
      return 1
    fi
  done

  ap_service_route
}

# FLUXSCRIPT END
