"""Fail-closed contracts for AutoFix property validation."""
from __future__ import annotations

from scp.autofix.property_validator import PropertySpec, validate_fix


def _always_true(_value):
    return True


def test_compile_failure_is_unverified() -> None:
    result = validate_fix(
        "def f(value):\n    return value\n",
        "not valid python !!!\n",
        None,
        PropertySpec(invariants=[_always_true], strategy="int"),
        n=3,
    )
    assert result.ok is False
    assert result.reason.startswith("unverified")


def test_missing_invariants_are_unverified() -> None:
    result = validate_fix(
        "def f(value):\n    return value\n",
        "def f(value):\n    return value\n",
        None,
        PropertySpec(invariants=[], strategy="int"),
        n=3,
    )
    assert result.ok is False
    assert "no invariants" in result.reason


def test_unknown_strategy_is_unverified() -> None:
    result = validate_fix(
        "def f(value):\n    return value\n",
        "def f(value):\n    return value\n",
        None,
        PropertySpec(invariants=[_always_true], strategy="does-not-exist"),
        n=3,
    )
    assert result.ok is False
    assert "strategy unavailable" in result.reason


def test_zero_requested_trials_are_unverified() -> None:
    result = validate_fix(
        "def f(value):\n    return value\n",
        "def f(value):\n    return value\n",
        None,
        PropertySpec(invariants=[_always_true], strategy="int"),
        n=0,
    )
    assert result.ok is False
    assert result.inputs_tested == 0
    assert "no executable inputs" in result.reason



def test_realtime_verifier_requires_a_baseline_and_inputs() -> None:
    from scp.autofix.realtime_verifier import InvariantSpec, RealTimeVerifier

    verifier = RealTimeVerifier(InvariantSpec(test_inputs=[1], max_inputs=1))
    new_function = verifier.check_patch(
        "def old(value):\n    return value\n",
        "def new(value):\n    return value\n",
        func_name="new",
    )
    assert new_function.ok is False
    assert "unverified" in new_function.reason

    no_inputs = RealTimeVerifier(InvariantSpec(test_inputs=[], max_inputs=0)).check_patch(
        "def f(value):\n    return value\n",
        "def f(value):\n    return value\n",
        func_name="f",
    )
    assert no_inputs.ok is False
    assert "no executable" in no_inputs.reason


def test_realtime_verifier_rejects_ambiguous_callable_target() -> None:
    from scp.autofix.realtime_verifier import RealTimeVerifier

    result = RealTimeVerifier().check_patch(
        "def a(value):\n    return value\n\ndef b(value):\n    return value\n",
        "def a(value):\n    return value\n\ndef b(value):\n    return value\n",
    )
    assert result.ok is False
    assert "multiple callables" in result.reason
