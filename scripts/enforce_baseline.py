#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""P0: Enforce Baseline.
Ensures tests pass, and checks if reality evidence (e.g., test reports) aligns with commit.
"""
import subprocess
import sys
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("baseline_enforcer")

def main():
    logger.info("Running P0 Baseline Check...")
    
    # 1. Check pytest passes
    logger.info("Running pytest...")
    result = subprocess.run(["pytest", "-q", "tests/", "scp/tests/"], capture_output=True, text=True)
    if result.returncode != 0:
        logger.error("Pytest failed! Baseline broken.")
        logger.error(result.stdout)
        sys.exit(1)
    logger.info("Pytest passed.")
    
    # 2. Add other evidence checks (README timestamps, coverage snapshots) here
    # For now, if tests pass, baseline is accepted.
    logger.info("Baseline reliable.")
    sys.exit(0)

if __name__ == "__main__":
    main()