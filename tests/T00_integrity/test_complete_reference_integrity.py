import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from tools.verify_complete_scp_reference import validate_reference

# ==============================================================================
# T00 - COMPLETE SCP REFERENCE INTEGRITY (26-P0.1)
# ==============================================================================
# The reference defines WHAT Complete SCP means and must stay free of
# implementation bindings (the "Complete SCP requires EpistemicScanner class"
# harness failure class). T00 enforces that the shipped reference itself can
# never reintroduce that failure mode.
# ==============================================================================

SPEC_PATH = ROOT / "spec" / "complete_scp_reference.yaml"


def test_shipped_reference_passes_fail_closed_validator():
    assert SPEC_PATH.is_file(), "spec/complete_scp_reference.yaml is a P0 artifact - it must exist"
    errors = validate_reference(SPEC_PATH)
    assert not errors, f"Complete SCP reference violates its own contract: {errors}"


def test_reference_never_binds_implementation_symbols():
    import re

    raw = SPEC_PATH.read_text(encoding="utf-8")
    offenders = [
        (number, line.strip())
        for number, line in enumerate(raw.splitlines(), start=1)
        if re.match(r"^\s*(class|method|module):\s*\S", line)
    ]
    assert not offenders, (
        f"Reference binds implementation details (must live in spec/implementation_bindings.yaml): {offenders}"
    )


def test_validator_rejects_a_reference_that_requires_a_class():
    """The exact historical failure mode (invented-class reference) must be caught."""
    import tempfile

    poisoned = SPEC_PATH.read_text(encoding="utf-8").replace(
        "  epistemic.evidence:\n", "  epistemic.evidence:\n    class: EpistemicScanner\n", 1
    )
    with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False, encoding="utf-8") as handle:
        handle.write(poisoned)
        poisoned_path = handle.name
    errors = validate_reference(Path(poisoned_path))
    assert any("must not bind implementations" in error for error in errors), (
        f"Validator failed to catch an implementation-bound reference: {errors}"
    )
