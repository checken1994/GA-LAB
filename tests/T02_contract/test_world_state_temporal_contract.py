import pytest

from scp.world_state import EntityEventAuthority, TemporalAuthority, WorldStateProjection

# ==============================================================================
# T02 - WORLD-STATE TEMPORAL CONTRACT (X08: CE-X08-01) - GREEN over the real
# bitemporal implementation: valid_time vs system_time are separate axes,
# append-only history, PREDICTED never becomes OBSERVED by its own predictor.
# ==============================================================================


@pytest.fixture()
def authority(tmp_path):
    return TemporalAuthority(tmp_path / "world.sqlite3")


def test_valid_time_and_system_time_are_recorded_separately_and_append_only(authority):
    first = authority.record_observation(
        subject="sensor:water-a", predicate="reading", value={"ppm": 40},
        valid_time="2026-09-01T08:00:00+00:00",
        evidence_refs=["evidence:1"], actor_id="ingest-1")
    second = authority.record_observation(
        subject="sensor:water-a", predicate="reading", value={"ppm": 55},
        valid_time="2026-09-01T09:00:00+00:00",
        evidence_refs=["evidence:2"], actor_id="ingest-1")

    assert first["valid_time"] != second["valid_time"]
    assert first["system_time"] <= second["system_time"]
    history = authority.history("sensor:water-a")
    assert len(history) == 2, "append-only log must retain every observation"
    assert {h["value_json"] for h in history} == {'{"ppm": 40}', '{"ppm": 55}'}


def test_observation_without_evidence_refs_is_refused(authority):
    with pytest.raises(Exception, match="evidence_refs"):
        authority.record_observation(
            subject="sensor:x", predicate="reading", value={"v": 1},
            valid_time="2026-09-01T08:00:00+00:00",
            evidence_refs=[], actor_id="ingest-1")


def test_correction_supersedes_and_never_rewrites_history(authority):
    original = authority.record_observation(
        subject="sensor:x", predicate="reading", value={"v": 1},
        valid_time="2026-09-01T08:00:00+00:00",
        evidence_refs=["evidence:1"], actor_id="ingest-1")
    corrected = authority.correct(original["assertion_id"], new_value={"v": 2},
                                  actor_id="ingest-1", evidence_refs=["evidence:2"])
    assert corrected["assertion_id"] != original["assertion_id"]
    history = authority.history("sensor:x")
    assert len(history) == 2
    superseded = [h for h in history if h["assertion_id"] == original["assertion_id"]][0]
    assert superseded["superseded_by"] == corrected["assertion_id"]


def test_predictor_can_never_promote_its_own_forecast_to_observed(authority):
    prediction = authority.record_prediction(
        subject="grid:district-a", predicate="outage", value={"likely": True},
        valid_time="2026-09-02T18:00:00+00:00", predictor_id="forecaster-1")

    with pytest.raises(Exception, match="predictor"):
        authority.promote_to_observed(prediction["assertion_id"],
                                      evidence_refs=["evidence:1"],
                                      resolver_id="forecaster-1")

    resolved = authority.promote_to_observed(prediction["assertion_id"],
                                             evidence_refs=["evidence:9"],
                                             resolver_id="reality-observer-1")
    assert resolved["epistemic_status"] == "OBSERVED"
    history = authority.history("grid:district-a")
    statuses = {h["epistemic_status"] for h in history}
    assert statuses == {"PREDICTED", "OBSERVED"}, "prediction history must survive resolution"


def test_projection_rebuild_is_deterministic_and_respects_supersede(authority):
    projection = WorldStateProjection(authority)
    a = authority.record_observation(
        subject="sensor:x", predicate="reading", value={"v": 1},
        valid_time="2026-09-01T08:00:00+00:00",
        evidence_refs=["evidence:1"], actor_id="ingest-1")
    authority.correct(a["assertion_id"], new_value={"v": 2},
                      actor_id="ingest-1", evidence_refs=["evidence:2"])

    state_one = projection.rebuild()
    state_two = projection.rebuild()
    assert state_one == state_two, "projection rebuild must be deterministic"
    readings = state_one["sensor:x"]["reading"]
    assert len(readings) == 1, "superseded assertion must not appear as current state"
    assert readings[0]["value"] == {"v": 2}


def test_entity_resolution_links_identity_and_preserves_lineage(tmp_path):
    authority = TemporalAuthority(tmp_path / "world.sqlite3")
    entities = EntityEventAuthority(authority)
    entities.record_event(entity_id="report-1", event_kind="complaint",
                          payload={"text": "water smells odd"}, valid_time="2026-09-01T08:00:00+00:00",
                          evidence_refs=["evidence:1"], actor_id="ingest-1")
    entities.record_event(entity_id="report-2", event_kind="complaint",
                          payload={"text": "same street, same smell"}, valid_time="2026-09-01T09:00:00+00:00",
                          evidence_refs=["evidence:2"], actor_id="ingest-1")

    link = entities.link_identity("report-1", "report-2")
    assert link["relation"] == "SAME_ENTITY"
    history = entities.event_history("report-1")
    subjects = {h["subject"] for h in history}
    assert subjects == {"entity:report-1", "entity:report-2"}, (
        "linked history must retain both original lineage identities"
    )
