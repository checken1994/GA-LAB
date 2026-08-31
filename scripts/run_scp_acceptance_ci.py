#!/usr/bin/env python3
"""Bootstrap SCP acceptance with deterministic repository/import/provider context.

The main acceptance runner intentionally exercises SCP as an external process.
This bootstrap supplies a second provider *family* on the same loopback fixture
so cross-provider independence is tested without real Internet/API dependency.
No production verification rule is weakened for CI.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _arg_value(name: str, default: str) -> str:
    try:
        index = sys.argv.index(name)
    except ValueError:
        return default
    if index + 1 >= len(sys.argv):
        return default
    return sys.argv[index + 1]


def configure_acceptance_environment() -> None:
    provider_port = _arg_value("--provider-port", "18081")
    os.environ["SCP_LLM_FALLBACK_PROVIDERS"] = (
        "acceptance-independent:ACCEPTANCE_PROVIDER_KEY:"
        "ACCEPTANCE_PROVIDER_BASE_URL:ACCEPTANCE_PROVIDER_MODEL"
    )
    os.environ["ACCEPTANCE_PROVIDER_KEY"] = "acceptance-independent-key"
    os.environ["ACCEPTANCE_PROVIDER_BASE_URL"] = f"http://127.0.0.1:{provider_port}/v1"
    os.environ["ACCEPTANCE_PROVIDER_MODEL"] = "acceptance-independent-model"


if __name__ == "__main__":
    configure_acceptance_environment()
    from scripts.run_scp_acceptance import main

    raise SystemExit(main())
