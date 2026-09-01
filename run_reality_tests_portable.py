#!/usr/bin/env python3
"""Fail-closed compatibility entrypoint for the canonical reality-test runner.

The implementation lives in scripts/run_reality_tests_portable.py.  Keeping
this root entrypoint preserves existing release/audit commands while executing
the exact canonical runner and propagating its non-zero exit status.
"""
from __future__ import annotations

import runpy
from pathlib import Path

TARGET = Path(__file__).resolve().parent / "scripts" / "run_reality_tests_portable.py"
if not TARGET.is_file():
    raise SystemExit(f"canonical reality runner missing: {TARGET}")
runpy.run_path(str(TARGET), run_name="__main__")
