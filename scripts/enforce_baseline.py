#!/usr/bin/env python3
"""Enforce the SCP baseline.

The assembled-system acceptance suite is authoritative for behavioral release
invariants. Component tests run afterwards as diagnostics and remain blockers,
but their PASS alone is never reported as proof that SCP is reliable.
"""
from __future__ import annotations

import logging
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ACCEPTANCE_DIR = ROOT / "reports" / "scp_acceptance_baseline"
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("baseline_enforcer")


def run(command: list[str], label: str) -> None:
    logger.info("Running %s...", label)
    result = subprocess.run(command, cwd=ROOT, text=True)
    if result.returncode != 0:
        logger.error("%s failed; baseline is NOT accepted.", label)
        raise SystemExit(result.returncode)
    logger.info("%s passed.", label)


def main() -> int:
    ACCEPTANCE_DIR.mkdir(parents=True, exist_ok=True)
    run(
        [
            sys.executable,
            "scripts/run_scp_acceptance_ci.py",
            "--output-dir",
            str(ACCEPTANCE_DIR),
        ],
        "SCP system acceptance",
    )
    run([sys.executable, "-m", "pytest", "-q"], "component diagnostics")
    logger.info("Baseline accepted: system invariants and component diagnostics both passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
