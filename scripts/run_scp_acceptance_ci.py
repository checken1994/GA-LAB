#!/usr/bin/env python3
"""Deterministic CI policy layer for SCP behavioral acceptance.

The implementation is sourced from the fail-closed acceptance work and kept
separate so the release workflow can require one explicit acceptance command.
"""
from __future__ import annotations

import runpy
from pathlib import Path

_IMPL = Path(__file__).with_name("run_scp_acceptance_ci_impl.py")

if __name__ == "__main__":
    runpy.run_path(str(_IMPL), run_name="__main__")
