#!/usr/bin/env python3
"""Fail-closed SCP behavioral acceptance implementation for CI.

Acceptance delegates to the strict assembled-system audit. The CI adapter keeps
runtime boot/reality/bounded checks in deny-egress mode while running the
provider unit contracts hermetically behind the separately verified egress
guard. Missing or failing strict-audit checks still propagate a non-zero exit.
"""
from __future__ import annotations

from scripts.run_system_audit_strict_ci import main as run_strict_system_audit


def main() -> int:
    return int(run_strict_system_audit())


if __name__ == "__main__":
    raise SystemExit(main())
