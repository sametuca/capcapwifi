#!/usr/bin/env bash

source "$(dirname "$(readlink -f "$0")")/lib/testlib.sh"

tests_init "$(basename "$0")"

# sandbox_remove_workfile() deletes files as root. The checks below are the
# regression net around the two properties that matter: it must never delete
# outside the workspace, and it must never turn a file name into a command.

SandboxWorkspacePath="$TEST_RUNTIME_DIR/workspace"
SandboxOutputDevice=/dev/null
mkdir -p "$SandboxWorkspacePath/sub"

# shellcheck disable=SC1090
source "$REPO_DIR/lib/SandboxUtils.sh"

remove_workfile() {
  sandbox_remove_workfile "$@"
  echo $?
}

# 1. A normal file inside the workspace is removed.
printf 'data' >"$SandboxWorkspacePath/plain.txt"
status=$(remove_workfile "$SandboxWorkspacePath/plain.txt")
assert_exit_code 0 "$status" "A regular workspace file is removed"
if [ -e "$SandboxWorkspacePath/plain.txt" ]; then
  fail "The removed file is still present"
else
  pass "The removed file is gone"
fi

# 2. A directory inside the workspace is removed recursively.
mkdir -p "$SandboxWorkspacePath/sub/nested"
printf 'x' >"$SandboxWorkspacePath/sub/nested/file"
status=$(remove_workfile "$SandboxWorkspacePath/sub/nested")
assert_exit_code 0 "$status" "A workspace directory is removed"
if [ -e "$SandboxWorkspacePath/sub/nested" ]; then
  fail "The removed directory is still present"
else
  pass "The removed directory is gone"
fi

# 3. Paths outside the workspace are refused, and stay on disk.
outside="$TEST_RUNTIME_DIR/outside.txt"
printf 'keep me' >"$outside"
status=$(remove_workfile "$outside")
assert_exit_code 2 "$status" "A path outside the workspace is refused"
if [ -f "$outside" ]; then
  pass "The outside file was left alone"
else
  fail "The outside file was deleted"
fi

# 4. A sibling directory sharing the workspace name as a prefix is refused.
#    The old prefix test accepted "$SandboxWorkspacePath-evil".
sibling="${SandboxWorkspacePath}-evil"
mkdir -p "$sibling"
printf 'keep me' >"$sibling/file"
status=$(remove_workfile "$sibling/file")
assert_exit_code 2 "$status" "A path in a sibling directory is refused"
if [ -f "$sibling/file" ]; then
  pass "The sibling file was left alone"
else
  fail "The sibling file was deleted"
fi

# 5. The workspace root itself is refused.
status=$(remove_workfile "$SandboxWorkspacePath")
assert_exit_code 2 "$status" "The workspace root is refused"
if [ -d "$SandboxWorkspacePath" ]; then
  pass "The workspace root survived"
else
  fail "The workspace root was deleted"
fi

# 6. A missing parent directory is refused rather than silently ignored.
status=$(remove_workfile "$SandboxWorkspacePath/gone/file.txt")
assert_exit_code 3 "$status" "A missing parent directory is refused"

# 7. A hostile file name is deleted literally, never executed.
hostile="$SandboxWorkspacePath/name with spaces;touch PWNED.txt"
printf 'data' >"$hostile"
status=$(remove_workfile "$hostile")
assert_exit_code 0 "$status" "A file name with spaces and a semicolon is removed"
if [ -e "$hostile" ]; then
  fail "The hostile-named file is still present"
else
  pass "The hostile-named file is gone"
fi
if [ -e "PWNED.txt" ] || [ -e "$TEST_RUNTIME_DIR/PWNED.txt" ]; then
  fail "The file name was interpreted as a command"
else
  pass "The file name was not interpreted as a command"
fi

# 8. A glob character in the name does not expand to its siblings.
mkdir -p "$SandboxWorkspacePath/glob"
printf 'a' >"$SandboxWorkspacePath/glob/a.txt"
printf 'b' >"$SandboxWorkspacePath/glob/b.txt"
status=$(remove_workfile "$SandboxWorkspacePath/glob/*.txt")
assert_exit_code 0 "$status" "A literal glob name is accepted as a path"
if [ -f "$SandboxWorkspacePath/glob/a.txt" ] && [ -f "$SandboxWorkspacePath/glob/b.txt" ]; then
  pass "The glob did not expand to the sibling files"
else
  fail "The glob expanded and deleted sibling files"
fi

finish_tests
exit $?
