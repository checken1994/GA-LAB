import importlib.util
import sys
from pathlib import Path

import pytest


POLICY_SOURCE = Path(__file__).resolve().parents[1] / "scp" / "autofix" / "policy_gate.py"


def _load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _assert_constitutional_block(module, tmp_path: Path) -> None:
    gate = module.PolicyGate(
        audit_log=module.ImmutableAuditLog(str(tmp_path / "policy.jsonl"))
    )
    decision = gate.evaluate_fix(
        module.PolicyFix(
            fix_id="synthetic-kill-case",
            patch="requests.get(url, verify=False)",
            bug_file="fixture.py",
        )
    )
    assert decision.allowed is False
    assert decision.severity == "BLOCK"
    assert "verify_false_tls" in decision.blocked_patterns


def test_live_constitutional_block_contract(tmp_path) -> None:
    module = _load_module(POLICY_SOURCE, "policy_gate_live_contract")
    _assert_constitutional_block(module, tmp_path)


def test_kill_to_pass_mutation_is_caught(tmp_path) -> None:
    original = POLICY_SOURCE.read_text(encoding="utf-8")
    needle = "decision = PolicyDecision(\n                        allowed=False,"
    assert needle in original
    mutant_source = original.replace(needle, needle.replace("False", "True"), 1)
    mutant_path = tmp_path / "policy_gate_mutant.py"
    mutant_path.write_text(mutant_source, encoding="utf-8")
    mutant = _load_module(mutant_path, "policy_gate_kill_to_pass_mutant")

    # The assertion contract must fail against a mutant that silently turns a
    # constitutional BLOCK into ALLOW. This is a killed mutant, not a claim
    # that the production code was dynamically modified.
    with pytest.raises(AssertionError):
        _assert_constitutional_block(mutant, tmp_path / "mutant")
