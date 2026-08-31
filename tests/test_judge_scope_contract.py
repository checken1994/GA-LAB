"""Contract guards for explicit Judge phase state propagation."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PHASES = ROOT / "scp" / "runtime" / "judge_parts" / "phases"
CONTEXT_SOURCE = PHASES / "context.py"
INPUT_SOURCE = PHASES / "phase2_input_detection.py"
BUILD_SOURCE = PHASES / "phase7_build_verdict.py"


def test_kb_short_circuit_uses_initialized_context_state():
    """KB short-circuit must copy named context state after security checks."""
    source = INPUT_SOURCE.read_text(encoding="utf-8")
    assert "locals().get" not in source
    assert "ctx._kb_sc_verdict = ctx.verdict_type" in source
    assert "ctx._kb_sc_answer = ctx.final_answer" in source
    assert "ctx._kb_sc_conf = ctx.confidence" in source
    assert source.index("if ctx.v98_early_fail:") < source.index("ctx._kb_sc_verdict = ctx.verdict_type")


def test_speculative_evidence_has_explicit_context_lifetime():
    """Speculative evidence must be initialized on JudgeContext and consumed explicitly."""
    context_source = CONTEXT_SOURCE.read_text(encoding="utf-8")
    build_source = BUILD_SOURCE.read_text(encoding="utf-8")
    assert "verdict_evidence_spec: Any = None" in context_source
    assert "in dir()" not in build_source
    assert (
        'ctx.verdict_evidence_spec is not None and ctx.verdict_type == "SPECULATIVE"'
        in build_source
    )
