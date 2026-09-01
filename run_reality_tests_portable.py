#!/usr/bin/env python3
"""Fail-closed, cross-platform runner for all committed SCP reality tests.

Every ``tests/reality-tests/reality_*.py`` script is executed in its own Python
process from the repository root. Missing test inventory, timeouts, crashes, or
non-zero exits are release failures. The runner keeps going after failures so CI
collects complete evidence instead of hiding later reality-test results.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REALITY_DIR = ROOT / "tests" / "reality-tests"
DEFAULT_TIMEOUT_SECONDS = 120


def _timeout_seconds() -> int:
    raw = os.environ.get("SCP_REALITY_TEST_TIMEOUT_SECONDS", str(DEFAULT_TIMEOUT_SECONDS))
    try:
        value = int(raw)
    except ValueError as exc:
        raise SystemExit("SCP_REALITY_TEST_TIMEOUT_SECONDS must be an integer") from exc
    if value <= 0:
        raise SystemExit("SCP_REALITY_TEST_TIMEOUT_SECONDS must be > 0")
    return value


def main() -> int:
    if not REALITY_DIR.is_dir():
        print(f"FAIL: reality-test directory is missing: {REALITY_DIR}", file=sys.stderr)
        return 1

    scripts = sorted(path for path in REALITY_DIR.glob("reality_*.py") if path.is_file())
    if not scripts:
        print(f"FAIL: no reality_*.py tests found in {REALITY_DIR}", file=sys.stderr)
        return 1

    timeout = _timeout_seconds()
    passed: list[str] = []
    failed: list[tuple[str, str]] = []

    print(f"Reality-test inventory: {len(scripts)} scripts; timeout={timeout}s each")
    for script in scripts:
        rel = script.relative_to(ROOT).as_posix()
        try:
            result = subprocess.run(
                [sys.executable, str(script)],
                cwd=ROOT,
                env=os.environ.copy(),
                text=True,
                encoding="utf-8",
                errors="replace",
                capture_output=True,
                timeout=timeout,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            stdout = exc.stdout or ""
            stderr = exc.stderr or ""
            detail = f"TIMEOUT after {timeout}s\n{stdout}\n{stderr}".strip()
            failed.append((rel, detail))
            print(f"  FAIL {rel} (timeout)")
            continue

        if result.returncode == 0:
            passed.append(rel)
            print(f"  PASS {rel}")
            continue

        detail = (
            f"exit={result.returncode}\n"
            f"--- stdout ---\n{result.stdout}\n"
            f"--- stderr ---\n{result.stderr}"
        ).strip()
        failed.append((rel, detail))
        print(f"  FAIL {rel} (exit {result.returncode})")

    executed = len(passed) + len(failed)
    print(f"\nReality-tests: discovered={len(scripts)} executed={executed} passed={len(passed)} failed={len(failed)}")

    if executed != len(scripts):
        print("FAIL: not every discovered reality test was executed", file=sys.stderr)
        return 1

    if failed:
        print("\nFailed reality tests:", file=sys.stderr)
        for name, detail in failed:
            print(f"\n===== {name} =====\n{detail}", file=sys.stderr)
        return 1

    print("PASS: all discovered reality tests completed successfully")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
