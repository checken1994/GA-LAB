#!/usr/bin/env python3
"""CI adapter for the strict system audit without weakening runtime egress.

The strict audit intentionally runs its assembled runtime with
SCP_EGRESS_MODE=deny. Some unit-level provider failover tests inject a fake
HTTP client and must exercise logic behind the egress guard; inheriting deny
would stop those tests at the guard and never test failover.

Only pytest subprocesses lose SCP_EGRESS_MODE. The parent strict-audit process
remains deny-egress for boot/reality/bounded runtime checks. The full suite
contains dedicated LLM egress-policy tests that explicitly assert deny and
allowlist behavior.
"""
from __future__ import annotations

import os
import subprocess
import sys

from scripts import run_system_audit_strict as strict


def _hermetic_pytest_env() -> dict[str, str]:
    env = os.environ.copy()
    env.pop("SCP_EGRESS_MODE", None)
    for key in (
        "OPENROUTER_API_KEY",
        "OPENROUTER_API_KEY_2",
        "OPENROUTER_API_KEY_3",
        "OPENAI_API_KEY",
        "DEEPSEEK_API_KEY",
        "GEMINI_API_KEY",
        "GLM_API_KEY",
    ):
        env.pop(key, None)
    return env


def _run_pytest(paths: list[str], timeout: int) -> dict:
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", *paths, "--tb=short"],
        cwd=strict.ROOT,
        capture_output=True,
        text=True,
        timeout=timeout,
        env=_hermetic_pytest_env(),
    )
    return {
        "ok": proc.returncode == 0,
        "returncode": proc.returncode,
        "output_tail": (proc.stdout + "\n" + proc.stderr)[-6000:],
    }


def _step_full_pytest() -> dict:
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "--tb=no"],
        cwd=strict.ROOT,
        capture_output=True,
        text=True,
        timeout=600,
        env=_hermetic_pytest_env(),
    )
    return {
        "ok": proc.returncode == 0,
        "returncode": proc.returncode,
        "output_tail": (proc.stdout + "\n" + proc.stderr)[-6000:],
    }


def main() -> int:
    strict._run_pytest = _run_pytest
    strict.step_full_pytest = _step_full_pytest
    return int(strict.main())


if __name__ == "__main__":
    raise SystemExit(main())
