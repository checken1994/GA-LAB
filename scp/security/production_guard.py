"""Fail-closed checks for explicitly declared production mode."""
from __future__ import annotations
import os
from scp.security.secret_loader import read_secret

_DANGEROUS_FLAGS = (
    "SCP_DEV_MODE",
    "SCP_SKIP_STARTUP_GATE",
    "SCP_AUTO_APPROVE_TIER3",
    "SCP_EVOLUTION_AUTO",
    "SCP_ENABLE_CLOSED_LOOP",
    "SCP_TIER3_ALLOW_RELAXATION",
    "SCP_TIER3_ALLOW_BAREEXCEPTPASS",
)
_TRUE = {"1", "true", "yes", "on"}


def enforce_production_safety() -> None:
    """Refuse startup only when explicit production mode is enabled.

    Error messages include flag names and policy names, never secret values.
    """
    if os.environ.get("SCP_PRODUCTION_MODE", "0").strip().lower() not in _TRUE:
        return
    errors: list[str] = []
    active = [
        name
        for name in _DANGEROUS_FLAGS
        if os.environ.get(name, "").strip().lower() in _TRUE
    ]
    if active:
        errors.append("unsafe bypass flags active: " + ", ".join(active))
    egress_mode = os.environ.get("SCP_EGRESS_MODE", "").strip().lower()
    if egress_mode not in {"deny", "allowlist"}:
        errors.append("SCP_EGRESS_MODE must be deny or allowlist in production")
    password = read_secret("SCP_AUTH_PASSWORD", "SCP_AUTH_PASSWORD_FILE")
    if len(password) < 16:
        errors.append("SCP_AUTH_PASSWORD must be at least 16 characters")
    if errors:
        raise RuntimeError(
            "Production safety guard refused startup: " + "; ".join(errors)
        )
