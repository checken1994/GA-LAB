"""Zero-Cost LLM wall (26-P0.13/14).

Authorization rule in free-only mode:
    fresh proof AND prompt_price == 0 AND completion_price == 0
    AND data-class/provider policy allows the request -> ALLOW_FREE
Everything else fails closed before the network driver.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from enum import Enum
from pathlib import Path

from scp.contracts.data_class import DataClass
from scp.contracts.ids import new_id
from scp.contracts.time import now_utc_iso
from scp.governance.privacy import PrivacyWriteGate
from scp.persistence import FoundationDB


class ZeroCostDecision(str, Enum):
    ALLOW_FREE = "ALLOW_FREE"
    DENY_PAID = "DENY_PAID"
    DENY_UNKNOWN_PRICE = "DENY_UNKNOWN_PRICE"
    DENY_STALE_PRICE = "DENY_STALE_PRICE"
    DENY_DATA_CLASS = "DENY_DATA_CLASS"


class ZeroCostDenied(RuntimeError):
    def __init__(self, decision: ZeroCostDecision):
        super().__init__(decision.value)
        self.decision = decision


def _decimal_price(value: object) -> Decimal:
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ValueError(f"invalid price value: {value!r}") from exc


def _parse_time(value: str) -> datetime:
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("pricing proof time must be timezone-aware")
    return parsed.astimezone(timezone.utc)


_ZERO_COST_MIGRATIONS = [
    (
        "0001_zero_cost_proofs",
        [
            """CREATE TABLE IF NOT EXISTS pricing_proofs (
                   proof_id TEXT PRIMARY KEY,
                   provider TEXT NOT NULL,
                   model TEXT NOT NULL,
                   prompt_price TEXT NOT NULL,
                   completion_price TEXT NOT NULL,
                   currency TEXT NOT NULL DEFAULT 'USD',
                   catalog_hash TEXT NOT NULL,
                   evidence_id TEXT,
                   observed_at TEXT NOT NULL,
                   expires_at TEXT NOT NULL,
                   active INTEGER NOT NULL DEFAULT 1,
                   metadata_json TEXT NOT NULL DEFAULT '{}')""",
            "CREATE INDEX IF NOT EXISTS idx_pricing_proof_model ON pricing_proofs(provider,model,observed_at)",
            """CREATE TABLE IF NOT EXISTS zero_cost_outbound_events (
                   event_id TEXT PRIMARY KEY,
                   provider TEXT NOT NULL,
                   model TEXT NOT NULL,
                   task_class TEXT,
                   data_class TEXT,
                   proof_id TEXT,
                   decision TEXT NOT NULL,
                   shadow INTEGER NOT NULL DEFAULT 0,
                   actual_sent INTEGER NOT NULL DEFAULT 0,
                   created_at TEXT NOT NULL)""",
            """CREATE TRIGGER IF NOT EXISTS pricing_proof_no_update
                   BEFORE UPDATE ON pricing_proofs
                   BEGIN SELECT RAISE(ABORT, 'pricing proof is immutable'); END;""",
        ],
    ),
]


@dataclass(frozen=True)
class PricingProof:
    proof_id: str
    provider: str
    model: str
    prompt_price: Decimal
    completion_price: Decimal
    currency: str
    catalog_hash: str
    evidence_id: str | None
    observed_at: str
    expires_at: str
    active: bool


@dataclass(frozen=True)
class ZeroCostRequest:
    provider: str
    model: str
    task_class: str
    data_class: DataClass | str | None


class PricingProofStore:
    def __init__(self, db_path: str | Path) -> None:
        self.db = FoundationDB(db_path, _ZERO_COST_MIGRATIONS)

    def record(
        self,
        *,
        provider: str,
        model: str,
        prompt_price: object,
        completion_price: object,
        catalog_hash: str,
        observed_at: str,
        expires_at: str,
        evidence_id: str | None,
        currency: str = "USD",
        metadata: dict | None = None,
    ) -> PricingProof:
        prompt = _decimal_price(prompt_price)
        completion = _decimal_price(completion_price)
        # Parsing both timestamps at write time prevents malformed/stale proof
        # records from reaching the authorization path.
        if _parse_time(expires_at) <= _parse_time(observed_at):
            raise ValueError("pricing proof expires_at must be after observed_at")
        proof_id = new_id("price")
        with self.db.transaction() as conn:
            conn.execute(
                """INSERT INTO pricing_proofs
                   (proof_id,provider,model,prompt_price,completion_price,currency,catalog_hash,
                    evidence_id,observed_at,expires_at,active,metadata_json)
                   VALUES (?,?,?,?,?,?,?,?,?,?,1,?)""",
                (
                    proof_id,
                    str(provider).strip().lower(),
                    str(model).strip(),
                    str(prompt),
                    str(completion),
                    str(currency).upper(),
                    str(catalog_hash),
                    evidence_id,
                    observed_at,
                    expires_at,
                    json.dumps(metadata or {}, ensure_ascii=False, sort_keys=True),
                ),
            )
        return self.get(proof_id)

    def get(self, proof_id: str) -> PricingProof:
        rows = self.db.query("SELECT * FROM pricing_proofs WHERE proof_id=?", (proof_id,))
        if not rows:
            raise KeyError(proof_id)
        row = rows[0]
        return PricingProof(
            proof_id=row["proof_id"],
            provider=row["provider"],
            model=row["model"],
            prompt_price=_decimal_price(row["prompt_price"]),
            completion_price=_decimal_price(row["completion_price"]),
            currency=row["currency"],
            catalog_hash=row["catalog_hash"],
            evidence_id=row["evidence_id"],
            observed_at=row["observed_at"],
            expires_at=row["expires_at"],
            active=bool(row["active"]),
        )

    def latest(self, provider: str, model: str) -> PricingProof | None:
        rows = self.db.query(
            """SELECT proof_id FROM pricing_proofs
               WHERE provider=? AND model=? AND active=1
               ORDER BY observed_at DESC, proof_id DESC LIMIT 1""",
            (str(provider).strip().lower(), str(model).strip()),
        )
        return self.get(rows[0]["proof_id"]) if rows else None

    def record_event(
        self,
        request: ZeroCostRequest,
        *,
        decision: ZeroCostDecision,
        proof_id: str | None,
        shadow: bool,
        actual_sent: bool,
    ) -> str:
        event_id = new_id("zcevt")
        data_class = request.data_class.value if isinstance(request.data_class, DataClass) else (
            str(request.data_class).upper() if request.data_class is not None else None
        )
        with self.db.transaction() as conn:
            conn.execute(
                """INSERT INTO zero_cost_outbound_events
                   (event_id,provider,model,task_class,data_class,proof_id,decision,shadow,actual_sent,created_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?)""",
                (
                    event_id,
                    request.provider,
                    request.model,
                    request.task_class,
                    data_class,
                    proof_id,
                    decision.value,
                    1 if shadow else 0,
                    1 if actual_sent else 0,
                    now_utc_iso(),
                ),
            )
        return event_id

    def close(self) -> None:
        self.db.close()


class ZeroCostGuard:
    def __init__(
        self,
        proof_store: PricingProofStore,
        *,
        privacy_gate: PrivacyWriteGate | None = None,
        require_evidence_id: bool = True,
    ) -> None:
        self.proof_store = proof_store
        self.privacy_gate = privacy_gate
        self.require_evidence_id = bool(require_evidence_id)

    @staticmethod
    def validate_free_only_config(env: dict[str, str] | None = None) -> None:
        source = os.environ if env is None else env
        mode = str(source.get("SCP_LLM_COST_MODE", "free_only")).strip().lower()
        if mode != "free_only":
            raise ValueError("P0 zero-cost wall requires SCP_LLM_COST_MODE=free_only")
        if str(source.get("SCP_ALLOW_PAID_FALLBACK", "0")).strip().lower() not in {"0", "false", "no", "off", ""}:
            raise ValueError("paid fallback is forbidden in free_only mode")
        if _decimal_price(source.get("SCP_MAX_LLM_COST_USD", "0")) != Decimal("0"):
            raise ValueError("SCP_MAX_LLM_COST_USD must be exactly 0")
        if str(source.get("SCP_FREE_REQUIRE_PRICE_PROOF", "1")).strip().lower() not in {"1", "true", "yes", "on"}:
            raise ValueError("fresh price proof cannot be disabled in free_only mode")
        if str(source.get("SCP_FREE_FAIL_IF_PRICE_UNKNOWN", "1")).strip().lower() not in {"1", "true", "yes", "on"}:
            raise ValueError("unknown price must fail closed in free_only mode")

    def evaluate(self, request: ZeroCostRequest, *, now: datetime | None = None) -> tuple[ZeroCostDecision, PricingProof | None]:
        proof = self.proof_store.latest(request.provider, request.model)
        if proof is None:
            return ZeroCostDecision.DENY_UNKNOWN_PRICE, None
        if self.require_evidence_id and not proof.evidence_id:
            return ZeroCostDecision.DENY_UNKNOWN_PRICE, proof
        current = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
        if _parse_time(proof.expires_at) <= current:
            return ZeroCostDecision.DENY_STALE_PRICE, proof
        if proof.prompt_price != Decimal("0") or proof.completion_price != Decimal("0"):
            return ZeroCostDecision.DENY_PAID, proof
        if self.privacy_gate is not None:
            data_class = request.data_class if request.data_class is not None else DataClass.SENSITIVE
            if not self.privacy_gate.provider_allowed(data_class):
                return ZeroCostDecision.DENY_DATA_CLASS, proof
        return ZeroCostDecision.ALLOW_FREE, proof

    def authorize(self, request: ZeroCostRequest, *, shadow: bool = False) -> PricingProof | None:
        decision, proof = self.evaluate(request)
        if shadow:
            self.proof_store.record_event(
                request,
                decision=decision,
                proof_id=proof.proof_id if proof else None,
                shadow=True,
                actual_sent=False,
            )
            return proof
        if decision is not ZeroCostDecision.ALLOW_FREE:
            self.proof_store.record_event(
                request,
                decision=decision,
                proof_id=proof.proof_id if proof else None,
                shadow=False,
                actual_sent=False,
            )
            raise ZeroCostDenied(decision)
        return proof

    def record_sent(self, request: ZeroCostRequest, proof: PricingProof | None, *, shadow: bool = False) -> str:
        decision, _ = self.evaluate(request)
        return self.proof_store.record_event(
            request,
            decision=decision,
            proof_id=proof.proof_id if proof else None,
            shadow=shadow,
            actual_sent=True,
        )
