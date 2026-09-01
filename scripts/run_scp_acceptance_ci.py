#!/usr/bin/env python3
"""Deterministic CI policy layer for SCP behavioral acceptance.

The implementation is sourced from the fail-closed acceptance work and kept
separate so the release workflow can require one explicit acceptance command.
"""
from __future__ import annotations

import runpy
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

_IMPL = Path(__file__).with_name("run_scp_acceptance_ci_impl.py")
if not _IMPL.is_file():
    raise SystemExit(f"acceptance implementation missing: {_IMPL}")

if __name__ == "__main__":
    runpy.run_path(str(_IMPL), run_name="__main__")
