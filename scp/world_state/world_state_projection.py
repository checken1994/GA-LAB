"""World-State Projection (X08): deterministic rebuild from the append log.

Rebuilding at the same cutoffs must produce the identical state - the journal
is authoritative, the projection is derived (same rule as TaskKernel)."""
from __future__ import annotations


class WorldStateProjection:
    def __init__(self, temporal) -> None:
        self.temporal = temporal

    def rebuild(self, *, as_of_system_time: str | None = None) -> dict:
        rows = self.temporal.db.query(
            "SELECT * FROM world_assertions ORDER BY system_time, assertion_id")
        state: dict = {}
        for row in rows:
            if as_of_system_time and row["system_time"] > as_of_system_time:
                continue
            if row["superseded_by"]:
                continue  # superseded assertions are history, not current state
            subject = row["subject"]
            state.setdefault(subject, {}).setdefault(row["predicate"], []).append({
                "assertion_id": row["assertion_id"],
                "value": __import__("json").loads(row["value_json"]),
                "epistemic_status": row["epistemic_status"],
                "valid_time": row["valid_time"],
                "system_time": row["system_time"],
            })
        return state

    def current(self, subject: str, predicate: str) -> dict | None:
        state = self.rebuild()
        entries = state.get(subject, {}).get(predicate) or []
        return entries[-1] if entries else None
