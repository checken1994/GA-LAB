"""Durable TaskKernel public contract and shared state-machine definitions."""
from __future__ import annotations

import hashlib
import json
import re
import secrets
import time
from contextvars import ContextVar
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from scp.kernel_storage import KernelStorage, StorageIntegrityError, make_storage

STATES = {
    "CREATED", "PLANNING", "READY", "QUEUED", "LEASED", "RUNNING",
    "WAITING_TOOL", "VERIFYING", "CHECKPOINTED", "UNKNOWN", "RECOVERING",
    "RECONCILING", "HUMAN_REVIEW", "RETRY_SCHEDULED", "COMPLETED",
    "FAILED", "CANCELLED",
}
TERMINAL = {"COMPLETED", "FAILED", "CANCELLED"}
ALLOWED_TRANSITIONS = {
    "CREATED": {"PLANNING", "CANCELLED"},
    "PLANNING": {"READY", "WAITING_APPROVAL", "FAILED", "CANCELLED"},
    "WAITING_APPROVAL": {"READY", "CANCELLED"},
    "READY": {"QUEUED", "CANCELLED"},
    "QUEUED": {"LEASED", "CANCELLED"},
    "LEASED": {"RUNNING", "RECOVERING", "CANCELLED"},
    "RUNNING": {"WAITING_TOOL", "VERIFYING", "CHECKPOINTED", "RECOVERING", "HUMAN_REVIEW", "FAILED", "CANCELLED"},
    "WAITING_TOOL": {"VERIFYING", "UNKNOWN", "RECOVERING", "FAILED", "CANCELLED"},
    "VERIFYING": {"RUNNING", "COMPLETED", "HUMAN_REVIEW", "FAILED"},
    "CHECKPOINTED": {"RUNNING", "QUEUED", "CANCELLED"},
    "UNKNOWN": {"RECONCILING", "HUMAN_REVIEW", "RECOVERING", "FAILED", "CANCELLED"},
    "HUMAN_REVIEW": {"READY", "CANCELLED", "FAILED"},
    "RECOVERING": {"RECONCILING", "CHECKPOINTED", "QUEUED", "HUMAN_REVIEW", "FAILED"},
    "RECONCILING": {"RECOVERING", "CHECKPOINTED", "QUEUED", "HUMAN_REVIEW", "FAILED", "CANCELLED"},
    "RETRY_SCHEDULED": {"QUEUED", "FAILED", "CANCELLED"},
    "COMPLETED": set(),
    "FAILED": set(),
    "CANCELLED": set(),
}


class KernelError(RuntimeError):
    pass


class InvalidTransition(KernelError):
    pass


class StaleLease(KernelError):
    pass


class KillSwitchActive(KernelError):
    pass


class CheckpointCorrupt(KernelError):
    pass


class NotFound(KernelError):
    pass


@dataclass(frozen=True)
class Lease:
    lease_id: str
    task_id: str
    attempt_id: str
    worker_id: str
    expires_at: float
    fencing_token: int
    global_kill_epoch: int


@dataclass(frozen=True)
class RecoveryDecision:
    decision: str
    reason: str
    safe_to_retry: bool
    required_evidence: tuple[str, ...]
    next_state: str
    escalation: str


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def stable_hash(value: Any) -> str:
    if isinstance(value, bytes):
        raw = value
    else:
        raw = json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    return "sha256:" + hashlib.sha256(raw).hexdigest()


_SENSITIVE_KEY_MARKERS = (
    "password", "passwd", "secret", "token", "api_key", "apikey",
    "authorization", "cookie", "private_key",
)
_SENSITIVE_VALUE_PATTERNS = (
    re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]{8,}"),
    re.compile(r"(?i)(?:api[_-]?key|access[_-]?token|refresh[_-]?token|password|secret)=\S+"),
)


def _checkpoint_contains_secret(value: Any, path: str = "checkpoint") -> bool:
    if isinstance(value, dict):
        for key, child in value.items():
            key_text = str(key).lower().replace("-", "_")
            if any(marker in key_text for marker in _SENSITIVE_KEY_MARKERS):
                return True
            if _checkpoint_contains_secret(child, f"{path}.{key}"):
                return True
        return False
    if isinstance(value, (list, tuple, set)):
        return any(_checkpoint_contains_secret(child, f"{path}[]") for child in value)
    if isinstance(value, str):
        return any(pattern.search(value) for pattern in _SENSITIVE_VALUE_PATTERNS)
    return False


def _assert_checkpoint_safe(value: Any) -> None:
    if _checkpoint_contains_secret(value):
        raise KernelError("checkpoint contains secret material")


def as_json(value: Any) -> str:
    payload = asdict(value) if hasattr(value, "__dataclass_fields__") else value
    return json.dumps(payload, ensure_ascii=False, sort_keys=True)


# Import the implementation only after all public/shared symbols exist. Its
# methods historically resolved these names from this module, so preserve that
# exact namespace explicitly instead of depending on extraction side effects.
from .task_kernel_parts import taskkernel as _taskkernel_part
_taskkernel_part.__dict__.update(globals())
TaskKernel = _taskkernel_part.TaskKernel

# Lease authority is execution-context scoped. ContextVar keeps concurrent
# async tasks/threads from borrowing another worker's lease while preserving
# the existing public idempotency method signatures. Only a successful claim
# binds a lease. Idempotency writes then re-check that exact lease *inside the
# write transaction*, so expiry, release, kill-epoch drift or a newer fencing
# token fail closed. A no-lease duplicate lookup may return "already claimed"
# but cannot create/retry/complete a logical action.
_LEASE_CONTEXT: ContextVar[dict[tuple[int, str], str]] = ContextVar(
    "scp_task_kernel_lease_context", default={}
)


def _bind_lease_context(kernel: Any, lease: Lease) -> None:
    bound = dict(_LEASE_CONTEXT.get())
    bound[(id(kernel), lease.task_id)] = lease.lease_id
    _LEASE_CONTEXT.set(bound)


def _bound_lease_id(kernel: Any, task_id: str) -> str | None:
    return _LEASE_CONTEXT.get().get((id(kernel), task_id))


_original_claim = TaskKernel.claim
_original_claim_next = TaskKernel.claim_next


def _claim_with_lease_context(
    self: Any,
    task_id: str,
    worker_id: str,
    attempt_id: str | None = None,
    ttl_seconds: float = 30.0,
) -> Lease:
    lease = _original_claim(self, task_id, worker_id, attempt_id, ttl_seconds)
    _bind_lease_context(self, lease)
    return lease


def _claim_next_with_lease_context(
    self: Any,
    worker_id: str,
    max_active_per_owner: int = 1,
    ttl_seconds: float = 30.0,
    now: float | None = None,
) -> Lease | None:
    lease = _original_claim_next(self, worker_id, max_active_per_owner, ttl_seconds, now)
    if lease is not None:
        _bind_lease_context(self, lease)
    return lease


def _idempotency_claim_fenced(
    self: Any,
    task_id: str,
    step_id: str,
    action_type: str,
    resource_identity: str,
) -> tuple[str, bool]:
    logical_key = stable_hash(
        {
            "task_id": task_id,
            "step_id": step_id,
            "action_type": action_type,
            "resource_identity": resource_identity,
        }
    )
    lease_id = _bound_lease_id(self, task_id)
    if not lease_id:
        # Recovery/read-only duplicate check is safe without lease authority.
        # Never turn RETRYABLE into CLAIMED and never create a new row here.
        row = self.conn.execute(
            "SELECT logical_key FROM idempotency WHERE logical_key=?", (logical_key,)
        ).fetchone()
        if row:
            return logical_key, False
        raise StaleLease("idempotency claim requires active lease authority")

    self._begin()
    try:
        self._assert_lease(lease_id, task_id)
        row = self.conn.execute(
            "SELECT * FROM idempotency WHERE logical_key=?", (logical_key,)
        ).fetchone()
        if row:
            if row["status"] == "RETRYABLE":
                self.conn.execute(
                    "UPDATE idempotency SET status='CLAIMED',result_ref=NULL WHERE logical_key=?",
                    (logical_key,),
                )
                self._commit()
                return logical_key, True
            self._commit()
            return logical_key, False
        self.conn.execute(
            "INSERT INTO idempotency(logical_key,task_id,step_id,action_type,resource_identity,status,created_at) VALUES (?,?,?,?,?,?,?)",
            (logical_key, task_id, step_id, action_type, resource_identity, "CLAIMED", now_iso()),
        )
        self._commit()
        return logical_key, True
    except Exception:
        self._rollback()
        raise


def _idempotency_complete_fenced(self: Any, logical_key: str, result_ref: str) -> None:
    if not logical_key or not result_ref:
        raise KernelError("invalid idempotency completion")
    self._begin()
    try:
        row = self.conn.execute(
            "SELECT * FROM idempotency WHERE logical_key=?", (logical_key,)
        ).fetchone()
        if not row:
            raise KernelError("idempotency key not found")
        lease_id = _bound_lease_id(self, str(row["task_id"]))
        if not lease_id:
            raise StaleLease("idempotency completion requires active lease authority")
        self._assert_lease(lease_id, str(row["task_id"]))
        if row["status"] == "COMPLETED":
            if row["result_ref"] != result_ref:
                raise KernelError("idempotency result mismatch")
            self._commit()
            return
        if row["status"] != "CLAIMED":
            raise KernelError(f"invalid idempotency status: {row['status']}")
        self.conn.execute(
            "UPDATE idempotency SET status='COMPLETED',result_ref=? WHERE logical_key=?",
            (result_ref, logical_key),
        )
        self._commit()
    except Exception:
        self._rollback()
        raise


def _idempotency_status(self: Any, logical_key: str) -> dict[str, Any]:
    row = self.conn.execute(
        "SELECT * FROM idempotency WHERE logical_key=?", (logical_key,)
    ).fetchone()
    if not row:
        raise NotFound(logical_key)
    return dict(row)


TaskKernel.claim = _claim_with_lease_context
TaskKernel.claim_next = _claim_next_with_lease_context
TaskKernel.idempotency_claim = _idempotency_claim_fenced
TaskKernel.idempotency_complete = _idempotency_complete_fenced
TaskKernel.idempotency_status = _idempotency_status

# The implementation may live in a part module, but the public class lived at
# ``scp.task_kernel.TaskKernel`` before the split. Preserve that identity for
# introspection and pickle/import compatibility.
TaskKernel.__module__ = __name__

__all__ = [
    "TaskKernel", "Lease", "RecoveryDecision", "KernelError",
    "InvalidTransition", "StaleLease", "KillSwitchActive",
    "CheckpointCorrupt", "NotFound", "STATES", "TERMINAL",
    "ALLOWED_TRANSITIONS", "now_iso", "stable_hash", "as_json",
]
