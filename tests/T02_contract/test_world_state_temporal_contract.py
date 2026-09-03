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


def test_same_name_different_lineage_never_silently_merged(tmp_path):
    authority = TemporalAuthority(tmp_path / "world.sqlite3")
    entities = EntityEventAuthority(authority)
    entities.record_event(entity_id="facility-alpha", event_kind="registration",
                          payload={"name": "Central Treatment Plant", "location": "District 1"},
                          valid_time="2026-09-01T08:00:00+00:00",
                          evidence_refs=["evidence:alpha"], actor_id="ingest-1")
    entities.record_event(entity_id="facility-beta", event_kind="registration",
                          payload={"name": "Central Treatment Plant", "location": "District 9"},
                          valid_time="2026-09-01T08:30:00+00:00",
                          evidence_refs=["evidence:beta"], actor_id="ingest-1")

    # Without explicit link_identity, identical name string does NOT merge entities
    assert entities.linked_ids("facility-alpha") == {"facility-alpha"}
    assert entities.linked_ids("facility-beta") == {"facility-beta"}
    hist_alpha = entities.event_history("facility-alpha")
    hist_beta = entities.event_history("facility-beta")
    assert len(hist_alpha) == 1 and hist_alpha[0]["subject"] == "entity:facility-alpha"
    assert len(hist_beta) == 1 and hist_beta[0]["subject"] == "entity:facility-beta"

    projection = WorldStateProjection(authority)
    state = projection.rebuild()
    assert "entity:facility-alpha" in state and "entity:facility-beta" in state
    assert state["entity:facility-alpha"]["event:registration"][0]["value"]["location"] == "District 1"
    assert state["entity:facility-beta"]["event:registration"][0]["value"]["location"] == "District 9"


def test_temporal_authority_persistence_across_db_restart(tmp_path):
    db_path = tmp_path / "persisted_world.sqlite3"
    authority_1 = TemporalAuthority(db_path)
    obs = authority_1.record_observation(
        subject="sensor:chlorine", predicate="ppm", value={"reading": 1.2},
        valid_time="2026-09-01T10:00:00+00:00", evidence_refs=["evidence:sensor-1"],
        actor_id="ingest-1")
    authority_1.correct(obs["assertion_id"], new_value={"reading": 1.5},
                        actor_id="ingest-1", evidence_refs=["evidence:recalibrated"])
    proj_1 = WorldStateProjection(authority_1)
    state_before_restart = proj_1.rebuild()

    # Restart simulated: close connection and instantiate fresh authority
    del authority_1
    del proj_1

    authority_2 = TemporalAuthority(db_path)
    proj_2 = WorldStateProjection(authority_2)
    state_after_restart = proj_2.rebuild()

    assert state_before_restart == state_after_restart, "projection after restart must be identical"
    raw_history = authority_2.history("sensor:chlorine")
    assert len(raw_history) == 2, "full append log must survive DB restart"
    assert any(h["superseded_by"] is not None for h in raw_history)


def test_change_detection_tracks_state_deltas_without_mutating_past(authority):
    t1 = "2026-09-01T08:00:00+00:00"
    t2 = "2026-09-01T12:00:00+00:00"
    authority.record_observation(
        subject="water:reservoir-1", predicate="turbidity", value={"ntu": 3.5},
        valid_time=t1, evidence_refs=["evidence:t1"], actor_id="sensor-auto")
    authority.record_observation(
        subject="water:reservoir-1", predicate="turbidity", value={"ntu": 18.2},
        valid_time=t2, evidence_refs=["evidence:t2"], actor_id="sensor-auto")

    history = authority.history("water:reservoir-1")
    assert len(history) == 2
    assert history[0]["valid_time"] == t1
    assert history[1]["valid_time"] == t2
    # Verify both observations coexist with differing valid_time and values
    v1 = __import__("json").loads(history[0]["value_json"])
    v2 = __import__("json").loads(history[1]["value_json"])
    assert v1["ntu"] == 3.5
    assert v2["ntu"] == 18.2

    projection = WorldStateProjection(authority)
    current = projection.current("water:reservoir-1", "turbidity")
    assert current is not None
    assert current["value"]["ntu"] == 18.2
    assert current["valid_time"] == t2
