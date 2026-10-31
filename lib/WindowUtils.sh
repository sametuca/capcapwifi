#!/usr/bin/env bash

# ============================================================ #
# ================ < Window Utils > ========================== #
# ============================================================ #
# Abstraction layer over xterm/tmux for headless operation.
# When -m/--multiplexer is set, uses tmux instead of xterm.

CAPCAPWindowCounter=0

capcap_window_init() {
	# Scan-only and dependency-install modes never open windows, so they must
	# not re-exec into tmux/xterm either: the GUI runs them with piped output.
	if [ "$CAPCAPScanOnly" ] || [ "$CAPCAPInstallDeps" ]; then
		CAPCAPDisplayMode="headless"
		return 0
	fi

	# --multiplexer was requested, or there is no X display to draw into.
	if [ "$CAPCAPTMux" ]; then
		CAPCAPDisplayMode="tmux"

		# If not already inside a tmux session, re-exec inside one.
		if [ -z "$TMUX" ]; then
			local _sessionName="CAPWIFI"
			tmux has-session -t "$_sessionName" 2>/dev/null && _sessionName="CAPCAP_$$"
			exec env LANG=C.UTF-8 LC_ALL=C.UTF-8 \
				tmux new-session -s "$_sessionName" "$0 $CAPCAPOriginalArgs"
		fi

		# Ensure UTF-8 is set for the current session's environment.
		tmux set-environment LANG C.UTF-8 2>/dev/null
		tmux set-environment LC_ALL C.UTF-8 2>/dev/null
		export LANG=C.UTF-8
		export LC_ALL=C.UTF-8

		# If already inside tmux (either we just re-execed or user ran inside tmux),
		# rename the session to CAPWIFI for consistency.
		tmux rename-session CAPWIFI 2>/dev/null

		# Enable mouse support (scrolling, pane selection).
		tmux set-option -g mouse on 2>/dev/null
	else
		# X display present, but xterm may still be missing. Falling back to
		# tmux beats failing halfway through an attack with no output window.
		if ! hash xterm 2>/dev/null && hash tmux 2>/dev/null; then
			CAPCAPDisplayMode="tmux"
			if [ -z "$TMUX" ]; then
				local _sessionName="CAPWIFI"
				tmux has-session -t "$_sessionName" 2>/dev/null && _sessionName="CAPCAP_$$"
				exec env LANG=C.UTF-8 LC_ALL=C.UTF-8 \
					tmux new-session -s "$_sessionName" "$0 $CAPCAPOriginalArgs"
			fi
			tmux rename-session CAPWIFI 2>/dev/null
			tmux set-option -g mouse on 2>/dev/null
			CAPCAPTMux=1
		else
			CAPCAPDisplayMode="xterm"
		fi
	fi
}

# capcap_window_open <pid_var> <title> <geometry> <bg> <fg> <command>
#   pid_var=""  -> foreground/blocking (waits for command to finish)
#   pid_var="X" -> background (stores xterm/tmux parent PID in variable X)
#   In debug mode, windows remain open after command exits.
capcap_window_open() {
	local pidVar="$1"
	local title="$2"
	local geometry="$3"
	local bg="$4"
	local fg="$5"
	local command="$6"

	CAPCAPWindowCounter=$((CAPCAPWindowCounter + 1))
	local windowName="${title:0:30}_${CAPCAPWindowCounter}"
	# Sanitize window name for tmux (no dots or colons)
	windowName=$(echo "$windowName" | tr '.:"' '___')

	if [ "$CAPCAPScanOnly" ]; then
		# Scan-only mode: no terminal windows, just background processes.
		if [ -z "$pidVar" ]; then
			# Foreground/blocking: run directly.
			eval $command
		else
			# Background: run in background, capture PID.
			eval $command &>/dev/null &
			eval "$pidVar=$!"
		fi
	elif [ "$CAPCAPDisplayMode" = "tmux" ]; then
		# Write command to a temp script to avoid all quoting issues with tmux.
		local cmdScript="$CAPCAPWorkspacePath/.cmd_${CAPCAPWindowCounter}.sh"

		if [ -z "$pidVar" ]; then
			# Foreground/blocking: create window, poll until command finishes.
			local doneFile="$CAPCAPWorkspacePath/.window_done_${CAPCAPWindowCounter}"
			rm -f "$doneFile"

			# Use a trap so the done file is written even if the window is
			# closed via Ctrl+C (SIGINT kills the process group before the
			# shell can run a trailing "; echo done" suffix).
			printf '#!/usr/bin/env bash\ntrap '"'"'echo done > "%s"'"'"' EXIT\n%s\n' \
				"$doneFile" "$command" > "$cmdScript"
			chmod +x "$cmdScript"

			if [ "$CAPCAPDebug" ]; then
				tmux new-window -n "$windowName" \
					"$cmdScript; echo 'Press enter to close...'; read"
			else
				tmux new-window -n "$windowName" "$cmdScript"
			fi

			# Poll until the command finishes.
			while [ ! -f "$doneFile" ]; do
				sleep 0.5
			done
			rm -f "$doneFile"
			rm -f "$cmdScript"

			# Refocus the main pane so the caller's output is immediately
			# visible without the user having to switch tmux windows manually.
			[ "$TMUX_PANE" ] && tmux select-pane -t "$TMUX_PANE" 2>/dev/null
		else
			# Background: create detached window, get PID.
			printf '#!/usr/bin/env bash\n%s\n' "$command" > "$cmdScript"
			chmod +x "$cmdScript"
			tmux new-window -d -n "$windowName" "$cmdScript"

			if [ "$CAPCAPDebug" ]; then
				# Set remain-on-exit for debug mode
				tmux set-option -t "$windowName" remain-on-exit on 2>/dev/null
			fi

			# Get the PID of the process running in the new pane.
			local panePID
			panePID=$(tmux list-panes -t "$windowName" -F '#{pane_pid}' 2>/dev/null | head -1)

			if [ -z "$panePID" ]; then
				# Fallback: try to get PID by listing all windows
				sleep 0.5
				panePID=$(tmux list-panes -t "$windowName" -F '#{pane_pid}' 2>/dev/null | head -1)
			fi

			eval "$pidVar=$panePID"
		fi
	else
		# xterm mode (original behavior)
		local holdFlag=""
		if [ "$CAPCAPDebug" ]; then
			holdFlag="-hold"
		fi

		if [ -z "$pidVar" ]; then
			# Foreground/blocking
			xterm $holdFlag -title "$title" $geometry \
				-bg "$bg" -fg "$fg" -e "$command" 2>> $CAPCAPOutputDevice
		else
			# Background
			xterm $holdFlag -title "$title" $geometry \
				-bg "$bg" -fg "$fg" -e "$command" &
			eval "$pidVar=$!"
		fi
	fi

	return 0
}

# capcap_window_close <pid_var_name>
# Kills the window and its process tree, then clears the variable.
capcap_window_close() {
	local pidVarName="$1"
	local pid="${!pidVarName}"

	if [ "$pid" ]; then
		kill "$pid" &> /dev/null
		# Also kill children
		local children
		children=$(pgrep -P "$pid" 2>/dev/null)
		if [ "$children" ]; then
			kill $children &> /dev/null
		fi
		eval "$pidVarName=''"
	fi
}

# capcap_window_cleanup
# Kills the entire CAPWIFI tmux session at shutdown.
capcap_window_cleanup() {
	if [ "$CAPCAPDisplayMode" = "tmux" ]; then
		# Kill all windows in the CAPWIFI session except the current one
		local currentWindow
		currentWindow=$(tmux display-message -p '#{window_id}' 2>/dev/null)

		# Kill all other windows
		local window
		for window in $(tmux list-windows -F '#{window_id}' 2>/dev/null); do
			if [ "$window" != "$currentWindow" ]; then
				tmux kill-window -t "$window" 2>/dev/null
			fi
		done
	fi
}

# FLUXSCRIPT END
