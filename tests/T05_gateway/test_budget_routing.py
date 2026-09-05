import pytest

from scp.core.budget_engine import order_tiers, route_tier


def test_budget_reorders_verified_free_only(monkeypatch):
    """Free-only policy removes paid tiers even for hard/autofix work."""
    monkeypatch.setenv("SCP_LLM_COST_MODE", "free_only")
    monkeypatch.setenv("SCP_BUDGET_TIER_AUTOFIX", "paid_first")

    assert route_tier("security architecture deadlock", task="autofix") == "free_first"
    assert order_tiers("security architecture deadlock", task="autofix") == ["free"]
    assert "paid" not in order_tiers("easy typo", task="default")


@pytest.mark.parametrize("mode", ["paid", "auto", "unknown", ""])
def test_invalid_cost_mode_cannot_create_paid_tier(monkeypatch, mode):
    monkeypatch.setenv("SCP_LLM_COST_MODE", mode)
    with pytest.raises(ValueError, match="free_only"):
        order_tiers("hard task", "autofix")
