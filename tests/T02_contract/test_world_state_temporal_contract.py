import pytest

# ==============================================================================
# T02 - WORLD-STATE TEMPORAL CONTRACT (X08: CE-X08-01 gates [T02,T06,T09,T10])
# ==============================================================================
# Bitemporal world state: Valid Time (when it was true in the world) and
# System Time (when SCP learned it) are separate axes. Observations are
# append-only; history is reconstructable; predictions never overwrite
# observations; entity identity survives resolution.
#
# Status: no world-state authority exists in production yet
# -> BLOCKED_MISSING_IMPLEMENTATION (red by design, drives implementation).
# ==============================================================================


def test_world_state_temporal_authority_exists_and_is_bitemporal():
    try:
        from scp.world_state.entity_event_authority import EntityEventAuthority  # noqa: F401
        from scp.world_state.temporal_authority import TemporalAuthority  # noqa: F401
        from scp.world_state.world_state_projection import WorldStateProjection  # noqa: F401
    except ImportError as exc:
        pytest.fail(
            "PRODUCT_BLOCKED: the X08 World-State / Temporal Model subsystem is not "
            f"implemented (import failed: {exc}). Required production authorities: "
            "EntityEventAuthority, TemporalAuthority, WorldStateProjection. Contract "
            "each must satisfy once implemented: (1) every observation is appended "
            "with separate valid_time and system_time - no overwrite, no update or "
            "delete of past rows; (2) full history is reconstructable from the "
            "append log alone at any system-time cutoff; (3) a correction is a NEW "
            "assertion that supersedes, never a rewrite; (4) predictions/forecasts "
            "are stored with epistemic status PREDICTED and can never be promoted "
            "to OBSERVED by the same authority that made them; (5) entity resolution "
            "may merge records only by linking identities - original lineage refs "
            "must survive; (6) projection rebuild from the log must reproduce the "
            "same world state (journal-authoritative, same rule as TaskKernel)."
        )


def test_forecast_result_can_never_be_written_as_observation():
    """Prediction-as-observation is a forbidden edge (X08 global invariants)."""
    pytest.fail(
        "PRODUCT_BLOCKED: no machine-enforced gate exists that rejects a write of "
        "epistemic status PREDICTED into an OBSERVED slot of the world state. When "
        "the temporal authority is implemented, its write API must carry an "
        "epistemic-status parameter and refuse PREDICTED->OBSERVED transitions "
        "originating from the predictor itself."
    )
