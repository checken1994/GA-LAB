# Auto-extracted from task_kernel.py
from __future__ import annotations
import hashlib
import json
import re
import secrets
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from scp.kernel_storage import KernelStorage, StorageIntegrityError, make_storage

class TaskKernel:
    """Small durable kernel. The journal is authoritative; tasks is a rebuildable projection.

    [CHAIN-AUDIT FIX 2026-08-29] Per-thread connections thay vì 1 shared
    connection: thực nghiệm 40-100 luồng đồng thời cho thấy shared connection
    làm SELECT đọc "nhìn thấy" snapshot cũ (row vừa commit vẫn invisible) →
    NotFound → ~8-16% task chết dưới tải. Mỗi thread có connection riêng
    (WAL sinh tồn đa connection), transaction không còn dính chéo thread.
    """

    def __init__(self, db_path: str | Path | None=None, *, storage: KernelStorage | None=None) -> None:
        """Initialise the kernel.

        Backward-compat: TaskKernel(db_path) still works.
        DI-ready: TaskKernel(storage=my_storage) injects a custom backend.
        Future: when TaskKernel is fully decoupled, the db_path arg will be removed.
        """
        if storage is not None:
            self._storage = storage
            self.db_path = getattr(storage, 'db_path', str(db_path or ''))
        else:
            if db_path is None:
                raise ValueError('Either db_path or storage= must be provided')
            self._storage = make_storage(db_path)
            self.db_path = str(db_path)
        self._schema()

    @property
    def conn(self) -> KernelStorage:
        """Backward-compatible query facade backed by the injected storage."""
        return self._storage

    def close(self) -> None:
        self._storage.close()

    def _schema(self) -> None:
        self.conn.executescript('\n            CREATE TABLE IF NOT EXISTS control (\n                id INTEGER PRIMARY KEY CHECK (id=1),\n                global_kill INTEGER NOT NULL DEFAULT 0,\n                global_kill_epoch INTEGER NOT NULL DEFAULT 0\n            );\n            INSERT OR IGNORE INTO control(id) VALUES(1);\n            CREATE TABLE IF NOT EXISTS tasks (\n                task_id TEXT PRIMARY KEY,\n                owner TEXT NOT NULL,\n                goal TEXT NOT NULL,\n                risk_tier TEXT NOT NULL,\n                deadline_ms INTEGER NOT NULL,\n                max_attempts INTEGER NOT NULL,\n                input_hash TEXT NOT NULL,\n                priority INTEGER NOT NULL DEFAULT 5,\n                state TEXT NOT NULL,\n                version INTEGER NOT NULL DEFAULT 1,\n                created_at TEXT NOT NULL,\n                updated_at TEXT NOT NULL\n            );\n            CREATE TABLE IF NOT EXISTS events (\n                event_id TEXT PRIMARY KEY,\n                task_id TEXT NOT NULL,\n                seq INTEGER NOT NULL,\n                type TEXT NOT NULL,\n                from_state TEXT,\n                to_state TEXT,\n                actor TEXT NOT NULL,\n                reason TEXT NOT NULL,\n                payload_json TEXT NOT NULL,\n                policy_hash TEXT,\n                prev_event_hash TEXT,\n                event_hash TEXT NOT NULL,\n                created_at TEXT NOT NULL,\n                UNIQUE(task_id, seq)\n            );\n            CREATE TABLE IF NOT EXISTS leases (\n                lease_id TEXT PRIMARY KEY,\n                task_id TEXT NOT NULL,\n                attempt_id TEXT NOT NULL,\n                worker_id TEXT NOT NULL,\n                issued_at REAL NOT NULL,\n                expires_at REAL NOT NULL,\n                heartbeat_at REAL NOT NULL,\n                fencing_token INTEGER NOT NULL,\n                global_kill_epoch INTEGER NOT NULL,\n                released INTEGER NOT NULL DEFAULT 0\n            );\n            CREATE INDEX IF NOT EXISTS idx_leases_task ON leases(task_id, fencing_token);\n            CREATE TABLE IF NOT EXISTS checkpoints (\n                checkpoint_id TEXT PRIMARY KEY,\n                task_id TEXT NOT NULL,\n                attempt_id TEXT NOT NULL,\n                step_id TEXT NOT NULL,\n                state TEXT NOT NULL,\n                planned_action_hash TEXT NOT NULL,\n                capability_epoch INTEGER NOT NULL,\n                idempotency_key TEXT NOT NULL,\n                pre_observation_ref TEXT,\n                post_observation_ref TEXT,\n                tool_result_json TEXT,\n                verifier_verdict TEXT,\n                payload_hash TEXT NOT NULL,\n                created_at TEXT NOT NULL\n            );\n            CREATE TABLE IF NOT EXISTS idempotency (\n                logical_key TEXT PRIMARY KEY,\n                task_id TEXT NOT NULL,\n                step_id TEXT NOT NULL,\n                action_type TEXT NOT NULL,\n                resource_identity TEXT NOT NULL,\n                status TEXT NOT NULL,\n                result_ref TEXT,\n                created_at TEXT NOT NULL\n            );\n            ')
        task_columns = {row['name'] for row in self.conn.execute('PRAGMA table_info(tasks)').fetchall()}
        if 'priority' not in task_columns:
            self.conn.execute('ALTER TABLE tasks ADD COLUMN priority INTEGER NOT NULL DEFAULT 5')
        self.conn.execute('\n            CREATE TABLE IF NOT EXISTS queue_accounts (\n                owner TEXT PRIMARY KEY,\n                active INTEGER NOT NULL DEFAULT 0,\n                dispatch_count INTEGER NOT NULL DEFAULT 0,\n                last_dispatch_at REAL NOT NULL DEFAULT 0\n            )\n            ')

    def _begin(self) -> None:
        """Acquire the write slot + BEGIN IMMEDIATE, với bounded retry trên
        'database is locked' (multi-connection WAL contention khi hệ thống
        đang chạy phụ trợ khác cùng lúc). Đã hết retry → raise, fail-closed."""
        self._storage.begin()

    def _commit(self) -> None:
        self._storage.commit()

    def _rollback(self) -> None:
        self._storage.rollback()

    def _control(self) -> Any:
        return self.conn.execute('SELECT * FROM control WHERE id=1').fetchone()

    def _task(self, task_id: str) -> Any:
        row = self.conn.execute('SELECT * FROM tasks WHERE task_id=?', (task_id,)).fetchone()
        if not row:
            raise NotFound(task_id)
        return row

    def _append_event(self, task_id: str, event_type: str, from_state: str | None, to_state: str | None, actor: str, reason: str, payload: dict[str, Any] | None=None, policy_hash: str | None=None, event_id: str | None=None) -> dict[str, Any]:
        event_id = event_id or 'evt_' + secrets.token_hex(12)
        payload = payload or {}
        previous = self.conn.execute('SELECT seq,event_hash FROM events WHERE task_id=? ORDER BY seq DESC LIMIT 1', (task_id,)).fetchone()
        seq = int(previous['seq'] + 1) if previous else 1
        prev_hash = previous['event_hash'] if previous else None
        body = {'event_id': event_id, 'task_id': task_id, 'seq': seq, 'type': event_type, 'from_state': from_state, 'to_state': to_state, 'actor': actor, 'reason': reason, 'payload': payload, 'policy_hash': policy_hash, 'prev_event_hash': prev_hash}
        event_hash = stable_hash(body)
        row = {'event_id': event_id, 'task_id': task_id, 'seq': seq, 'type': event_type, 'from_state': from_state, 'to_state': to_state, 'actor': actor, 'reason': reason, 'payload_json': json.dumps(payload, ensure_ascii=False, sort_keys=True), 'policy_hash': policy_hash, 'prev_event_hash': prev_hash, 'event_hash': event_hash, 'created_at': now_iso()}
        try:
            self.conn.execute('INSERT INTO events(event_id,task_id,seq,type,from_state,to_state,actor,reason,payload_json,policy_hash,prev_event_hash,event_hash,created_at) VALUES (:event_id,:task_id,:seq,:type,:from_state,:to_state,:actor,:reason,:payload_json,:policy_hash,:prev_event_hash,:event_hash,:created_at)', row)
        except StorageIntegrityError:
            existing = self.conn.execute('SELECT * FROM events WHERE event_id=?', (event_id,)).fetchone()
            if existing:
                return dict(existing)
            raise
        return row

    def create_task(self, task_id: str, owner: str, goal: str, risk_tier: str='R0', deadline_ms: int=120000, max_attempts: int=3, input_hash: str | None=None, priority: int=5) -> dict[str, Any]:
        if not task_id or not owner or (not goal) or (deadline_ms <= 0) or (max_attempts <= 0):
            raise KernelError('invalid task contract')
        if not isinstance(priority, int) or not 0 <= priority <= 100:
            raise KernelError('invalid task priority')
        if risk_tier not in {'R0', 'R1', 'R2', 'R3'}:
            raise KernelError('invalid risk tier')
        created = now_iso()
        input_hash = input_hash or stable_hash({'goal': goal})
        self._begin()
        try:
            self.conn.execute('INSERT INTO tasks(task_id,owner,goal,risk_tier,deadline_ms,max_attempts,input_hash,priority,state,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)', (task_id, owner, goal, risk_tier, deadline_ms, max_attempts, input_hash, priority, 'CREATED', created, created))
            self._append_event(task_id, 'TASK_CREATED', None, 'CREATED', 'kernel', 'task_created', {'input_hash': input_hash})
            self._commit()
        except Exception:
            self._rollback()
            raise
        return self.get_task(task_id)

    def transition(self, task_id: str, to_state: str, actor: str='kernel', reason: str='', payload: dict[str, Any] | None=None, event_id: str | None=None) -> dict[str, Any]:
        if to_state not in STATES and to_state != 'WAITING_APPROVAL':
            raise InvalidTransition(f'unknown target state {to_state}')
        self._begin()
        try:
            if event_id:
                existing = self.conn.execute('SELECT * FROM events WHERE event_id=?', (event_id,)).fetchone()
                if existing:
                    if existing['task_id'] != task_id or existing['to_state'] != to_state:
                        raise InvalidTransition('event_id reused for a different transition')
                    self._commit()
                    return self.get_task(task_id)
            task = self._task(task_id)
            old = task['state']
            if to_state not in ALLOWED_TRANSITIONS.get(old, set()):
                raise InvalidTransition(f'{old}->{to_state}')
            if old in TERMINAL:
                raise InvalidTransition('terminal task is immutable')
            if to_state in ('COMPLETED', 'FAILED', 'RUNNING', 'CHECKPOINTED', 'VERIFYING'):
                try:
                    from scp.meta.why_gate import get_why_gate, WhyDecision
                    why_res = get_why_gate().gate(action_type='kernel_transition', action_desc=f'Transition {task_id} from {old} to {to_state} by {actor}', context=reason, llm_enabled=False)
                    if why_res.decision == WhyDecision.REJECT:
                        raise InvalidTransition(f'WHY Gate REJECTED this kernel transition: {why_res.falsification_reason}')
                except InvalidTransition:
                    raise
                except Exception as why_err:
                    raise InvalidTransition(f'WHY Gate crashed, fail-closed: {why_err}')
            self.conn.execute('UPDATE tasks SET state=?,version=version+1,updated_at=? WHERE task_id=?', (to_state, now_iso(), task_id))
            self._append_event(task_id, 'STATE_TRANSITION', old, to_state, actor, reason or f'{old}->{to_state}', payload, event_id=event_id)
            self._commit()
        except Exception:
            self._rollback()
            raise
        return self.get_task(task_id)

    def _assert_not_killed(self) -> Any:
        control = self._control()
        if control['global_kill']:
            raise KillSwitchActive('global kill switch active')
        return control

    def claim(self, task_id: str, worker_id: str, attempt_id: str | None=None, ttl_seconds: float=30.0) -> Lease:
        if ttl_seconds <= 0 or not worker_id:
            raise KernelError('invalid lease contract')
        self._begin()
        try:
            control = self._assert_not_killed()
            task = self._task(task_id)
            created_at = datetime.fromisoformat(task['created_at']).timestamp()
            if time.time() >= created_at + int(task['deadline_ms']) / 1000.0:
                raise KernelError('task deadline exceeded')
            if task['state'] != 'QUEUED':
                raise KernelError(f"task not queueable: {task['state']}")
            attempt_id = attempt_id or 'attempt_' + secrets.token_hex(8)
            old = self.conn.execute('SELECT COALESCE(MAX(fencing_token),0) AS n FROM leases WHERE task_id=?', (task_id,)).fetchone()['n']
            token = int(old) + 1
            now = time.time()
            lease_id = 'lease_' + secrets.token_hex(12)
            self.conn.execute('INSERT INTO leases(lease_id,task_id,attempt_id,worker_id,issued_at,expires_at,heartbeat_at,fencing_token,global_kill_epoch) VALUES (?,?,?,?,?,?,?,?,?)', (lease_id, task_id, attempt_id, worker_id, now, now + ttl_seconds, now, token, control['global_kill_epoch']))
            self.conn.execute("UPDATE tasks SET state='LEASED',version=version+1,updated_at=? WHERE task_id=?", (now_iso(), task_id))
            self.conn.execute('INSERT INTO queue_accounts(owner,active,dispatch_count,last_dispatch_at) VALUES (?,?,?,?) ON CONFLICT(owner) DO UPDATE SET active=active+1,dispatch_count=dispatch_count+1,last_dispatch_at=excluded.last_dispatch_at', (task['owner'], 1, 1, now))
            self._append_event(task_id, 'LEASE_GRANTED', 'QUEUED', 'LEASED', 'kernel', 'lease_granted', {'lease_id': lease_id, 'fencing_token': token, 'worker_id': worker_id})
            self._commit()
            return Lease(lease_id, task_id, attempt_id, worker_id, now + ttl_seconds, token, control['global_kill_epoch'])
        except Exception:
            self._rollback()
            raise

    def claim_next(self, worker_id: str, max_active_per_owner: int=1, ttl_seconds: float=30.0, now: float | None=None) -> Lease | None:
        """Claim one queued task using priority + owner fair-share + deadline guards."""
        if not worker_id or max_active_per_owner <= 0 or ttl_seconds <= 0:
            raise KernelError('invalid queue claim contract')
        now = time.time() if now is None else float(now)
        self._begin()
        try:
            control = self._assert_not_killed()
            candidates = self.conn.execute("\n                SELECT t.*, COALESCE(a.active,0) AS owner_active,\n                       COALESCE(a.dispatch_count,0) AS owner_dispatch_count,\n                       COALESCE(a.last_dispatch_at,0) AS owner_last_dispatch_at\n                FROM tasks t LEFT JOIN queue_accounts a ON a.owner=t.owner\n                WHERE t.state='QUEUED'\n                ORDER BY t.priority ASC, owner_dispatch_count ASC,\n                         owner_last_dispatch_at ASC, t.created_at ASC, t.task_id ASC\n                ").fetchall()
            for task in candidates:
                created_at = datetime.fromisoformat(task['created_at']).timestamp()
                if now >= created_at + int(task['deadline_ms']) / 1000.0:
                    self.conn.execute("UPDATE tasks SET state='FAILED',version=version+1,updated_at=? WHERE task_id=?", (now_iso(), task['task_id']))
                    self._append_event(task['task_id'], 'DEADLINE_EXPIRED', 'QUEUED', 'FAILED', 'kernel', 'queue_deadline_guard', {'deadline_ms': task['deadline_ms']})
                    continue
                if int(task['owner_active']) >= max_active_per_owner:
                    continue
                attempt_id = 'attempt_' + secrets.token_hex(8)
                latest = self.conn.execute('SELECT COALESCE(MAX(fencing_token),0) AS n FROM leases WHERE task_id=?', (task['task_id'],)).fetchone()['n']
                fencing_token = int(latest) + 1
                lease_id = 'lease_' + secrets.token_hex(12)
                expires_at = now + ttl_seconds
                self.conn.execute('INSERT INTO leases(lease_id,task_id,attempt_id,worker_id,issued_at,expires_at,heartbeat_at,fencing_token,global_kill_epoch) VALUES (?,?,?,?,?,?,?,?,?)', (lease_id, task['task_id'], attempt_id, worker_id, now, expires_at, now, fencing_token, control['global_kill_epoch']))
                self.conn.execute("UPDATE tasks SET state='LEASED',version=version+1,updated_at=? WHERE task_id=?", (now_iso(), task['task_id']))
                self.conn.execute('INSERT INTO queue_accounts(owner,active,dispatch_count,last_dispatch_at) VALUES (?,?,?,?) ON CONFLICT(owner) DO UPDATE SET active=active+1,dispatch_count=dispatch_count+1,last_dispatch_at=excluded.last_dispatch_at', (task['owner'], 1, 1, now))
                self._append_event(task['task_id'], 'LEASE_GRANTED', 'QUEUED', 'LEASED', 'kernel', 'fair_queue_claim', {'lease_id': lease_id, 'fencing_token': fencing_token, 'worker_id': worker_id})
                self._commit()
                return Lease(lease_id, task['task_id'], attempt_id, worker_id, expires_at, fencing_token, control['global_kill_epoch'])
            self._commit()
            return None
        except Exception:
            self._rollback()
            raise

    def queue_status(self) -> dict[str, Any]:
        rows = self.conn.execute('SELECT owner,active,dispatch_count,last_dispatch_at FROM queue_accounts ORDER BY owner').fetchall()
        queued = self.conn.execute("SELECT COUNT(*) AS n FROM tasks WHERE state='QUEUED'").fetchone()['n']
        return {'queued': int(queued), 'owners': [dict(row) for row in rows]}

    def _lease(self, lease_id: str) -> Any:
        row = self.conn.execute('SELECT * FROM leases WHERE lease_id=?', (lease_id,)).fetchone()
        if not row:
            raise StaleLease(lease_id)
        return row

    def _assert_lease(self, lease_id: str, task_id: str) -> Any:
        lease = self._lease(lease_id)
        control = self._control()
        now = time.time()
        if lease['task_id'] != task_id or lease['released'] or lease['expires_at'] <= now or (lease['global_kill_epoch'] != control['global_kill_epoch']) or control['global_kill']:
            raise StaleLease(lease_id)
        latest = self.conn.execute('SELECT COALESCE(MAX(fencing_token), 0) AS n FROM leases WHERE task_id=?', (task_id,)).fetchone()['n']
        if int(lease['fencing_token']) != int(latest):
            raise StaleLease(lease_id)
        return lease

    def start(self, task_id: str, lease_id: str) -> dict[str, Any]:
        self._begin()
        try:
            self._assert_lease(lease_id, task_id)
            task = self._task(task_id)
            if task['state'] != 'LEASED':
                raise InvalidTransition(f"{task['state']}->RUNNING")
            self.conn.execute("UPDATE tasks SET state='RUNNING',version=version+1,updated_at=? WHERE task_id=?", (now_iso(), task_id))
            self._append_event(task_id, 'WORKER_STARTED', 'LEASED', 'RUNNING', 'worker', 'lease_valid', {'lease_id': lease_id})
            self._commit()
        except Exception:
            self._rollback()
            raise
        return self.get_task(task_id)

    def heartbeat(self, task_id: str, lease_id: str, extend_seconds: float=30.0) -> Lease:
        self._begin()
        try:
            lease = self._assert_lease(lease_id, task_id)
            now = time.time()
            expires = now + extend_seconds
            self.conn.execute('UPDATE leases SET heartbeat_at=?,expires_at=? WHERE lease_id=?', (now, expires, lease_id))
            self._commit()
            return Lease(lease['lease_id'], lease['task_id'], lease['attempt_id'], lease['worker_id'], expires, lease['fencing_token'], lease['global_kill_epoch'])
        except Exception:
            self._rollback()
            raise

    def expire_leases(self, now: float | None=None) -> list[str]:
        now = now or time.time()
        expired = []
        self._begin()
        try:
            for lease in self.conn.execute('SELECT * FROM leases WHERE released=0 AND expires_at<=?', (now,)).fetchall():
                expired.append(lease['lease_id'])
                task = self._task(lease['task_id'])
                if task['state'] in {'LEASED', 'RUNNING', 'WAITING_TOOL'}:
                    old = task['state']
                    self.conn.execute("UPDATE tasks SET state='RECOVERING',version=version+1,updated_at=? WHERE task_id=?", (now_iso(), task['task_id']))
                    self._append_event(task['task_id'], 'LEASE_EXPIRED', old, 'RECOVERING', 'kernel', 'heartbeat_expired', {'lease_id': lease['lease_id']})
                self.conn.execute('UPDATE leases SET released=1 WHERE lease_id=?', (lease['lease_id'],))
                owner = self._task(lease['task_id'])['owner']
                self.conn.execute('UPDATE queue_accounts SET active=CASE WHEN active>0 THEN active-1 ELSE 0 END WHERE owner=?', (owner,))
            self._commit()
            return expired
        except Exception:
            self._rollback()
            raise

    def release(self, task_id: str, lease_id: str) -> None:
        self._begin()
        try:
            self._assert_lease(lease_id, task_id)
            self.conn.execute('UPDATE leases SET released=1 WHERE lease_id=?', (lease_id,))
            owner = self._task(task_id)['owner']
            self.conn.execute('UPDATE queue_accounts SET active=CASE WHEN active>0 THEN active-1 ELSE 0 END WHERE owner=?', (owner,))
            self._append_event(task_id, 'LEASE_RELEASED', None, None, 'kernel', 'worker_release', {'lease_id': lease_id})
            self._commit()
        except Exception:
            self._rollback()
            raise

    def checkpoint(self, task_id: str, lease_id: str, step_id: str, state: str, planned_action: Any, capability_epoch: int, idempotency_key: str, pre_observation_ref: str | None=None, post_observation_ref: str | None=None, tool_result: Any | None=None, verifier_verdict: str | None=None) -> str:
        if state not in STATES:
            raise CheckpointCorrupt('invalid checkpoint state')
        _assert_checkpoint_safe({'planned_action': planned_action, 'pre_observation_ref': pre_observation_ref, 'post_observation_ref': post_observation_ref, 'tool_result': tool_result})
        self._begin()
        try:
            lease = self._assert_lease(lease_id, task_id)
            payload = {'task_id': task_id, 'attempt_id': lease['attempt_id'], 'step_id': step_id, 'state': state, 'planned_action': planned_action, 'capability_epoch': capability_epoch, 'idempotency_key': idempotency_key, 'pre_observation_ref': pre_observation_ref, 'post_observation_ref': post_observation_ref, 'tool_result': tool_result, 'verifier_verdict': verifier_verdict}
            cp_id = 'cp_' + secrets.token_hex(10)
            payload_hash = stable_hash(payload)
            self.conn.execute('INSERT INTO checkpoints(checkpoint_id,task_id,attempt_id,step_id,state,planned_action_hash,capability_epoch,idempotency_key,pre_observation_ref,post_observation_ref,tool_result_json,verifier_verdict,payload_hash,created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)', (cp_id, task_id, lease['attempt_id'], step_id, state, stable_hash(planned_action), capability_epoch, idempotency_key, pre_observation_ref, post_observation_ref, json.dumps(tool_result, ensure_ascii=False, sort_keys=True) if tool_result is not None else None, verifier_verdict, payload_hash, now_iso()))
            # [P1 FIX 2026-09-05] A checkpoint is a snapshot, not a state
            # transition: to_state must stay NULL. rebuild_projection derives
            # the task state from the last non-null to_state, so a non-NULL
            # value here would project the checkpoint snapshot state (e.g.
            # WAITING_TOOL) after a crash even though the tasks table never
            # transitioned there. The authoritative checkpoint state lives in
            # the checkpoints row ('state' column), not in the projection.
            self._append_event(task_id, 'CHECKPOINT_WRITTEN', None, None, 'kernel', 'checkpoint_written', {'checkpoint_id': cp_id, 'payload_hash': payload_hash, 'idempotency_key': idempotency_key})
            self._commit()
            return cp_id
        except Exception:
            self._rollback()
            raise

    def record_action_dispatched(self, task_id: str, lease_id: str, step_id: str, planned_action: Any, capability_epoch: int, idempotency_key: str, provider_request_id: str, pre_observation_ref: str | None=None) -> dict[str, Any]:
        """Persist the side-effect boundary before a provider response is trusted."""
        if not step_id or not idempotency_key or (not str(provider_request_id).strip()):
            raise KernelError('dispatch requires step, idempotency key and provider request')
        _assert_checkpoint_safe({'planned_action': planned_action, 'pre_observation_ref': pre_observation_ref, 'provider_request_id': provider_request_id})
        self._begin()
        try:
            lease = self._assert_lease(lease_id, task_id)
            task = self._task(task_id)
            if task['state'] not in {'RUNNING', 'WAITING_TOOL'}:
                raise InvalidTransition(f"{task['state']}->UNKNOWN")
            existing = self.conn.execute("SELECT * FROM checkpoints WHERE task_id=? AND attempt_id=? AND step_id=? AND idempotency_key=? AND state='UNKNOWN' ORDER BY created_at DESC LIMIT 1", (task_id, lease['attempt_id'], step_id, idempotency_key)).fetchone()
            if existing:
                existing_result = json.loads(existing['tool_result_json'] or '{}')
                if existing_result.get('provider_request_id') != str(provider_request_id):
                    raise KernelError('idempotency key reused with different provider request')
                self._commit()
                result = dict(existing)
                result['dispatch_status'] = 'UNKNOWN'
                result['provider_request_id'] = existing_result.get('provider_request_id')
                return result
            tool_result = {'dispatch_status': 'UNKNOWN', 'provider_request_id': str(provider_request_id), 'planned_action': planned_action}
            payload = {'task_id': task_id, 'attempt_id': lease['attempt_id'], 'step_id': step_id, 'state': 'UNKNOWN', 'planned_action': planned_action, 'capability_epoch': capability_epoch, 'idempotency_key': idempotency_key, 'pre_observation_ref': pre_observation_ref, 'post_observation_ref': None, 'tool_result': tool_result, 'verifier_verdict': None}
            checkpoint_id = 'cp_' + secrets.token_hex(10)
            payload_hash = stable_hash(payload)
            self.conn.execute('INSERT INTO checkpoints(checkpoint_id,task_id,attempt_id,step_id,state,planned_action_hash,capability_epoch,idempotency_key,pre_observation_ref,post_observation_ref,tool_result_json,verifier_verdict,payload_hash,created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)', (checkpoint_id, task_id, lease['attempt_id'], step_id, 'UNKNOWN', stable_hash(planned_action), capability_epoch, idempotency_key, pre_observation_ref, None, json.dumps(tool_result, ensure_ascii=False, sort_keys=True), None, payload_hash, now_iso()))
            old_state = task['state']
            self.conn.execute("UPDATE tasks SET state='UNKNOWN',version=version+1,updated_at=? WHERE task_id=?", (now_iso(), task_id))
            self._append_event(task_id, 'ACTION_DISPATCHED', old_state, 'UNKNOWN', 'worker', 'side_effect_response_unknown', {'checkpoint_id': checkpoint_id, 'step_id': step_id, 'idempotency_key': idempotency_key, 'provider_request_id': str(provider_request_id)})
            self._commit()
            result = self.get_checkpoint(checkpoint_id)
            result['dispatch_status'] = 'UNKNOWN'
            result['provider_request_id'] = str(provider_request_id)
            return result
        except Exception:
            self._rollback()
            raise

    def _load_reconcile_checkpoint(self, task_id: str, checkpoint_id: str) -> dict[str, Any]:
        checkpoint = self.conn.execute('SELECT * FROM checkpoints WHERE checkpoint_id=?', (checkpoint_id,)).fetchone()
        if not checkpoint or checkpoint['task_id'] != task_id:
            raise KernelError('checkpoint task mismatch')
        if checkpoint['state'] != 'UNKNOWN':
            raise KernelError('reconcile requires UNKNOWN checkpoint')
        try:
            tool_result = json.loads(checkpoint['tool_result_json'] or '{}')
        except (TypeError, ValueError) as exc:
            raise KernelError('checkpoint integrity: invalid tool result JSON') from exc
        if 'planned_action' not in tool_result:
            raise KernelError('checkpoint integrity: planned action unavailable')
        try:
            self.validate_checkpoint(checkpoint_id, tool_result['planned_action'])
        except CheckpointCorrupt as exc:
            raise KernelError(f'checkpoint integrity: {exc}') from exc
        return dict(checkpoint)

    def enter_reconciling(self, task_id: str, checkpoint_id: str, reason: str='reconcile_required') -> dict[str, Any]:
        self._begin()
        try:
            task = self._task(task_id)
            self._load_reconcile_checkpoint(task_id, checkpoint_id)
            if task['state'] == 'RECONCILING':
                self._commit()
                return dict(task)
            if task['state'] != 'UNKNOWN':
                raise InvalidTransition(f"{task['state']}->RECONCILING")
            self.conn.execute("UPDATE tasks SET state='RECONCILING',version=version+1,updated_at=? WHERE task_id=?", (now_iso(), task_id))
            self._append_event(task_id, 'RECONCILE_STARTED', 'UNKNOWN', 'RECONCILING', 'kernel', reason or 'reconcile_required', {'checkpoint_id': checkpoint_id})
            self._commit()
            return self.get_task(task_id)
        except Exception:
            self._rollback()
            raise

    def reconcile_unknown(self, task_id: str, checkpoint_id: str, outcome: str, evidence_ref: str, verifier_id: str | None=None) -> dict[str, Any]:
        """Reconcile an uncertain side effect without auto-completing the task."""
        if outcome not in {'NOT_APPLIED', 'APPLIED', 'UNKNOWN'}:
            raise KernelError('invalid reconcile outcome')
        if not evidence_ref or not str(evidence_ref).strip():
            raise KernelError('reconcile evidence is required')
        if outcome in {'APPLIED', 'UNKNOWN'} and (not verifier_id):
            raise KernelError('reconcile verifier is required')
        _assert_checkpoint_safe({'evidence_ref': evidence_ref, 'verifier_id': verifier_id})
        self._begin()
        try:
            task = self._task(task_id)
            checkpoint = self._load_reconcile_checkpoint(task_id, checkpoint_id)
            if task['state'] != 'RECONCILING':
                raise InvalidTransition(f"{task['state']}->reconcile_outcome")
            idem = self.conn.execute('SELECT * FROM idempotency WHERE logical_key=?', (checkpoint['idempotency_key'],)).fetchone()
            if not idem:
                raise KernelError('reconcile idempotency key not found')
            old_state = task['state']
            if outcome == 'NOT_APPLIED':
                if idem['status'] != 'CLAIMED':
                    raise KernelError('reconcile idempotency status is not CLAIMED')
                self.conn.execute("UPDATE idempotency SET status='RETRYABLE',result_ref=? WHERE logical_key=?", (evidence_ref, checkpoint['idempotency_key']))
                next_state = 'QUEUED'
                event_type = 'RECONCILE_NOT_APPLIED'
            elif outcome == 'APPLIED':
                self.conn.execute("UPDATE idempotency SET status='RECONCILED_APPLIED',result_ref=? WHERE logical_key=?", (evidence_ref, checkpoint['idempotency_key']))
                next_state = 'HUMAN_REVIEW'
                event_type = 'RECONCILE_APPLIED'
            else:
                self.conn.execute("UPDATE idempotency SET status='RECONCILED_UNKNOWN',result_ref=? WHERE logical_key=?", (evidence_ref, checkpoint['idempotency_key']))
                next_state = 'HUMAN_REVIEW'
                event_type = 'RECONCILE_UNKNOWN'
            self.conn.execute('UPDATE tasks SET state=?,version=version+1,updated_at=? WHERE task_id=?', (next_state, now_iso(), task_id))
            self._append_event(task_id, event_type, old_state, next_state, verifier_id or 'provider-state-reader', 'reconcile_outcome_recorded', {'checkpoint_id': checkpoint_id, 'outcome': outcome, 'evidence_ref': evidence_ref, 'verifier_id': verifier_id})
            self._commit()
            return self.get_task(task_id)
        except Exception:
            self._rollback()
            raise

    def validate_checkpoint(self, checkpoint_id: str, planned_action: Any) -> dict[str, Any]:
        row = self.conn.execute('SELECT * FROM checkpoints WHERE checkpoint_id=?', (checkpoint_id,)).fetchone()
        if not row:
            raise CheckpointCorrupt(checkpoint_id)
        if row['planned_action_hash'] != stable_hash(planned_action):
            raise CheckpointCorrupt('planned action hash mismatch')
        try:
            tool_result = json.loads(row['tool_result_json']) if row['tool_result_json'] is not None else None
        except (TypeError, ValueError) as exc:
            raise CheckpointCorrupt('checkpoint tool result is not valid JSON') from exc
        payload = {'task_id': row['task_id'], 'attempt_id': row['attempt_id'], 'step_id': row['step_id'], 'state': row['state'], 'planned_action': planned_action, 'capability_epoch': row['capability_epoch'], 'idempotency_key': row['idempotency_key'], 'pre_observation_ref': row['pre_observation_ref'], 'post_observation_ref': row['post_observation_ref'], 'tool_result': tool_result, 'verifier_verdict': row['verifier_verdict']}
        if row['payload_hash'] != stable_hash(payload):
            raise CheckpointCorrupt('checkpoint payload hash mismatch')
        return dict(row)

    def idempotency_claim(self, task_id: str, step_id: str, action_type: str, resource_identity: str) -> tuple[str, bool]:
        logical_key = stable_hash({'task_id': task_id, 'step_id': step_id, 'action_type': action_type, 'resource_identity': resource_identity})
        self._begin()
        try:
            row = self.conn.execute('SELECT * FROM idempotency WHERE logical_key=?', (logical_key,)).fetchone()
            if row:
                if row['status'] == 'RETRYABLE':
                    self.conn.execute("UPDATE idempotency SET status='CLAIMED',result_ref=NULL WHERE logical_key=?", (logical_key,))
                    self._commit()
                    return (logical_key, True)
                self._commit()
                return (logical_key, False)
            self.conn.execute('INSERT INTO idempotency(logical_key,task_id,step_id,action_type,resource_identity,status,created_at) VALUES (?,?,?,?,?,?,?)', (logical_key, task_id, step_id, action_type, resource_identity, 'CLAIMED', now_iso()))
            self._commit()
            return (logical_key, True)
        except Exception:
            self._rollback()
            raise

    def idempotency_complete(self, logical_key: str, result_ref: str) -> None:
        if not logical_key or not result_ref:
            raise KernelError('invalid idempotency completion')
        self._begin()
        try:
            row = self.conn.execute('SELECT * FROM idempotency WHERE logical_key=?', (logical_key,)).fetchone()
            if not row:
                raise KernelError('idempotency key not found')
            if row['status'] == 'COMPLETED':
                if row['result_ref'] != result_ref:
                    raise KernelError('idempotency result mismatch')
                self._commit()
                return
            if row['status'] != 'CLAIMED':
                raise KernelError(f"invalid idempotency status: {row['status']}")
            self.conn.execute("UPDATE idempotency SET status='COMPLETED',result_ref=? WHERE logical_key=?", (result_ref, logical_key))
            self._commit()
        except Exception:
            self._rollback()
            raise

    def commit_verification_result(self, task_id: str, lease_id: str, verification_result: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(verification_result, dict) or verification_result.get('verdict') != 'VERIFIED':
            raise KernelError('completion requires verifier verdict VERIFIED')
        if not verification_result.get('verifier_id') or not verification_result.get('evidence_ref'):
            raise KernelError('completion requires verifier identity and evidence')
        return self.commit_completed(task_id, lease_id, 'VERIFIED', str(verification_result['evidence_ref']))

    def commit_completed(self, task_id: str, lease_id: str, verifier_verdict: str, evidence_ref: str) -> dict[str, Any]:
        if verifier_verdict != 'VERIFIED' or not evidence_ref:
            raise KernelError('completion requires independent VERIFIED verdict and evidence')
        self._begin()
        try:
            self._assert_lease(lease_id, task_id)
            task = self._task(task_id)
            if task['state'] not in {'VERIFYING', 'RUNNING'}:
                raise InvalidTransition(f"{task['state']}->COMPLETED")
            old = task['state']
            self.conn.execute("UPDATE tasks SET state='COMPLETED',version=version+1,updated_at=? WHERE task_id=?", (now_iso(), task_id))
            self._append_event(task_id, 'TASK_COMPLETED', old, 'COMPLETED', 'verifier', 'postcondition_verified', {'evidence_ref': evidence_ref, 'verifier_verdict': verifier_verdict, 'lease_id': lease_id})
            self.conn.execute('UPDATE leases SET released=1 WHERE lease_id=?', (lease_id,))
            self.conn.execute('UPDATE queue_accounts SET active=CASE WHEN active>0 THEN active-1 ELSE 0 END WHERE owner=(SELECT owner FROM tasks WHERE task_id=? )', (task_id,))
            self._commit()
            return self.get_task(task_id)
        except Exception:
            self._rollback()
            raise

    def set_global_kill(self, active: bool, actor: str='operator') -> int:
        self._begin()
        try:
            c = self._control()
            epoch = int(c['global_kill_epoch']) + (1 if active else 0)
            self.conn.execute('UPDATE control SET global_kill=?,global_kill_epoch=? WHERE id=1', (1 if active else 0, epoch))
            self._append_event('__global__', 'GLOBAL_KILL_ON' if active else 'GLOBAL_KILL_OFF', None, None, actor, 'operator_toggle', {'epoch': epoch})
            self._commit()
            return epoch
        except Exception:
            self._rollback()
            raise

    def set_task_kill(self, task_id: str, actor: str='operator') -> dict[str, Any]:
        self._begin()
        try:
            task = self._task(task_id)
            if task['state'] in TERMINAL:
                raise InvalidTransition('terminal task is immutable')
            active_leases = self.conn.execute('SELECT lease_id FROM leases WHERE task_id=? AND released=0', (task_id,)).fetchall()
            self.conn.execute("UPDATE tasks SET state='CANCELLED',version=version+1,updated_at=? WHERE task_id=?", (now_iso(), task_id))
            self.conn.execute('UPDATE leases SET released=1 WHERE task_id=?', (task_id,))
            for _ in active_leases:
                self.conn.execute('UPDATE queue_accounts SET active=CASE WHEN active>0 THEN active-1 ELSE 0 END WHERE owner=?', (task['owner'],))
            self._append_event(task_id, 'TASK_KILLED', task['state'], 'CANCELLED', actor, 'task_kill', {})
            self._commit()
            return self.get_task(task_id)
        except Exception:
            self._rollback()
            raise

    def auto_reconcile_orphans(self, actor: str='kernel_watchdog', stale_seconds: float=60.0, now: float | None=None) -> list[str]:
        """Tự động rà soát các task bị mồ côi (chết do crash, mất kết nối) và đưa vào RECONCILING.

        [P1 FIX 2026-09-05] Watchdog phải tôn trọng lease authority:
        - Gate trên lease còn hạn (leases.expires_at do heartbeat refresh cùng
          heartbeat_at), KHÔNG gate trên tasks.updated_at — worker sống có thể
          ở lại RUNNING lâu mà không đổi state; heartbeat không đụng vào
          tasks.updated_at nên cờ cũ từng bắt worker hợp lệ thành mồ côi.
        - Chuyển state chỉ qua ALLOWED_TRANSITIONS + version increment
          (LEASED/RUNNING -> RECOVERING -> RECONCILING); cựu bản ghi raw
          'UPDATE ... state=UNKNOWN' từng ghi transition ngoài luật vào journal.
        """
        orphans: list[str] = []
        now = time.time() if now is None else float(now)
        cutoff = int(now - float(stale_seconds))
        try:
            self._begin()
            rows = self.conn.execute(
                "SELECT task_id, state FROM tasks "
                "WHERE state IN ('LEASED', 'RUNNING') "
                "AND CAST(strftime('%s', updated_at) AS INTEGER) < ?",
                (cutoff,),
            ).fetchall()
            for r in rows:
                tid = r['task_id']
                # Lease authority gate: an unreleased lease with expires_at in
                # the future still belongs to a live worker (heartbeat refreshes
                # heartbeat_at/expires_at together) — the watchdog must not
                # hijack it, fail-closed instead.
                lease = self.conn.execute(
                    'SELECT * FROM leases WHERE task_id=? AND released=0 ORDER BY fencing_token DESC LIMIT 1',
                    (tid,),
                ).fetchone()
                if lease is not None and float(lease['expires_at']) > now:
                    continue
                task = self._task(tid)
                # LOST_RESPONSE with action_dispatched=True is the fail-closed
                # assumption for an orphan: route through the reconcile path.
                decision = self.recovery_decision('LOST_RESPONSE', True, 'UNKNOWN')
                plan = [('RECOVERING', 'ORPHAN_TIMEOUT')]
                if decision.next_state == 'RECONCILING':
                    plan.append(('RECONCILING', 'AUTO_RECONCILE_INITIATED'))
                payload = {
                    'lease_id': lease['lease_id'] if lease is not None else None,
                    'heartbeat_at': float(lease['heartbeat_at']) if lease is not None else None,
                    'expires_at': float(lease['expires_at']) if lease is not None else None,
                    'watchdog_now': now,
                    'stale_seconds': float(stale_seconds),
                }
                current = task['state']
                moved = False
                for target, reason in plan:
                    # Never write a transition outside the map (no free-form state).
                    if target not in ALLOWED_TRANSITIONS.get(current, set()):
                        break
                    self.conn.execute(
                        'UPDATE tasks SET state=?,version=version+1,updated_at=? WHERE task_id=?',
                        (target, now_iso(), tid),
                    )
                    self._append_event(tid, 'STATE_TRANSITION', current, target, actor, reason, dict(payload))
                    current = target
                    moved = True
                if not moved:
                    continue
                if lease is not None:
                    self.conn.execute('UPDATE leases SET released=1 WHERE lease_id=?', (lease['lease_id'],))
                self.conn.execute(
                    'UPDATE queue_accounts SET active=CASE WHEN active>0 THEN active-1 ELSE 0 END WHERE owner=?',
                    (task['owner'],),
                )
                orphans.append(tid)
            self._commit()
        except Exception:
            self._rollback()
            raise
        return orphans

    def verify_integrity(self) -> dict[str, Any]:
        """[C3 — Gemini indictment: SQLite SPOF] Kiểm tra sức khoẻ DB.

        PRAGMA quick_check + verify hash-chain toàn bộ journal. KHÔNG tự sửa
        gì — chỉ báo cáo (fail-closed với bằng chứng). Đây là durability
        single-node; HA đa node (Raft/etcd) là kiến trúc khác, không claim."""
        quick = self.conn.execute('PRAGMA quick_check').fetchone()[0]
        chains = {'checked': 0, 'invalid': []}
        for row in self.conn.execute('SELECT DISTINCT task_id FROM events').fetchall():
            chains['checked'] += 1
            result = self.verify_journal(row['task_id'])
            if not result['hash_chain_valid']:
                chains['invalid'].append({'task_id': row['task_id'], 'errors': result['errors'][:3]})
        return {'quick_check': quick, 'tasks': chains['checked'], 'invalid_chains': chains['invalid']}

    def backup(self, backup_dir: str | Path, retain: int=7) -> dict[str, Any]:
        """Online backup qua sqlite3 backup API (an toàn khi đang chạy WAL) +
        prune giữ lại `retain` bản mới nhất. Đây là giảm thiểu thiệt hại khi
        hỏng sector — KHÔNG phải High Availability đa node."""
        import time as _time
        dest = Path(backup_dir)
        dest.mkdir(parents=True, exist_ok=True)
        import uuid
        stamp = f"{_time.strftime('%Y%m%d-%H%M%S')}-{_time.time_ns() % 10 ** 9:09d}-{uuid.uuid4().hex[:6]}"
        target = dest / f'kernel-backup-{stamp}.sqlite3'
        self._storage.backup_to(target)
        backups = sorted(dest.glob('kernel-backup-*.sqlite3'))
        pruned = 0
        for old in backups[:max(0, len(backups) - int(retain))]:
            old.unlink(missing_ok=True)
            pruned += 1
        return {'backup': str(target), 'size_bytes': target.stat().st_size, 'pruned': pruned, 'retained': len(backups) - pruned}

    def recover_on_boot(self, actor: str='boot_recovery') -> dict[str, Any]:
        """[Cổng F — Event-Sourcing Crash Recovery] Máy tự replay journal.

        Audit Cổng F/C: TraceLedger từng chỉ là immutable log cho NGƯỜI đọc.
        Hàm này biến journal thành replay engine: lúc boot, mọi task non-
        terminal được dựng lại state từ journal (hash-chain được verify
        trước), rồi đưa về trạng thái an toàn theo luật chuyển đổi:

          LEASED/WAITING_TOOL -> RECOVERING (đuợc ALLOWED_TRANSITIONS cho phép)
          RUNNING/VERIFYING   -> HUMAN_REVIEW
          CHECKPOINTED        -> QUEUED (resume được)
          UNKNOWN/RECONCILING/... -> giữ nguyên + báo cáo (cần luồng reconcile)

        Fail-closed tuyệt đối: journal hash-chain HỎNG → KHÔNG tự sửa, chỉ
        báo cáo corrupted (nhẹ tay với bằng chứng hơn là tiện tay "khắc phục").
        """
        report: dict[str, Any] = {'recovered': [], 'corrupted': [], 'left_as_is': []}
        rows = self.conn.execute('SELECT task_id, state FROM tasks').fetchall()
        for row in rows:
            task_id, state = (row['task_id'], row['state'])
            journal = self.verify_journal(task_id)
            if not journal['hash_chain_valid']:
                report['corrupted'].append({'task_id': task_id, 'errors': journal['errors'][:5]})
                continue
            if state in TERMINAL:
                continue
            self.rebuild_projection(task_id)
            current = self._task(task_id)['state']
            if current == 'RUNNING' or current == 'VERIFYING':
                self.transition(task_id, 'HUMAN_REVIEW', actor=actor, reason='boot_recovery_in_flight')
                report['recovered'].append({'task_id': task_id, 'from': current, 'to': 'HUMAN_REVIEW'})
            elif current in {'LEASED', 'WAITING_TOOL'}:
                self.transition(task_id, 'RECOVERING', actor=actor, reason='boot_recovery_in_flight')
                report['recovered'].append({'task_id': task_id, 'from': current, 'to': 'RECOVERING'})
            elif current == 'CHECKPOINTED':
                self.transition(task_id, 'QUEUED', actor=actor, reason='boot_recovery_resume')
                report['recovered'].append({'task_id': task_id, 'from': current, 'to': 'QUEUED'})
            else:
                report['left_as_is'].append({'task_id': task_id, 'state': current})
        return report

    def in_flight_count(self) -> int:
        """[CHAIN-AUDIT: backpressure] Số task chưa tới quyết định cuối —
        dùng làm admission control chống ngập kernel dưới tải đồng thời."""
        row = self.conn.execute("SELECT COUNT(*) AS n FROM tasks WHERE state NOT IN ('COMPLETED','FAILED','CANCELLED')").fetchone()
        return int(row['n'])

    def get_task(self, task_id: str) -> dict[str, Any]:
        return dict(self._task(task_id))

    def get_events(self, task_id: str) -> list[dict[str, Any]]:
        return [dict(x) for x in self.conn.execute('SELECT * FROM events WHERE task_id=? ORDER BY seq', (task_id,)).fetchall()]

    def get_checkpoint(self, checkpoint_id: str) -> dict[str, Any]:
        row = self.conn.execute('SELECT * FROM checkpoints WHERE checkpoint_id=?', (checkpoint_id,)).fetchone()
        if not row:
            raise CheckpointCorrupt(checkpoint_id)
        return dict(row)

    def verify_journal(self, task_id: str) -> dict[str, Any]:
        events = self.get_events(task_id)
        prev = None
        errors = []
        for i, e in enumerate(events, 1):
            if e['seq'] != i:
                errors.append(f"sequence:{e['seq']} expected {i}")
            if e['prev_event_hash'] != prev:
                errors.append(f"prev_hash:{e['seq']}")
            try:
                payload = json.loads(e['payload_json'])
            except (TypeError, ValueError):
                errors.append(f"payload_json:{e['seq']}")
                prev = e['event_hash']
                continue
            body = {'event_id': e['event_id'], 'task_id': e['task_id'], 'seq': e['seq'], 'type': e['type'], 'from_state': e['from_state'], 'to_state': e['to_state'], 'actor': e['actor'], 'reason': e['reason'], 'payload': payload, 'policy_hash': e['policy_hash'], 'prev_event_hash': e['prev_event_hash']}
            if stable_hash(body) != e['event_hash']:
                errors.append(f"event_hash:{e['seq']}")
            prev = e['event_hash']
        return {'task_id': task_id, 'event_count': len(events), 'hash_chain_valid': not errors, 'errors': errors}

    def rebuild_projection(self, task_id: str) -> dict[str, Any]:
        journal = self.verify_journal(task_id)
        if not journal['hash_chain_valid']:
            details = ';'.join(journal['errors'])
            raise KernelError(f'journal integrity invalid: {details}')
        events = self.get_events(task_id)
        if not events:
            raise NotFound(task_id)
        state = events[0]['to_state']
        for event in events[1:]:
            if event['to_state']:
                state = event['to_state']
        self.conn.execute('UPDATE tasks SET state=?,updated_at=? WHERE task_id=?', (state, now_iso(), task_id))
        return self.get_task(task_id)

    @staticmethod
    def recovery_decision(reason: str, action_dispatched: bool=False, side_effect_risk: str='R0') -> RecoveryDecision:
        if action_dispatched or reason in {'TOOL_UNKNOWN_STATE', 'LOST_RESPONSE', 'WORKER_CRASH_AFTER_SUBMIT'}:
            return RecoveryDecision('RECONCILE', 'ACTION_DISPATCHED_WITHOUT_RESULT', False, ('provider_request_status', 'read_only_state'), 'RECONCILING', 'human_review_if_unknown')
        if reason in {'PROVIDER_TIMEOUT', 'DEPENDENCY_NOT_READY', 'TRANSIENT_NETWORK'} and side_effect_risk in {'R0', 'R1'}:
            return RecoveryDecision('RETRY', 'TRANSIENT_FAILURE', True, (), 'QUEUED', 'bounded_backoff')
        if reason in {'POLICY_DENIED', 'INVALID_CAPABILITY', 'CHECKPOINT_CORRUPT'}:
            return RecoveryDecision('STOP', 'NON_RETRYABLE_POLICY_OR_INTEGRITY_FAILURE', False, (), 'FAILED', 'none')
        return RecoveryDecision('REVIEW', 'INSUFFICIENT_STATE_EVIDENCE', False, ('last_checkpoint', 'event_journal'), 'HUMAN_REVIEW', 'human_required')
