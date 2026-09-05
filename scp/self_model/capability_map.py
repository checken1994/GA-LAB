"""Evidence-derived capability self-model (26-P0.10).

There is deliberately NO mark_verified() API. Capability maturity is recomputed
from the Complete-SCP reference, implementation bindings, importability, and
validated evidence bound to the exact tested SHA.
"""
from __future__ import annotations

import importlib.util
import json
import re
import subprocess
from enum import Enum
from pathlib import Path

import yaml

from scp.contracts.ids import new_id
from scp.contracts.maturity import Maturity
from scp.contracts.time import now_utc_iso
from scp.epistemic.evidence_store import EvidenceStore
from scp.persistence import FoundationDB


class CapabilityStatus(str, Enum):
    UNKNOWN = "UNKNOWN"
    DECLARED = "DECLARED"
    STATIC_PRESENT = "STATIC_PRESENT"
    INTEGRATED = "INTEGRATED"
    RUNTIME_VERIFIED = "RUNTIME_VERIFIED"
    RECOVERY_VERIFIED = "RECOVERY_VERIFIED"
    DEGRADED = "DEGRADED"
    UNAVAILABLE = "UNAVAILABLE"


_LEVEL_TO_MATURITY = {
    "A": Maturity.M2_STATIC_PRESENT,
    "B": Maturity.M3_INTEGRATED,
    "C": Maturity.M4_RUNTIME_VERIFIED,
    "D": Maturity.M5_RECOVERY_VERIFIED,
}
_MATURITY_ORDER = {m: i for i, m in enumerate(Maturity)}


_SELF_MODEL_MIGRATIONS = [
    (
        "0001_self_model",
        [
            """CREATE TABLE IF NOT EXISTS capability_proofs (
                   proof_id TEXT PRIMARY KEY,
                   capability_id TEXT NOT NULL,
                   evidence_id TEXT NOT NULL,
                   evidence_level TEXT NOT NULL CHECK(evidence_level IN ('A','B','C','D')),
                   tested_sha TEXT NOT NULL,
                   recorded_at TEXT NOT NULL,
                   UNIQUE(capability_id,evidence_id,evidence_level,tested_sha))""",
            """CREATE TABLE IF NOT EXISTS self_model_blindspots (
                   blindspot_id TEXT PRIMARY KEY,
                   capability_id TEXT NOT NULL,
                   unobservable TEXT NOT NULL,
                   reason TEXT NOT NULL,
                   affected_claims_json TEXT NOT NULL DEFAULT '[]',
                   needed_evidence_json TEXT NOT NULL DEFAULT '[]',
                   needed_instrumentation_json TEXT NOT NULL DEFAULT '[]',
                   status TEXT NOT NULL DEFAULT 'OPEN'
                     CHECK(status IN ('OPEN','MITIGATED','CLOSED')),
                   created_at TEXT NOT NULL,
                   closed_at TEXT)""",
            """CREATE TRIGGER IF NOT EXISTS capability_proofs_no_update
                   BEFORE UPDATE ON capability_proofs
                   BEGIN SELECT RAISE(ABORT, 'capability proof is immutable'); END;""",
        ],
    ),
    (
        # Append-only DELETE enforcement (M5). self_model_blindspots has a
        # status lifecycle (OPEN/MITIGATED/CLOSED) so UPDATE stays allowed,
        # but rows are never removed from the audit history.
        "0002_capability_proofs_append_only",
        [
            """CREATE TRIGGER IF NOT EXISTS capability_proofs_no_delete
                   BEFORE DELETE ON capability_proofs
                   BEGIN SELECT RAISE(ABORT, 'capability_proofs is append-only - record a new proof instead'); END;""",
            """CREATE TRIGGER IF NOT EXISTS self_model_blindspots_no_delete
                   BEFORE DELETE ON self_model_blindspots
                   BEGIN SELECT RAISE(ABORT, 'self_model_blindspots is append-only - close via status lifecycle'); END;""",
        ],
    ),
]


class CapabilityMap:
    def __init__(
        self,
        *,
        governance_db_path: str | Path,
        evidence_store: EvidenceStore,
        reference_path: str | Path,
        bindings_path: str | Path,
    ) -> None:
        self.db = FoundationDB(governance_db_path, _SELF_MODEL_MIGRATIONS)
        self.evidence_store = evidence_store
        self.reference_path = Path(reference_path)
        self.bindings_path = Path(bindings_path)
        self._repo_root_cache: Path | None = None

    def _repo_root(self) -> Path:
        """Repo that owns the Complete-SCP reference (walk up to .git)."""
        if self._repo_root_cache is None:
            for candidate in self.reference_path.resolve().parents:
                if (candidate / ".git").exists():
                    self._repo_root_cache = candidate
                    break
            else:
                self._repo_root_cache = Path.cwd()
        return self._repo_root_cache

    def _current_head_sha(self) -> str:
        """Ground-truth HEAD sha (git rev-parse HEAD); fail-closed on error."""
        root = self._repo_root()
        try:
            proc = subprocess.run(
                ["git", "-C", str(root), "rev-parse", "HEAD"],
                capture_output=True,
                text=True,
                timeout=15,
                check=False,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            raise ValueError(
                f"cannot verify tested_sha against HEAD: git invocation failed ({exc})"
            ) from exc
        sha = (proc.stdout or "").strip().lower()
        if proc.returncode != 0 or not re.fullmatch(r"[0-9a-f]{40}", sha):
            detail = ((proc.stderr or "").strip() or "no output")[:200]
            raise ValueError(
                f"cannot verify tested_sha against HEAD in {root}: git rev-parse HEAD failed ({detail})"
            )
        return sha

    def _load_specs(self) -> tuple[dict, dict]:
        reference = yaml.safe_load(self.reference_path.read_text(encoding="utf-8")) or {}
        bindings_doc = yaml.safe_load(self.bindings_path.read_text(encoding="utf-8")) or {}
        return reference, bindings_doc.get("bindings") or {}

    @staticmethod
    def _binding_importable(module_name: str) -> bool:
        try:
            return importlib.util.find_spec(module_name) is not None
        except (ImportError, AttributeError, ValueError):
            return False

    def record_proof(
        self,
        *,
        capability_id: str,
        evidence_id: str,
        evidence_level: str,
        tested_sha: str,
        archived: bool = False,
    ) -> str:
        """Record evidence eligibility; never directly marks a capability verified.

        Fail-closed validation:
          - the evidence must be integrity-valid and its immutable metadata must
            carry the matching ``tested_sha``, ``evidence_level`` AND the
            ``capability_id`` being proven (an evidence row bound to another
            capability can never support this one);
          - ``tested_sha`` must match ``git rev-parse HEAD`` of the repo owning
            the Complete-SCP reference at write time, so a proof can never be
            recorded against a sha nobody has tested; ``archived=True`` is the
            explicit override for archiving HISTORICAL proofs (it still cannot
            manufacture verification for the current sha, because
            ``recompute_capability`` only counts proofs matching its own sha).
        """
        level = str(evidence_level).strip().upper()
        if level not in _LEVEL_TO_MATURITY:
            raise ValueError("evidence_level must be A/B/C/D")
        sha = str(tested_sha).strip().lower()
        ev = self.evidence_store.get(evidence_id)
        metadata = json.loads(ev.get("metadata_json") or "{}")
        if str(metadata.get("tested_sha") or "").strip().lower() != sha:
            raise ValueError("capability proof evidence tested_sha mismatch")
        if str(metadata.get("evidence_level") or "").strip().upper() != level:
            raise ValueError("capability proof evidence level mismatch")
        if str(metadata.get("capability_id") or "").strip() != str(capability_id):
            raise ValueError("capability proof evidence must declare the capability_id it proves")
        if not archived:
            head_sha = self._current_head_sha()
            if sha != head_sha:
                raise ValueError(
                    f"tested_sha {sha} does not match current HEAD {head_sha}; "
                    "pass archived=True only for historical proof archival"
                )
        reference, _ = self._load_specs()
        if capability_id not in (reference.get("capabilities") or {}):
            raise ValueError(f"unknown Complete-SCP capability: {capability_id}")
        proof_id = new_id("proof")
        with self.db.transaction() as conn:
            conn.execute(
                """INSERT OR IGNORE INTO capability_proofs
                   (proof_id,capability_id,evidence_id,evidence_level,tested_sha,recorded_at)
                   VALUES (?,?,?,?,?,?)""",
                (proof_id, capability_id, evidence_id, level, sha, now_utc_iso()),
            )
        return proof_id

    def recompute_capability(self, capability_id: str, tested_sha: str) -> dict:
        reference, bindings = self._load_specs()
        capabilities = reference.get("capabilities") or {}
        if capability_id not in capabilities:
            return {
                "capability_id": capability_id,
                "status": CapabilityStatus.UNKNOWN.value,
                "maturity": Maturity.M0_IDEA.value,
                "tested_sha": str(tested_sha),
                "evidence_refs": [],
                "limitations": ["capability is not declared in Complete-SCP reference"],
            }

        ref_version = str((reference.get("reference") or {}).get("version", "UNKNOWN"))
        binding = bindings.get(capability_id) or {}
        modules = [str(x) for x in (binding.get("implementations") or [])]
        present = [m for m in modules if self._binding_importable(m)]
        missing = [m for m in modules if m not in present]

        maturity = Maturity.M1_SPECIFIED
        status = CapabilityStatus.DECLARED
        limitations: list[str] = []
        if modules and not missing:
            maturity = Maturity.M2_STATIC_PRESENT
            status = CapabilityStatus.STATIC_PRESENT
        elif modules and missing:
            limitations.append(f"missing implementation bindings: {missing}")
        elif not modules:
            limitations.append("no implementation binding")

        rows = self.db.query(
            """SELECT evidence_id,evidence_level,tested_sha,recorded_at
               FROM capability_proofs WHERE capability_id=? AND tested_sha=?
               ORDER BY recorded_at""",
            (capability_id, str(tested_sha)),
        )
        valid_rows: list[dict] = []
        for row in rows:
            try:
                ev = self.evidence_store.get(row["evidence_id"])
                metadata = json.loads(ev.get("metadata_json") or "{}")
                if str(metadata.get("tested_sha") or "") != str(tested_sha):
                    continue
                if str(metadata.get("evidence_level") or "").upper() != row["evidence_level"]:
                    continue
                valid_rows.append(row)
            except Exception:
                continue

        if not missing:
            for row in valid_rows:
                candidate = _LEVEL_TO_MATURITY[row["evidence_level"]]
                if _MATURITY_ORDER[candidate] > _MATURITY_ORDER[maturity]:
                    maturity = candidate
            if maturity is Maturity.M3_INTEGRATED:
                status = CapabilityStatus.INTEGRATED
            elif maturity is Maturity.M4_RUNTIME_VERIFIED:
                status = CapabilityStatus.RUNTIME_VERIFIED
            elif maturity is Maturity.M5_RECOVERY_VERIFIED:
                status = CapabilityStatus.RECOVERY_VERIFIED

        # Proofs for another SHA stay historical, never support this snapshot.
        stale = self.db.query(
            "SELECT COUNT(*) AS n FROM capability_proofs WHERE capability_id=? AND tested_sha<>?",
            (capability_id, str(tested_sha)),
        )[0]["n"]
        if stale:
            limitations.append(f"{stale} historical proof(s) belong to other SHA(s) and were ignored")

        if missing and valid_rows:
            status = CapabilityStatus.DEGRADED
            limitations.append("evidence exists but current implementation binding is unavailable")

        return {
            "capability_id": capability_id,
            "reference_version": ref_version,
            "status": status.value,
            "maturity": maturity.value,
            "implementation_bindings": modules,
            "missing_bindings": missing,
            "tested_sha": str(tested_sha),
            "evidence_refs": [r["evidence_id"] for r in valid_rows],
            "last_runtime_verified_at": max(
                (r["recorded_at"] for r in valid_rows if r["evidence_level"] in {"C", "D"}),
                default=None,
            ),
            "last_recovery_verified_at": max(
                (r["recorded_at"] for r in valid_rows if r["evidence_level"] == "D"),
                default=None,
            ),
            "limitations": limitations,
        }

    def add_blindspot(
        self,
        *,
        capability_id: str,
        unobservable: str,
        reason: str,
        affected_claims: list[str] | tuple[str, ...] = (),
        needed_evidence: list[str] | tuple[str, ...] = (),
        needed_instrumentation: list[str] | tuple[str, ...] = (),
    ) -> str:
        blindspot_id = new_id("blind")
        with self.db.transaction() as conn:
            conn.execute(
                """INSERT INTO self_model_blindspots
                   (blindspot_id,capability_id,unobservable,reason,affected_claims_json,
                    needed_evidence_json,needed_instrumentation_json,status,created_at)
                   VALUES (?,?,?,?,?,?,?,'OPEN',?)""",
                (
                    blindspot_id,
                    capability_id,
                    str(unobservable),
                    str(reason),
                    json.dumps(list(affected_claims), sort_keys=True),
                    json.dumps(list(needed_evidence), sort_keys=True),
                    json.dumps(list(needed_instrumentation), sort_keys=True),
                    now_utc_iso(),
                ),
            )
        return blindspot_id

    def list_blindspots(self, capability_id: str | None = None) -> list[dict]:
        if capability_id is None:
            return self.db.query("SELECT * FROM self_model_blindspots ORDER BY created_at")
        return self.db.query(
            "SELECT * FROM self_model_blindspots WHERE capability_id=? ORDER BY created_at",
            (capability_id,),
        )

    def close(self) -> None:
        self.db.close()
