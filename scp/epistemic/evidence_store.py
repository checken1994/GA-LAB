"""Evidence Store (26-P0.05) - the strongest P0 authority.

Invariants:
  - occurrence identity != content identity: the same content observed twice
    yields the SAME content_hash/blob but TWO different evidence_ids;
  - the epistemic tables (`evidence`, `content_blobs`, `evidence_links`) are
    APPEND-ONLY (SQLite triggers abort UPDATE and DELETE) - a wrong observation
    is corrected by a NEW evidence + SUPERSEDES relation, never by rewriting
    history; only the lifecycle tables (`evidence_payload_state`,
    `retention_events`) stay mutable;
  - record_hash = sha256 (or HMAC-SHA256 when a key is configured) over the
    canonical immutable metadata, so raw-SQL tampering with metadata is
    detectable by verify_integrity(); the keyed variant is defense-in-depth:
    a raw-SQL actor can no longer recompute the hash after editing, but it is
    NOT an external trust root (the key lives with the deployment);
  - blob write is crash-ordered: staging -> fsync -> atomic rename -> DB
    transaction, and content blobs are deduplicated while occurrences are not;
  - blob write is crash-ordered: staging -> fsync -> atomic rename -> DB
    transaction, and content blobs are deduplicated while occurrences are not;
  - missing/tampered payload fails CLOSED (never returned as valid evidence);
  - MODEL_RESPONSE evidence proves "the model said X" - never "X is true".
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import subprocess
import uuid
from pathlib import Path

from scp.contracts.data_class import DataClass, parse_data_class
from scp.contracts.ids import content_id, new_id
from scp.contracts.time import now_utc_iso
from scp.persistence import FoundationDB

EVIDENCE_KINDS = {
    "HTTP_RESPONSE",
    "FILE_OBSERVATION",
    "RUNTIME_OBSERVATION",
    "TEST_RESULT",
    "CONFIG_SNAPSHOT",
    "GIT_SNAPSHOT",
    "MODEL_RESPONSE",   # proves "model said X", never "X is true"
    "HUMAN_ATTESTATION",
}

_IMMUTABLE_FIELDS = (
    "evidence_id", "kind", "content_hash", "source_id", "observed_at",
    "task_id", "attempt_id", "trace_id", "collector_id", "collector_version",
    "policy_hash", "data_class", "retention_policy_id", "valid_from",
    "valid_to", "metadata_json", "created_at",
)

_EVIDENCE_MIGRATIONS = [
    (
        "0001_evidence_core",
        [
            """CREATE TABLE IF NOT EXISTS evidence (
                   evidence_id TEXT PRIMARY KEY,
                   kind TEXT NOT NULL,
                   content_hash TEXT NOT NULL,
                   content_ref TEXT,
                   source_id TEXT,
                   observed_at TEXT NOT NULL,
                   task_id TEXT,
                   attempt_id TEXT,
                   trace_id TEXT,
                   collector_id TEXT NOT NULL,
                   collector_version TEXT NOT NULL,
                   policy_hash TEXT,
                   data_class TEXT NOT NULL,
                   retention_policy_id TEXT,
                   valid_from TEXT,
                   valid_to TEXT,
                   metadata_json TEXT NOT NULL,
                   record_hash TEXT NOT NULL,
                   created_at TEXT NOT NULL)""",
            """CREATE TABLE IF NOT EXISTS content_blobs (
                   content_hash TEXT PRIMARY KEY,
                   storage_path TEXT NOT NULL,
                   byte_length INTEGER NOT NULL,
                   mime_type TEXT,
                   created_at TEXT NOT NULL)""",
            """CREATE TABLE IF NOT EXISTS evidence_links (
                   parent_evidence_id TEXT NOT NULL,
                   child_evidence_id TEXT NOT NULL,
                   relation TEXT NOT NULL,
                   created_at TEXT NOT NULL,
                   PRIMARY KEY (parent_evidence_id, child_evidence_id, relation))""",
            """CREATE TABLE IF NOT EXISTS evidence_payload_state (
                   evidence_id TEXT PRIMARY KEY,
                   payload_state TEXT NOT NULL DEFAULT 'AVAILABLE',
                   last_checked_at TEXT NOT NULL)""",
            """CREATE TABLE IF NOT EXISTS retention_events (
                   retention_event_id TEXT PRIMARY KEY,
                   target TEXT NOT NULL,
                   reason TEXT NOT NULL,
                   policy TEXT,
                   purged_at TEXT NOT NULL)""",
            """CREATE TRIGGER IF NOT EXISTS evidence_no_update
                   BEFORE UPDATE ON evidence
                   BEGIN
                       SELECT RAISE(ABORT, 'evidence is immutable - supersede instead');
                   END;""",
        ],
    ),
    (
        # Append-only DELETE enforcement (M5). Lifecycle tables
        # (evidence_payload_state, retention_events) stay mutable by design.
        "0002_evidence_append_only",
        [
            """CREATE TRIGGER IF NOT EXISTS evidence_no_delete
                   BEFORE DELETE ON evidence
                   BEGIN
                       SELECT RAISE(ABORT, 'evidence is append-only - purge via retention lifecycle');
                   END;""",
            """CREATE TRIGGER IF NOT EXISTS content_blobs_no_delete
                   BEFORE DELETE ON content_blobs
                   BEGIN
                       SELECT RAISE(ABORT, 'content_blobs is append-only - purge via retention lifecycle');
                   END;""",
            """CREATE TRIGGER IF NOT EXISTS evidence_links_no_delete
                   BEFORE DELETE ON evidence_links
                   BEGIN
                       SELECT RAISE(ABORT, 'evidence_links is append-only - supersede instead');
                   END;""",
        ],
    ),
]


class EvidenceIntegrityError(RuntimeError):
    """Payload missing/tampered/purged - evidence must NOT be used as valid."""


def _blob_rel_path(digest: str) -> str:
    # Windows forbids ':' in file names (it means Alternate Data Stream), so
    # the blob FILE name is the bare hex digest; the "sha256:" prefix lives in
    # the content_hash column only.
    hex_part = digest.split(":", 1)[1]
    return f"sha256/{hex_part[:2]}/{hex_part[2:4]}/{hex_part}"


# --- Keyed record_hash (defense-in-depth, M5) -------------------------------
# Plain sha256 over canonical metadata is recomputable by ANY raw-SQL actor,
# so an attacker who drops the immutability trigger can re-hash edited rows.
# When an HMAC key is configured, record_hash becomes HMAC-SHA256(key, ...) and
# can no longer be recomputed without the key. This is NOT an external trust
# root and NOT a secrecy guarantee: the key lives with the deployment. It only
# raises the cost of tampering.
HMAC_KEY_ENV = "SCP_EVIDENCE_HMAC_KEY"
_HMAC_SCHEME_PREFIX = "hmac-sha256:"


def derive_repo_identity_key(repo_root: str | Path) -> str:
    """Deterministic HMAC key material derived from repo identity.

    Prefers the git origin URL; falls back to the resolved repo path. The
    result is NOT a secret (anyone with repo read access can recompute it) -
    deployments with a real secret store should pass ``SCP_EVIDENCE_HMAC_KEY``
    instead. Useful when no secret store exists but tamper elevation is still
    wanted.
    """
    root = Path(repo_root)
    identity = ""
    try:
        proc = subprocess.run(
            ["git", "-C", str(root), "config", "--get", "remote.origin.url"],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
        if proc.returncode == 0:
            identity = proc.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        identity = ""
    if not identity:
        identity = str(root.resolve())
    return "sha256:" + hashlib.sha256(
        f"scp-evidence-hmac-v1:{identity}".encode("utf-8")
    ).hexdigest()


class EvidenceStore:
    def __init__(
        self,
        db_path: str | Path,
        objects_dir: str | Path,
        hmac_key: str | bytes | None = None,
    ) -> None:
        # Key resolution: explicit param > env SCP_EVIDENCE_HMAC_KEY > None.
        # Without a key the store stays fully backward compatible (plain
        # sha256 record_hash); with a key it writes/requires HMAC record_hash.
        key: bytes | None = hmac_key if hmac_key is not None else (os.environ.get(HMAC_KEY_ENV) or None)
        if isinstance(key, str):
            key = key.encode("utf-8")
        self._hmac_key: bytes | None = key if key else None
        self.db = FoundationDB(db_path, _EVIDENCE_MIGRATIONS)
        self.objects_dir = Path(objects_dir)
        self.objects_dir.mkdir(parents=True, exist_ok=True)
        staging = self.objects_dir / ".staging"
        staging.mkdir(parents=True, exist_ok=True)
        # C1 reconciliation: a previous process may have died after staging a
        # blob but before the atomic rename - staged files are safe to delete.
        for leftover in staging.iterdir():
            leftover.unlink(missing_ok=True)

    def _record_hash(self, canonical_metadata_json: str) -> str:
        """Keyed (HMAC-SHA256) or plain (sha256) hash of canonical metadata."""
        data = canonical_metadata_json.encode("utf-8")
        if self._hmac_key:
            return _HMAC_SCHEME_PREFIX + hmac.new(self._hmac_key, data, hashlib.sha256).hexdigest()
        return content_id(data)

    def observe(
        self,
        *,
        kind: str,
        content: bytes,
        collector_id: str,
        collector_version: str,
        source_id: str | None = None,
        task_id: str | None = None,
        attempt_id: str | None = None,
        trace_id: str | None = None,
        policy_hash: str | None = None,
        data_class: DataClass | str = DataClass.INTERNAL,
        retention_policy_id: str | None = None,
        metadata: dict | None = None,
        mime_type: str | None = None,
        observed_at: str | None = None,
    ) -> dict:
        kind = str(kind).strip().upper()
        if kind not in EVIDENCE_KINDS:
            raise ValueError(f"unknown evidence kind: {kind!r}")
        if not isinstance(content, (bytes, bytearray)) or not content:
            raise ValueError("evidence content must be non-empty bytes")
        digest = content_id(bytes(content))
        blob_path = self.objects_dir / _blob_rel_path(digest)

        # C1->C2-safe blob write: stage + fsync, then atomic rename. If the
        # blob already exists, VERIFY it before reuse - never overwrite.
        staging = self.objects_dir / ".staging" / uuid.uuid4().hex
        staging.parent.mkdir(parents=True, exist_ok=True)
        staging.write_bytes(bytes(content))
        with staging.open("rb+") as handle:
            handle.flush()
            os.fsync(handle.fileno())
        if blob_path.exists():
            if content_id(blob_path.read_bytes()) != digest:
                raise EvidenceIntegrityError(
                    f"existing blob hash mismatch for {digest} - refusing to overwrite"
                )
            staging.unlink(missing_ok=True)
        else:
            blob_path.parent.mkdir(parents=True, exist_ok=True)
            os.replace(staging, blob_path)

        row = {
            "evidence_id": new_id("ev"),
            "kind": kind,
            "content_hash": digest,
            "content_ref": _blob_rel_path(digest),
            "source_id": source_id,
            "observed_at": observed_at or now_utc_iso(),
            "task_id": task_id,
            "attempt_id": attempt_id,
            "trace_id": trace_id,
            "collector_id": collector_id,
            "collector_version": collector_version,
            "policy_hash": policy_hash,
            "data_class": parse_data_class(data_class).value,
            "retention_policy_id": retention_policy_id,
            "valid_from": None,
            "valid_to": None,
            "metadata_json": json.dumps(metadata or {}, ensure_ascii=False, sort_keys=True),
            "created_at": now_utc_iso(),
        }
        row["record_hash"] = self._record_hash(
            json.dumps({f: row[f] for f in _IMMUTABLE_FIELDS}, ensure_ascii=False, sort_keys=True)
        )
        with self.db.transaction() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO content_blobs (content_hash, storage_path, byte_length, mime_type, created_at) VALUES (?,?,?,?,?)",
                (digest, _blob_rel_path(digest), len(content), mime_type, now_utc_iso()),
            )
            conn.execute(
                """INSERT INTO evidence (evidence_id, kind, content_hash, content_ref, source_id,
                       observed_at, task_id, attempt_id, trace_id, collector_id, collector_version,
                       policy_hash, data_class, retention_policy_id, valid_from, valid_to,
                       metadata_json, record_hash, created_at)
                   VALUES (:evidence_id,:kind,:content_hash,:content_ref,:source_id,:observed_at,
                       :task_id,:attempt_id,:trace_id,:collector_id,:collector_version,
                       :policy_hash,:data_class,:retention_policy_id,:valid_from,:valid_to,
                       :metadata_json,:record_hash,:created_at)""",
                row,
            )
            conn.execute(
                "INSERT INTO evidence_payload_state (evidence_id, payload_state, last_checked_at) VALUES (?, 'AVAILABLE', ?)",
                (row["evidence_id"], now_utc_iso()),
            )
        return self.get(row["evidence_id"])

    def get(self, evidence_id: str) -> dict:
        rows = self.db.query("SELECT * FROM evidence WHERE evidence_id=?", (evidence_id,))
        if not rows:
            raise KeyError(f"evidence not found: {evidence_id}")
        record = dict(rows[0])
        integrity = self.verify_integrity(evidence_id)
        if not integrity["ok"]:
            raise EvidenceIntegrityError(
                f"evidence {evidence_id} failed integrity: {integrity['errors']} "
                f"(payload_state={integrity['payload_state']})"
            )
        record["payload_state"] = integrity["payload_state"]
        return record

    def verify_integrity(self, evidence_id: str) -> dict:
        rows = self.db.query("SELECT * FROM evidence WHERE evidence_id=?", (evidence_id,))
        if not rows:
            return {"ok": False, "payload_state": "MISSING", "errors": ["evidence row not found"]}
        record = dict(rows[0])
        errors: list[str] = []

        canonical = json.dumps({f: record[f] for f in _IMMUTABLE_FIELDS}, ensure_ascii=False, sort_keys=True)
        stored_hash = record["record_hash"] or ""
        # Scheme dispatch is FAIL-CLOSED in both directions:
        #   - a keyed record without a configured key cannot be validated;
        #   - an unkeyed record in a keyed store is refused, because plain
        #     sha256 is recomputable by any raw-SQL actor (that is exactly the
        #     tamper vector the HMAC key exists to close).
        if stored_hash.startswith(_HMAC_SCHEME_PREFIX):
            if not self._hmac_key:
                errors.append("record_hash is HMAC-keyed but no HMAC key is configured (fail-closed)")
            else:
                expected = _HMAC_SCHEME_PREFIX + hmac.new(
                    self._hmac_key, canonical.encode("utf-8"), hashlib.sha256
                ).hexdigest()
                if expected != stored_hash:
                    errors.append("record_hash mismatch - immutable metadata was tampered with")
        elif stored_hash.startswith("sha256:"):
            if self._hmac_key:
                errors.append(
                    "record_hash is unkeyed but this store requires an HMAC-keyed hash - "
                    "possible tampering or unkeyed legacy record"
                )
            elif stored_hash != content_id(canonical.encode("utf-8")):
                errors.append("record_hash mismatch - immutable metadata was tampered with")
        else:
            errors.append("record_hash scheme is unknown - fail-closed")

        state_rows = self.db.query(
            "SELECT payload_state FROM evidence_payload_state WHERE evidence_id=?", (evidence_id,)
        )
        state = state_rows[0]["payload_state"] if state_rows else "MISSING"
        if state != "AVAILABLE":
            errors.append(f"payload is {state}")
        else:
            blob_path = self.objects_dir / (record["content_ref"] or "")
            if not blob_path.is_file():
                errors.append("blob file missing (C4)")
                state = "MISSING"
            else:
                if content_id(blob_path.read_bytes()) != record["content_hash"]:
                    errors.append("blob content hash mismatch (C4 tamper)")
                    state = "MISSING"
        if errors:
            self.db.execute(
                "INSERT INTO evidence_payload_state (evidence_id, payload_state, last_checked_at) VALUES (?,?,?) "
                "ON CONFLICT(evidence_id) DO UPDATE SET payload_state=excluded.payload_state, last_checked_at=excluded.last_checked_at",
                (evidence_id, state if state in {"PURGED", "MISSING"} else "MISSING", now_utc_iso()),
            )
            self.db._conn.commit()
        return {"ok": not errors, "payload_state": state, "errors": errors}

    def read_content(self, evidence_id: str) -> bytes:
        record = self.get(evidence_id)  # fail-closed on any integrity problem
        return (self.objects_dir / record["content_ref"]).read_bytes()

    def link(self, parent_evidence_id: str, child_evidence_id: str, relation: str) -> None:
        relation = str(relation).strip().upper()
        if not relation.replace("_", "").isalnum():
            raise ValueError(f"invalid relation: {relation!r}")
        with self.db.transaction() as conn:
            conn.execute(
                "INSERT INTO evidence_links (parent_evidence_id, child_evidence_id, relation, created_at) VALUES (?,?,?,?)",
                (parent_evidence_id, child_evidence_id, relation, now_utc_iso()),
            )

    def supersede(self, old_evidence_id: str, **observe_kwargs) -> dict:
        """A wrong observation is corrected by NEW evidence + SUPERSEDES, never an edit."""
        replacement = self.observe(**observe_kwargs)
        self.link(old_evidence_id, replacement["evidence_id"], "SUPERSEDES")
        return replacement

    def purge_payload(self, evidence_id: str, reason: str, policy: str | None = None) -> str:
        """Retention purge: metadata + hash stay durable forever, payload goes."""
        rows = self.db.query("SELECT content_ref FROM evidence WHERE evidence_id=?", (evidence_id,))
        if not rows:
            raise KeyError(evidence_id)
        blob_path = self.objects_dir / (rows[0]["content_ref"] or "")
        if blob_path.is_file():
            blob_path.unlink()
        event_id = new_id("ret")
        with self.db.transaction() as conn:
            conn.execute(
                "INSERT INTO evidence_payload_state (evidence_id, payload_state, last_checked_at) VALUES (?, 'PURGED', ?) "
                "ON CONFLICT(evidence_id) DO UPDATE SET payload_state='PURGED', last_checked_at=excluded.last_checked_at",
                (evidence_id, now_utc_iso()),
            )
            conn.execute(
                "INSERT INTO retention_events (retention_event_id, target, reason, policy, purged_at) VALUES (?,?,?,?,?)",
                (event_id, evidence_id, reason, policy, now_utc_iso()),
            )
        return event_id

    def scan_orphans(self) -> list[str]:
        """C2 reconciliation: blob files on disk that no evidence row references."""
        referenced = {row["content_hash"] for row in self.db.query("SELECT content_hash FROM content_blobs")}
        orphans: list[str] = []
        root = self.objects_dir / "sha256"
        if root.is_dir():
            for path in root.rglob("*"):
                if not path.is_file():
                    continue
                if content_id(path.read_bytes()) not in referenced:
                    orphans.append(str(path))
        return orphans
