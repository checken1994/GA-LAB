from __future__ import annotations

import hashlib
import json
import secrets
import sqlite3
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


STATES = {
    "CREATED", "PLANNING", "READY", "QUEUED", "LEASED",     "RUNNING", "WAITING_TOOL", "VERIFYING", "CHECKPOINTED", "UNKNOWN", "RECOVERING", "RECONCILING",

    "HUMAN_REVIEW", "RETRY_SCHEDULED", "COMPLETED", "FAILED", "CANCELLED",
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
    "WAITING_APPROVAL": {"READY", "CANCELLED"},
    "COMPLETED": set(), "FAILED": set(), "CANCELLED": set(),
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
        raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return "sha256:" + hashlib.sha256(raw).hexdigest()


class TaskKernel:
    """Small durable kernel. The journal is authoritative; tasks is a rebuildable projection."""

    def __init__(self, db_path: str | Path):
        self.db_path = str(db_path)
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.db_path, timeout=10, isolation_level=None, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA foreign_keys=ON")
        self.conn.execute("PRAGMA busy_timeout=10000")
        self._schema()

    def close(self) -> None:
        self.conn.close()

    def _schema(self) -> None:
        self.conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS control (
                id INTEGER PRIMARY KEY CHECK (id=1),
                global_kill INTEGER NOT NULL DEFAULT 0,
                global_kill_epoch INTEGER NOT NULL DEFAULT 0
            );
            INSERT OR IGNORE INTO control(id) VALUES(1);
            CREATE TABLE IF NOT EXISTS tasks (
                task_id TEXT PRIMARY KEY,
                owner TEXT NOT NULL,
                goal TEXT NOT NULL,
                risk_tier TEXT NOT NULL,
                deadline_ms INTEGER NOT NULL,
                max_attempts INTEGER NOT NULL,
                input_hash TEXT NOT NULL,
                state TEXT NOT NULL,
                version INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS events (
                event_id TEXT PRIMARY KEY,
                task_id TEXT NOT NULL,
                seq INTEGER NOT NULL,
                type TEXT NOT NULL,
                from_state TEXT,
                to_state TEXT,
                actor TEXT NOT NULL,
                reason TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                policy_hash TEXT,
                prev_event_hash TEXT,
                event_hash TEXT NOT NULL,
                created_at TEXT NOT NULL,
                UNIQUE(task_id, seq)
            );
            CREATE TABLE IF NOT EXISTS leases (
                lease_id TEXT PRIMARY KEY,
                task_id TEXT NOT NULL,
                attempt_id TEXT NOT NULL,
                worker_id TEXT NOT NULL,
                issued_at REAL NOT NULL,
                expires_at REAL NOT NULL,
                heartbeat_at REAL NOT NULL,
                fencing_token INTEGER NOT NULL,
                global_kill_epoch INTEGER NOT NULL,
                released INTEGER NOT NULL DEFAULT 0
            );
            CREATE INDEX IF NOT EXISTS idx_leases_task ON leases(task_id, fencing_token);
            CREATE TABLE IF NOT EXISTS checkpoints (
                checkpoint_id TEXT PRIMARY KEY,
                task_id TEXT NOT NULL,
                attempt_id TEXT NOT NULL,
                step_id TEXT NOT NULL,
                state TEXT NOT NULL,
                planned_action_hash TEXT NOT NULL,
                capability_epoch INTEGER NOT NULL,
                idempotency_key TEXT NOT NULL,
                pre_observation_ref TEXT,
                post_observation_ref TEXT,
                tool_result_json TEXT,
                verifier_verdict TEXT,
                payload_hash TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS idempotency (
                logical_key TEXT PRIMARY KEY,
                task_id TEXT NOT NULL,
                step_id TEXT NOT NULL,
                action_type TEXT NOT NULL,
                resource_identity TEXT NOT NULL,
                status TEXT NOT NULL,
                result_ref TEXT,
                created_at TEXT NOT NULL
            );
            """
        )

    def _begin(self) -> None:
        self.conn.execute("BEGIN IMMEDIATE")

    def _control(self) -> sqlite3.Row:
        return self.conn.execute("SELECT * FROM control WHERE id=1").fetchone()

    def _task(self, task_id: str) -> sqlite3.Row:
        row = self.conn.execute("SELECT * FROM tasks WHERE task_id=?", (task_id,)).fetchone()
        if not row:
            raise NotFound(task_id)
        return row

    def _append_event(self, task_id: str, event_type: str, from_state: str | None, to_state: str | None,
                      actor: str, reason: str, payload: dict[str, Any] | None = None,
                      policy_hash: str | None = None, event_id: str | None = None) -> dict[str, Any]:
        event_id = event_id or "evt_" + secrets.token_hex(12)
        payload = payload or {}
        previous = self.conn.execute(
            "SELECT seq,event_hash FROM events WHERE task_id=? ORDER BY seq DESC LIMIT 1", (task_id,)
        ).fetchone()
        seq = int(previous["seq"] + 1) if previous else 1
        prev_hash = previous["event_hash"] if previous else None
        body = {
            "event_id": event_id, "task_id": task_id, "seq": seq, "type": event_type,
            "from_state": from_state, "to_state": to_state, "actor": actor, "reason": reason,
            "payload": payload, "policy_hash": policy_hash, "prev_event_hash": prev_hash,
        }
        event_hash = stable_hash(body)
        row = {
            "event_id": event_id, "task_id": task_id, "seq": seq, "type": event_type,
            "from_state": from_state, "to_state": to_state, "actor": actor, "reason": reason,
            "payload_json": json.dumps(payload, ensure_ascii=False, sort_keys=True),
            "policy_hash": policy_hash, "prev_event_hash": prev_hash,
            "event_hash": event_hash, "created_at": now_iso(),
        }
        try:
            self.conn.execute(
                "INSERT INTO events(event_id,task_id,seq,type,from_state,to_state,actor,reason,payload_json,policy_hash,prev_event_hash,event_hash,created_at) VALUES (:event_id,:task_id,:seq,:type,:from_state,:to_state,:actor,:reason,:payload_json,:policy_hash,:prev_event_hash,:event_hash,:created_at)", row
            )
        except sqlite3.IntegrityError:
            existing = self.conn.execute("SELECT * FROM events WHERE event_id=?", (event_id,)).fetchone()
            if existing:
                return dict(existing)
            raise
        return row

    def create_task(self, task_id: str, owner: str, goal: str, risk_tier: str = "R0",
                    deadline_ms: int = 120000, max_attempts: int = 3, input_hash: str | None = None) -> dict[str, Any]:
        if not task_id or not owner or not goal or deadline_ms <= 0 or max_attempts <= 0:
            raise KernelError("invalid task contract")
        if risk_tier not in {"R0", "R1", "R2", "R3"}:
            raise KernelError("invalid risk tier")
        created = now_iso(); input_hash = input_hash or stable_hash({"goal": goal})
        self._begin()
        try:
            self.conn.execute(
                "INSERT INTO tasks(task_id,owner,goal,risk_tier,deadline_ms,max_attempts,input_hash,state,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
                (task_id, owner, goal, risk_tier, deadline_ms, max_attempts, input_hash, "CREATED", created, created),
            )
            self._append_event(task_id, "TASK_CREATED", None, "CREATED", "kernel", "task_created", {"input_hash": input_hash})
            self.conn.execute("COMMIT")
        except Exception:
            self.conn.execute("ROLLBACK")
            raise
        return self.get_task(task_id)

    def transition(self, task_id: str, to_state: str, actor: str = "kernel", reason: str = "",
                   payload: dict[str, Any] | None = None, event_id: str | None = None) -> dict[str, Any]:
        if to_state not in STATES and to_state != "WAITING_APPROVAL":
            raise InvalidTransition(f"unknown target state {to_state}")
        self._begin()
        try:
            if event_id:
                existing = self.conn.execute("SELECT * FROM events WHERE event_id=?", (event_id,)).fetchone()
                if existing:
                    if existing["task_id"] != task_id or existing["to_state"] != to_state:
                        raise InvalidTransition("event_id reused for a different transition")
                    self.conn.execute("COMMIT")
                    return self.get_task(task_id)
            task = self._task(task_id); old = task["state"]
            if to_state not in ALLOWED_TRANSITIONS.get(old, set()):
                raise InvalidTransition(f"{old}->{to_state}")
            if old in TERMINAL:
                raise InvalidTransition("terminal task is immutable")
            self.conn.execute("UPDATE tasks SET state=?,version=version+1,updated_at=? WHERE task_id=?", (to_state, now_iso(), task_id))
            self._append_event(task_id, "STATE_TRANSITION", old, to_state, actor, reason or f"{old}->{to_state}", payload, event_id=event_id)
            self.conn.execute("COMMIT")
        except Exception:
            self.conn.execute("ROLLBACK")
            raise
        return self.get_task(task_id)

    def _assert_not_killed(self) -> sqlite3.Row:
        control = self._control()
        if control["global_kill"]:
            raise KillSwitchActive("global kill switch active")
        return control

    def claim(self, task_id: str, worker_id: str, attempt_id: str | None = None, ttl_seconds: float = 30.0) -> Lease:
        if ttl_seconds <= 0 or not worker_id:
            raise KernelError("invalid lease contract")
        self._begin()
        try:
            control = self._assert_not_killed(); task = self._task(task_id)
            created_at = datetime.fromisoformat(task["created_at"]).timestamp()
            if time.time() >= created_at + (int(task["deadline_ms"]) / 1000.0):
                raise KernelError("task deadline exceeded")
            if task["state"] != "QUEUED":
                raise KernelError(f"task not queueable: {task['state']}")
            attempt_id = attempt_id or "attempt_" + secrets.token_hex(8)
            old = self.conn.execute("SELECT COALESCE(MAX(fencing_token),0) AS n FROM leases WHERE task_id=?", (task_id,)).fetchone()["n"]
            token = int(old) + 1; now = time.time(); lease_id = "lease_" + secrets.token_hex(12)
            self.conn.execute(
                "INSERT INTO leases(lease_id,task_id,attempt_id,worker_id,issued_at,expires_at,heartbeat_at,fencing_token,global_kill_epoch) VALUES (?,?,?,?,?,?,?,?,?)",
                (lease_id, task_id, attempt_id, worker_id, now, now + ttl_seconds, now, token, control["global_kill_epoch"]),
            )
            self.conn.execute("UPDATE tasks SET state='LEASED',version=version+1,updated_at=? WHERE task_id=?", (now_iso(), task_id))
            self._append_event(task_id, "LEASE_GRANTED", "QUEUED", "LEASED", "kernel", "lease_granted", {"lease_id": lease_id, "fencing_token": token, "worker_id": worker_id})
            self.conn.execute("COMMIT")
            return Lease(lease_id, task_id, attempt_id, worker_id, now + ttl_seconds, token, control["global_kill_epoch"])
        except Exception:
            self.conn.execute("ROLLBACK")
            raise

    def _lease(self, lease_id: str) -> sqlite3.Row:
        row = self.conn.execute("SELECT * FROM leases WHERE lease_id=?", (lease_id,)).fetchone()
        if not row:
            raise StaleLease(lease_id)
        return row

    def _assert_lease(self, lease_id: str, task_id: str) -> sqlite3.Row:
        lease = self._lease(lease_id); control = self._control(); now = time.time()
        if lease["task_id"] != task_id or lease["released"] or lease["expires_at"] <= now or lease["global_kill_epoch"] != control["global_kill_epoch"] or control["global_kill"]:
            raise StaleLease(lease_id)
        latest = self.conn.execute(
            "SELECT COALESCE(MAX(fencing_token), 0) AS n FROM leases WHERE task_id=?",
            (task_id,),
        ).fetchone()["n"]
        if int(lease["fencing_token"]) != int(latest):
            raise StaleLease(lease_id)
        return lease
    def start(self, task_id: str, lease_id: str) -> dict[str, Any]:
        self._begin()
        try:
            self._assert_lease(lease_id, task_id); task = self._task(task_id)
            if task["state"] != "LEASED": raise InvalidTransition(f"{task['state']}->RUNNING")
            self.conn.execute("UPDATE tasks SET state='RUNNING',version=version+1,updated_at=? WHERE task_id=?", (now_iso(), task_id))
            self._append_event(task_id, "WORKER_STARTED", "LEASED", "RUNNING", "worker", "lease_valid", {"lease_id": lease_id})
            self.conn.execute("COMMIT")
        except Exception:
            self.conn.execute("ROLLBACK"); raise
        return self.get_task(task_id)

    def heartbeat(self, task_id: str, lease_id: str, extend_seconds: float = 30.0) -> Lease:
        self._begin()
        try:
            lease = self._assert_lease(lease_id, task_id); now = time.time(); expires = now + extend_seconds
            self.conn.execute("UPDATE leases SET heartbeat_at=?,expires_at=? WHERE lease_id=?", (now, expires, lease_id))
            self.conn.execute("COMMIT")
            return Lease(lease["lease_id"], lease["task_id"], lease["attempt_id"], lease["worker_id"], expires, lease["fencing_token"], lease["global_kill_epoch"])
        except Exception:
            self.conn.execute("ROLLBACK"); raise

    def expire_leases(self, now: float | None = None) -> list[str]:
        now = now or time.time(); expired=[]; self._begin()
        try:
            for lease in self.conn.execute("SELECT * FROM leases WHERE released=0 AND expires_at<=?", (now,)).fetchall():
                expired.append(lease["lease_id"])
                task = self._task(lease["task_id"])
                if task["state"] in {"LEASED", "RUNNING", "WAITING_TOOL"}:
                    old=task["state"]; self.conn.execute("UPDATE tasks SET state='RECOVERING',version=version+1,updated_at=? WHERE task_id=?", (now_iso(), task["task_id"]))
                    self._append_event(task["task_id"], "LEASE_EXPIRED", old, "RECOVERING", "kernel", "heartbeat_expired", {"lease_id": lease["lease_id"]})
                self.conn.execute("UPDATE leases SET released=1 WHERE lease_id=?", (lease["lease_id"],))
            self.conn.execute("COMMIT")
            return expired
        except Exception:
            self.conn.execute("ROLLBACK"); raise

    def release(self, task_id: str, lease_id: str) -> None:
        self._begin()
        try:
            lease=self._assert_lease(lease_id,task_id);self.conn.execute("UPDATE leases SET released=1 WHERE lease_id=?",(lease_id,));self._append_event(task_id,"LEASE_RELEASED",None,None,"kernel","worker_release",{"lease_id":lease_id});self.conn.execute("COMMIT")
        except Exception:
            self.conn.execute("ROLLBACK");raise

    def checkpoint(self, task_id: str, lease_id: str, step_id: str, state: str, planned_action: Any,
                   capability_epoch: int, idempotency_key: str, pre_observation_ref: str | None = None,
                   post_observation_ref: str | None = None, tool_result: Any | None = None,
                   verifier_verdict: str | None = None) -> str:
        if state not in STATES: raise CheckpointCorrupt("invalid checkpoint state")
        self._begin()
        try:
            lease=self._assert_lease(lease_id,task_id); payload={"task_id":task_id,"attempt_id":lease["attempt_id"],"step_id":step_id,"state":state,"planned_action":planned_action,"capability_epoch":capability_epoch,"idempotency_key":idempotency_key,"pre_observation_ref":pre_observation_ref,"post_observation_ref":post_observation_ref,"tool_result":tool_result,"verifier_verdict":verifier_verdict};cp_id="cp_"+secrets.token_hex(10);payload_hash=stable_hash(payload)
            self.conn.execute("INSERT INTO checkpoints(checkpoint_id,task_id,attempt_id,step_id,state,planned_action_hash,capability_epoch,idempotency_key,pre_observation_ref,post_observation_ref,tool_result_json,verifier_verdict,payload_hash,created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",(cp_id,task_id,lease["attempt_id"],step_id,state,stable_hash(planned_action),capability_epoch,idempotency_key,pre_observation_ref,post_observation_ref,json.dumps(tool_result,ensure_ascii=False,sort_keys=True) if tool_result is not None else None,verifier_verdict,payload_hash,now_iso()))
            self._append_event(task_id,"CHECKPOINT_WRITTEN",None,state,"kernel","checkpoint_written",{"checkpoint_id":cp_id,"payload_hash":payload_hash,"idempotency_key":idempotency_key})
            self.conn.execute("COMMIT");return cp_id
        except Exception:
            self.conn.execute("ROLLBACK");raise

    def validate_checkpoint(self, checkpoint_id: str, planned_action: Any) -> dict[str, Any]:
        row=self.conn.execute("SELECT * FROM checkpoints WHERE checkpoint_id=?",(checkpoint_id,)).fetchone()
        if not row: raise CheckpointCorrupt(checkpoint_id)
        if row["planned_action_hash"] != stable_hash(planned_action): raise CheckpointCorrupt("planned action hash mismatch")
        return dict(row)

    def idempotency_claim(self, task_id: str, step_id: str, action_type: str, resource_identity: str) -> tuple[str, bool]:
        logical_key=stable_hash({"task_id":task_id,"step_id":step_id,"action_type":action_type,"resource_identity":resource_identity})
        self._begin()
        try:
            row=self.conn.execute("SELECT * FROM idempotency WHERE logical_key=?",(logical_key,)).fetchone()
            if row: self.conn.execute("COMMIT");return logical_key,False
            self.conn.execute("INSERT INTO idempotency(logical_key,task_id,step_id,action_type,resource_identity,status,created_at) VALUES (?,?,?,?,?,?,?)",(logical_key,task_id,step_id,action_type,resource_identity,"CLAIMED",now_iso()));self.conn.execute("COMMIT");return logical_key,True
        except Exception:
            self.conn.execute("ROLLBACK");raise

    def idempotency_complete(self, logical_key: str, result_ref: str) -> None:
        self.conn.execute("UPDATE idempotency SET status='COMPLETED',result_ref=? WHERE logical_key=?",(result_ref,logical_key))

    def commit_verification_result(self, task_id: str, lease_id: str, verification_result: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(verification_result, dict) or verification_result.get("verdict") != "VERIFIED":
            raise KernelError("completion requires verifier verdict VERIFIED")
        if not verification_result.get("verifier_id") or not verification_result.get("evidence_ref"):
            raise KernelError("completion requires verifier identity and evidence")
        return self.commit_completed(task_id, lease_id, "VERIFIED", str(verification_result["evidence_ref"]))

    def commit_completed(self, task_id: str, lease_id: str, verifier_verdict: str, evidence_ref: str) -> dict[str, Any]:
        if verifier_verdict != "VERIFIED" or not evidence_ref: raise KernelError("completion requires independent VERIFIED verdict and evidence")
        self._begin()
        try:
            self._assert_lease(lease_id,task_id);task=self._task(task_id)
            if task["state"] not in {"VERIFYING","RUNNING"}: raise InvalidTransition(f"{task['state']}->COMPLETED")
            old=task["state"];self.conn.execute("UPDATE tasks SET state='COMPLETED',version=version+1,updated_at=? WHERE task_id=?",(now_iso(),task_id));self._append_event(task_id,"TASK_COMPLETED",old,"COMPLETED","verifier","postcondition_verified",{"evidence_ref":evidence_ref,"verifier_verdict":verifier_verdict,"lease_id":lease_id});self.conn.execute("UPDATE leases SET released=1 WHERE lease_id=?",(lease_id,));self.conn.execute("COMMIT");return self.get_task(task_id)
        except Exception:
            self.conn.execute("ROLLBACK");raise

    def set_global_kill(self, active: bool, actor: str = "operator") -> int:
        self._begin()
        try:
            c=self._control();epoch=int(c["global_kill_epoch"])+(1 if active else 0);self.conn.execute("UPDATE control SET global_kill=?,global_kill_epoch=? WHERE id=1",(1 if active else 0,epoch));self._append_event("__global__","GLOBAL_KILL_ON" if active else "GLOBAL_KILL_OFF",None,None,actor,"operator_toggle",{"epoch":epoch});self.conn.execute("COMMIT");return epoch
        except Exception:
            self.conn.execute("ROLLBACK");raise

    def set_task_kill(self, task_id: str, actor: str = "operator") -> dict[str, Any]:
        self._begin()
        try:
            task=self._task(task_id)
            if task["state"] in TERMINAL:
                raise InvalidTransition("terminal task is immutable")
            self.conn.execute("UPDATE tasks SET state='CANCELLED',version=version+1,updated_at=? WHERE task_id=?",(now_iso(),task_id));self.conn.execute("UPDATE leases SET released=1 WHERE task_id=?",(task_id,));self._append_event(task_id,"TASK_KILLED",task["state"],"CANCELLED",actor,"task_kill",{});self.conn.execute("COMMIT");return self.get_task(task_id)
        except Exception:
            self.conn.execute("ROLLBACK");raise

    def get_task(self, task_id: str) -> dict[str, Any]: return dict(self._task(task_id))
    def get_events(self, task_id: str) -> list[dict[str, Any]]: return [dict(x) for x in self.conn.execute("SELECT * FROM events WHERE task_id=? ORDER BY seq",(task_id,)).fetchall()]
    def get_checkpoint(self, checkpoint_id: str) -> dict[str, Any]:
        row=self.conn.execute("SELECT * FROM checkpoints WHERE checkpoint_id=?",(checkpoint_id,)).fetchone()
        if not row: raise CheckpointCorrupt(checkpoint_id)
        return dict(row)
    def verify_journal(self, task_id: str) -> dict[str, Any]:
        events=self.get_events(task_id);prev=None;errors=[]
        for i,e in enumerate(events,1):
            if e["seq"]!=i: errors.append(f"sequence:{e['seq']} expected {i}")
            if e["prev_event_hash"]!=prev: errors.append(f"prev_hash:{e['seq']}")
            body={"event_id":e["event_id"],"task_id":e["task_id"],"seq":e["seq"],"type":e["type"],"from_state":e["from_state"],"to_state":e["to_state"],"actor":e["actor"],"reason":e["reason"],"payload":json.loads(e["payload_json"]),"policy_hash":e["policy_hash"],"prev_event_hash":e["prev_event_hash"]}
            if stable_hash(body)!=e["event_hash"]: errors.append(f"event_hash:{e['seq']}")
            prev=e["event_hash"]
        return {"task_id":task_id,"event_count":len(events),"hash_chain_valid":not errors,"errors":errors}

    def rebuild_projection(self, task_id: str) -> dict[str, Any]:
        events=self.get_events(task_id)
        if not events: raise NotFound(task_id)
        state=events[0]["to_state"]
        for e in events[1:]:
            if e["to_state"]: state=e["to_state"]
        self.conn.execute("UPDATE tasks SET state=?,updated_at=? WHERE task_id=?",(state,now_iso(),task_id));return self.get_task(task_id)

    @staticmethod
    def recovery_decision(reason: str, action_dispatched: bool = False, side_effect_risk: str = "R0") -> RecoveryDecision:
        if action_dispatched or reason in {"TOOL_UNKNOWN_STATE", "LOST_RESPONSE", "WORKER_CRASH_AFTER_SUBMIT"}:
            return RecoveryDecision("RECONCILE","ACTION_DISPATCHED_WITHOUT_RESULT",False,("provider_request_status","read_only_state"),"RECONCILING","human_review_if_unknown")
        if reason in {"PROVIDER_TIMEOUT", "DEPENDENCY_NOT_READY", "TRANSIENT_NETWORK"} and side_effect_risk in {"R0","R1"}:
            return RecoveryDecision("RETRY","TRANSIENT_FAILURE",True,(),"QUEUED","bounded_backoff")
        if reason in {"POLICY_DENIED", "INVALID_CAPABILITY", "CHECKPOINT_CORRUPT"}:
            return RecoveryDecision("STOP","NON_RETRYABLE_POLICY_OR_INTEGRITY_FAILURE",False,(),"FAILED","none")
        return RecoveryDecision("REVIEW","INSUFFICIENT_STATE_EVIDENCE",False,("last_checkpoint","event_journal"),"HUMAN_REVIEW","human_required")


def as_json(value: Any) -> str:
    return json.dumps(asdict(value) if hasattr(value, "__dataclass_fields__") else value, ensure_ascii=False, sort_keys=True)
