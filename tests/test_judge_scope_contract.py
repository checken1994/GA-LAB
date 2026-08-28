"""Contract guards for GA-LAB monolith state propagation."""
from pathlib import Path

SOURCE = Path(__file__).resolve().parents[1] / "scp" / "runtime" / "judge_parts" / "judgecore_mixin.py"


def test_kb_short_circuit_uses_initialized_state():
    source = SOURCE.read_text(encoding="utf-8")
    assert "_kb_sc_verdict = locals().get" not in source
    assert "_kb_sc_answer = locals().get" not in source
    assert "_kb_sc_conf = locals().get" not in source
    assert "_kb_sc_verdict = verdict_type" in source
    assert "_kb_sc_answer = final_answer" in source
    assert "_kb_sc_conf = confidence" in source


def test_speculative_evidence_has_explicit_lifetime():
    source = SOURCE.read_text(encoding="utf-8")
    assert "verdict_evidence_spec = None" in source
    assert "in dir() and verdict_type == \"SPECULATIVE\"" not in source
    assert "verdict_evidence_spec is not None and verdict_type == \"SPECULATIVE\"" in source
