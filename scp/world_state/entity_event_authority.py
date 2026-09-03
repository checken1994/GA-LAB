"""Entity/Event Authority (X08): record events and resolve entity identity
by LINKING - never by destroying original lineage references."""
from __future__ import annotations

import uuid

from scp.contracts.time import now_utc_iso
from scp.world_state.temporal_authority import TemporalAuthority


class EntityEventAuthority:
    def __init__(self, temporal: TemporalAuthority) -> None:
        self.temporal = temporal

    def record_event(self, *, entity_id: str, event_kind: str, payload: dict,
                     valid_time: str, evidence_refs, actor_id: str) -> dict:
        return self.temporal.record_observation(
            subject=f"entity:{entity_id}", predicate=f"event:{event_kind}",
            value=payload, valid_time=valid_time,
            evidence_refs=evidence_refs, actor_id=actor_id,
        )

    def link_identity(self, entity_a: str, entity_b: str, *, relation: str = "SAME_ENTITY") -> dict:
        """Resolve two records into one identity by LINKING. Both original ids
        are retained forever; nothing is merged away."""
        if entity_a == entity_b:
            raise ValueError("self-link is meaningless")
        link_id = "link_" + uuid.uuid4().hex[:24]
        self.temporal.db.execute(
            "INSERT INTO identity_links (link_id, entity_a, entity_b, relation, created_at) VALUES (?,?,?,?,?)",
            (link_id, entity_a, entity_b, relation, now_utc_iso()))
        self.temporal.db._conn.commit()
        return {"link_id": link_id, "entity_a": entity_a, "entity_b": entity_b, "relation": relation}

    def linked_ids(self, entity_id: str) -> set:
        links = self.temporal.db.query(
            "SELECT entity_a, entity_b FROM identity_links WHERE entity_a=? OR entity_b=?",
            (entity_id, entity_id))
        ids = {entity_id}
        changed = True
        while changed:
            changed = False
            for link in links:
                if link["entity_a"] in ids and link["entity_b"] not in ids:
                    ids.add(link["entity_b"]); changed = True
                if link["entity_b"] in ids and link["entity_a"] not in ids:
                    ids.add(link["entity_a"]); changed = True
        return ids

    def event_history(self, entity_id: str) -> list[dict]:
        history = []
        for eid in sorted(self.linked_ids(entity_id)):
            history.extend(self.temporal.history(f"entity:{eid}"))
        history.sort(key=lambda row: row["system_time"])
        return history
