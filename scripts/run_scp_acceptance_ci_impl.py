#!/usr/bin/env python3
"""Fail-closed SCP behavioral acceptance implementation for CI.

This implementation intentionally delegates to the strict system audit because
that runner exercises the assembled runtime across real process, HTTP,
persistence, recovery, tamper-detection and bounded-runtime boundaries.  It is
therefore at least as strict as a unit/component acceptance shim and keeps a
missing acceptance implementation from being silently skipped.
"""
from __future__ import annotations

from scripts.run_system_audit_strict import main as run_strict_system_audit


def main() -> int:
    return int(run_strict_system_audit())


if __name__ == "__main__":
    raise SystemExit(main())
