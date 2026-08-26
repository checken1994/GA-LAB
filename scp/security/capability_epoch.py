from __future__ import annotations

import json
import os
import tempfile
import threading
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any


class CapabilityRevokedError(RuntimeError):
    """Raised when a new action cannot receive a capability token."""


@dataclass(frozen=True)
class CapabilityToken:
    subject: str
    epoch: int
    token_id: str
    issued_at: float


class CapabilityAuthority:
    """Durable, epoch-based capability revocation for one SCP tool boundary.

    Revocation increments the epoch and persists an atomic JSON state file. Every
    action must obtain and validate a token immediately before dispatch. Old
    tokens remain invalid after both revoke and restore because restore also
    increments the epoch.
    """

    SCHEMA_VERSION = "scp-capability-epoch-v1"

    def __init__(self, state_path: str | Path) -> None:
        self.state_path = Path(state_path)
        self._lock = threading.RLock()
        self.state_path.parent.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _default_state() -> dict[str, Any]:
        return {
            "schema_version": CapabilityAuthority.SCHEMA_VERSION,
            "epoch": 0,
            "revoked": False,
            "reason": "initial",
            "actor": "system",
            "updated_at": time.time(),
        }

    def _load(self) -> dict[str, Any]:
        if not self.state_path.exists():
            return self._default_state()
        try:
            data = json.loads(self.state_path.read_text(encoding="utf-8"))
            if data.get("schema_version") != self.SCHEMA_VERSION:
                raise ValueError("unsupported capability state schema")
            if not isinstance(data.get("epoch"), int) or data["epoch"] < 0:
                raise ValueError("invalid capability epoch")
            if not isinstance(data.get("revoked"), bool):
                raise ValueError("invalid capability revoked flag")
            return data
        except (OSError, ValueError, json.JSONDecodeError):
            # Corrupt control state is fail-closed. A deliberate restore call
            # writes a fresh valid epoch; no action is silently permitted.
            state = self._default_state()
            state.update({"epoch": 0, "revoked": True, "reason": "state_corrupt", "actor": "system"})
            return state

    def _persist(self, state: dict[str, Any]) -> None:
        payload = json.dumps(state, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
        fd, temporary = tempfile.mkstemp(prefix="capability-", suffix=".tmp", dir=str(self.state_path.parent))
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, self.state_path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)

    def status(self) -> dict[str, Any]:
        with self._lock:
            state = self._load()
            return {
                "schema_version": state["schema_version"],
                "epoch": state["epoch"],
                "revoked": state["revoked"],
                "reason": state.get("reason", ""),
                "actor": state.get("actor", ""),
                "updated_at": state.get("updated_at"),
                "state_path": str(self.state_path),
            }

    def issue(self, subject: str) -> CapabilityToken:
        subject = str(subject).strip()[:128]
        if not subject:
            raise CapabilityRevokedError("capability subject is required")
        with self._lock:
            state = self._load()
            if state["revoked"]:
                raise CapabilityRevokedError(f"capabilities revoked: {state.get('reason', 'operator_revoke')}")
            return CapabilityToken(subject=subject, epoch=state["epoch"], token_id=uuid.uuid4().hex, issued_at=time.time())

    def validate(self, token: CapabilityToken | None) -> bool:
        if token is None:
            return False
        with self._lock:
            state = self._load()
            return not state["revoked"] and token.epoch == state["epoch"]

    def revoke(self, reason: str = "operator_revoke", actor: str = "operator") -> dict[str, Any]:
        with self._lock:
            state = self._load()
            next_state = {
                **state,
                "epoch": int(state["epoch"]) + 1,
                "revoked": True,
                "reason": str(reason).strip()[:256] or "operator_revoke",
                "actor": str(actor).strip()[:128] or "operator",
                "updated_at": time.time(),
            }
            self._persist(next_state)
            return self.status()

    def restore(self, reason: str = "operator_restore", actor: str = "operator") -> dict[str, Any]:
        with self._lock:
            state = self._load()
            next_state = {
                **state,
                "epoch": int(state["epoch"]) + 1,
                "revoked": False,
                "reason": str(reason).strip()[:256] or "operator_restore",
                "actor": str(actor).strip()[:128] or "operator",
                "updated_at": time.time(),
            }
            self._persist(next_state)
            return self.status()


__all__ = ["CapabilityAuthority", "CapabilityRevokedError", "CapabilityToken"]
