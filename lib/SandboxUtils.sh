#!/usr/bin/env bash

if [ "$SandboxUtilsVersion" ]; then return 0; fi
readonly SandboxUtilsVersion="1.0"

# Respect values already provided by the caller (capcapwifi.sh assigns the real
# workspace path right after sourcing this file, and tests point both of these
# at a scratch directory).
SandboxWorkspacePath="${SandboxWorkspacePath:-/tmp/sandbox}"
SandboxOutputDevice="${SandboxOutputDevice:-/dev/stdout}"

# After changing global identifiers in the main script,
# I forgot to update the identifiers here, leading to a
# horrific accident where the script ended and executed
# the command "rm -rf /*" ... yeah, fuck that...
# Spent an entire day retreiving all my shit back.
#
# The deletion below therefore never goes through eval: the target is
# passed as a quoted argument to rm with a leading "--", so neither word
# splitting, pathname expansion, nor an embedded ";" / "$(...)" in a
# filename can turn into a command. The workspace prefix check is kept,
# but it now requires a real path component boundary ("$dir/x"), so a
# sibling directory such as "${dir}-evil" is not accepted.
function sandbox_remove_workfile() {
  local -r __target=${1:-}

  # Check we've got the environment variables ready.
  if [[ -z "$SandboxWorkspacePath" || -z "$SandboxOutputDevice" ]]; then
    echo "The workspace path, or the output device is missing." >"$SandboxOutputDevice"
    return 1
  fi

  # Refuse empty targets, the workspace root itself, and anything that
  # does not sit strictly inside the workspace.
  if [[ -z "$__target" || "$__target" == "$SandboxWorkspacePath" ]]; then
    echo "Stopped an attempt to delete the workspace itself." >"$SandboxOutputDevice"
    return 2
  fi

  if [[ "$__target" != "$SandboxWorkspacePath"/* ]]; then
    echo "Stopped an attempt to delete non-workfiles." >"$SandboxOutputDevice"
    return 2
  fi

  # Resolve the parent directory so a symlinked path cannot be used to
  # escape the workspace (the final component itself may be a symlink we
  # are deleting, which is fine: rm removes the link, not its target).
  local __parent
  __parent=$(dirname -- "$__target")
  if [[ ! -d "$__parent" ]]; then
    echo "Refusing to delete a workfile whose directory does not exist." >"$SandboxOutputDevice"
    return 3
  fi

  # Remove the target (force: no interactive prompt, and "-r" so
  # directories work). "--" stops option parsing for odd file names.
  rm -rf -- "$__target" &> "$SandboxOutputDevice"
}

# FLUXSCRIPT END
