"""Temporal Authority (X08): bitemporal world assertions.

Contract (CE-X08-01):
  - every assertion is APPENDED with separate valid_time (when it was true in
    the world) and system_time (when SCP learned it) - no update, no delete;
  - epistemic status is explicit: OBSERVED / INFERRED / PREDICTED;
  - a PREDICTED assertion can never be promoted to OBSERVED by the predictor
    that made it - resolution requires evidence refs from a different actor;
  - history is fully reconstructable from the append log.
"""
from __future__ import annotations

import sqlite3
import uuid
from pathlib import Path

from scp.contracts.time import now_utc_iso, parse_utc_iso
from scp.persistence import FoundationDB

_MIGRATIONS = [
    ("0001_world_assertions", [
        """CREATE TABLE IF NOT EXISTS world_assertions (
               assertion_id TEXT PRIMARY KEY,
               subject TEXT NOT NULL,
               predicate TEXT NOT NULL,
               value_json TEXT NOT NULL,
               epistemic_status TEXT NOT NULL CHECK (epistemic_status IN ('OBSERVED','INFERRED','PREDICTED')),
               valid_time TEXT NOT NULL,
               system_time TEXT NOT NULL,
               actor_id TEXT NOT NULL,
               evidence_refs_json TEXT NOT NULL,
               superseded_by TEXT)""",
        """CREATE TRIGGER IF NOT EXISTS world_assertions_no_update
               BEFORE UPDATE ON world_assertions
               FOR EACH ROW
               WHEN OLD.subject IS NOT NEW.subject
                 OR OLD.predicate IS NOT NEW.predicate
                 OR OLD.value_json IS NOT NEW.value_json
                 OR OLD.epistemic_status IS NOT NEW.epistemic_status
                 OR OLD.valid_time IS NOT NEW.valid_time
                 OR OLD.system_time IS NOT NEW.system_time
                 OR OLD.actor_id IS NOT NEW.actor_id
                 OR OLD.evidence_refs_json IS NOT NEW.evidence_refs_json
                 OR (OLD.superseded_by IS NOT NULL AND OLD.superseded_by IS NOT NEW.superseded_by)
               BEGIN
                   SELECT RAISE(ABORT, 'immutable core fields are append-only - only superseded_by lifecycle is writable');
               END;""",
        """CREATE TRIGGER IF NOT EXISTS world_assertions_no_delete
               BEFORE DELETE ON world_assertions
               BEGIN
                   SELECT RAISE(ABORT, 'world assertions are append-only');
               END;""",
        """CREATE TABLE IF NOT EXISTS identity_links (
               link_id TEXT PRIMARY KEY,
               entity_a TEXT NOT NULL,
               entity_b TEXT NOT NULL,
               relation TEXT NOT NULL,
               created_at TEXT NOT NULL)""",
    ]),
]


class WorldStateError(RuntimeError):
    pass


class TemporalAuthority:
    def __init__(self, db_path: str | Path) -> None:
        self.db = FoundationDB(db_path, _MIGRATIONS)

    def record_observation(self, *, subject: str, predicate: str, value: dict,
                           valid_time: str, evidence_refs, actor_id: str) -> dict:
        """OBSERVED assertions require independent evidence references."""
        if not evidence_refs:
            raise WorldStateError(
                "OBSERVED assertion requires evidence_refs - unaudited world "
                "writes are forbidden"
            )
        return self._append(subject, predicate, value, "OBSERVED", valid_time,
                            actor_id, list(evidence_refs))

    def record_prediction(self, *, subject: str, predicate: str, value: dict,
                          valid_time: str, predictor_id: str) -> dict:
        """PREDICTED assertions are stored as such; see promote_to_observed."""
        return self._append(subject, predicate, value, "PREDICTED", valid_time,
                            predictor_id, [])

    def promote_to_observed(self, assertion_id: str, *, evidence_refs, resolver_id: str) -> dict:
        rows = self.db.query(
            "SELECT * FROM world_assertions WHERE assertion_id=?", (assertion_id,))
        if not rows:
            raise KeyError(assertion_id)
        row = rows[0]
        if row["epistemic_status"] != "PREDICTED":
            raise WorldStateError("only PREDICTED assertions can be resolved")
        if not evidence_refs:
            raise WorldStateError("promotion to OBSERVED requires evidence_refs")
        if row["actor_id"] == resolver_id:
            raise WorldStateError(
                "the predictor can never promote its own prediction to OBSERVED - "
                "resolution requires a different resolver backed by evidence"
            )
        resolved = self._append(row["subject"], row["predicate"],
                                json_loads(row["value_json"]), "OBSERVED",
                                row["valid_time"], resolver_id, list(evidence_refs))
        self.db.execute(
            "UPDATE world_assertions SET superseded_by=? WHERE assertion_id=?",
            (resolved["assertion_id"], assertion_id))
        self.db._conn.commit()
        return resolved

    def correct(self, assertion_id: str, *, new_value: dict, actor_id: str,
                evidence_refs) -> dict:
        """A correction is a NEW superseding assertion, never a rewrite."""
        rows = self.db.query("SELECT * FROM world_assertions WHERE assertion_id=?", (assertion_id,))
        if not rows:
            raise KeyError(assertion_id)
        old = rows[0]
        corrected = self._append(old["subject"], old["predicate"], new_value,
                                 old["epistemic_status"], old["valid_time"],
                                 actor_id, list(evidence_refs or []))
        self.db.execute(
            "UPDATE world_assertions SET superseded_by=? WHERE assertion_id=?",
            (corrected["assertion_id"], assertion_id))
        self.db._conn.commit()
        return corrected

    def history(self, subject: str) -> list[dict]:
        return self.db.query(
            "SELECT * FROM world_assertions WHERE subject=? ORDER BY system_time",
            (subject,))

    def _append(self, subject, predicate, value, status, valid_time, actor_id,
                evidence_refs) -> dict:
        parse_utc_iso(valid_time)  # fail-closed on naive/invalid timestamps
        row = {
            "assertion_id": "w_" + uuid.uuid4().hex[:24],
            "subject": subject,
            "predicate": predicate,
            "value_json": json_dumps(value),
            "epistemic_status": status,
            "valid_time": valid_time,
            "system_time": now_utc_iso(),
            "actor_id": actor_id,
            "evidence_refs_json": json_dumps(list(evidence_refs)),
            "superseded_by": None,
        }
        with self.db.transaction() as conn:
            conn.execute(
                """INSERT INTO world_assertions (assertion_id, subject, predicate,
                       value_json, epistemic_status, valid_time, system_time,
                       actor_id, evidence_refs_json, superseded_by)
                   VALUES (:assertion_id,:subject,:predicate,:value_json,
                       :epistemic_status,:valid_time,:system_time,:actor_id,
                       :evidence_refs_json,:superseded_by)""", row)
        return row


def json_dumps(value) -> str:
    import json
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def json_loads(raw: str):
    import json
    return json.loads(raw)
