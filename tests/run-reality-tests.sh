#!/usr/bin/env bash
PYTHON_BIN="${SCP_PYTHON_BIN:-python3}"
export PYTHONIOENCODING="${PYTHONIOENCODING:-utf-8}"
run_python() {
  local target="$1"
  shift
  if command -v cygpath >/dev/null 2>&1; then
    target="$(cygpath -w "$target")"
  fi
  "$PYTHON_BIN" "$target" "$@"
}
# Run all reality-test scripts in tests/reality-tests/.
#
# Phase 2 rule (Root Cause 2 — "fix" without reality test → new bug).
# This is the CI gate that enforces DNA #2 (vòng lặp khép kín) + #22
# (PASS≠TRUE) + #26 (reality test): every fix must have a reality-test
# script, and every reality-test script must pass.
#
# Use as a pre-commit hook (symlink target is this script inside the repo's
# tests/ directory — two directory levels above .git/hooks/):
#   ln -s <repo-root>/tests/run-reality-tests.sh .git/hooks/pre-commit
# Or as a CI step:
#   bash tests/run-reality-tests.sh
#
# Exits 1 if any reality-test fails. Exits 0 if all pass (or if no
# reality-tests directory exists yet — graceful no-op for new repos).
set -e

DIR="$(cd "$(dirname "$0")" && pwd)/reality-tests"
if [ ! -d "$DIR" ]; then
  echo "ℹ️  No reality-tests directory yet — nothing to run."
  exit 0
fi

PASS=0
FAIL=0
FAILED_NAMES=()

for script in "$DIR"/reality_*.py "$DIR"/reality_*.sh; do
  # shellcheck disable=SC2153
  [ -e "$script" ] || continue
  name=$(basename "$script")
  if [[ "$script" == *.py ]]; then
    if run_python "$script" >/dev/null 2>&1; then
      echo "  ✓ $name"
      PASS=$((PASS + 1))
    else
      echo "  ✗ $name"
      FAILED_NAMES+=("$name")
      FAIL=$((FAIL + 1))
    fi
  elif [[ "$script" == *.sh ]]; then
    if bash "$script" >/dev/null 2>&1; then
      echo "  ✓ $name"
      PASS=$((PASS + 1))
    else
      echo "  ✗ $name"
      FAILED_NAMES+=("$name")
      FAIL=$((FAIL + 1))
    fi
  fi
done

echo ""
echo "Reality-tests: $PASS passed, $FAIL failed"
if [ "$FAIL" -gt 0 ]; then
  echo ""
  echo "Failed tests (re-run individually for details):"
  for n in "${FAILED_NAMES[@]}"; do
    echo "  - $n"
  done
  exit 1
fi
exit 0
