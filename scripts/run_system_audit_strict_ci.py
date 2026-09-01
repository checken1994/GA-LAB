#!/usr/bin/env python3
"""CI adapter for the strict system audit without weakening runtime egress.

The strict audit intentionally runs its assembled runtime with
SCP_EGRESS_MODE=deny. Some unit-level provider failover tests inject a fake
HTTP client and must exercise logic *behind* the egress guard; inheriting deny
would stop those tests at the guard and never test failover.

This adapter changes only the environment of pytest subprocesses: it pins
SCP_EGRESS_MODE and provider credential variables to empty strings. Pinning
rather than deleting prevents dotenv/config loading from restoring deny mode
or live credentials inside the hermetic test subprocess. The parent strict
audit remains deny-egress, so boot/reality/bounded runtime checks keep the
fail-closed network policy. Dedicated egress-policy tests set deny/allowlist
explicitly and assert that denied external transports are never touched.
"""
from __future__ import annotations

import os
import subprocess
import sys

from scripts import run_system_audit_strict as strict


def _hermetic_pytest_env() -> dict[str, str]:
    env = os.environ.copy()
    # Empty-but-present blocks dotenv/config loaders from restoring deny mode
    # while still making llm_egress_allowed() use its historical test behavior.
    env["SCP_EGRESS_MODE"] = ""
    # Empty-but-present also prevents dotenv from loading real provider keys.
    for key in (
        "OPENROUTER_API_KEY",
        "OPENROUTER_API_KEY_2",
        "OPENROUTER_API_KEY_3",
        "OPENAI_API_KEY",
        "DEEPSEEK_API_KEY",
        "GEMINI_API_KEY",
        "GLM_API_KEY",
    ):
        env[key] = ""
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
