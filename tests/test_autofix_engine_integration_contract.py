from pathlib import Path

from scp.autofix.classifier import BugReport, BugTier
from scp.autofix.engine import AutoFixEngine
from scp.autofix.llm_fix import process_bug_with_llm
from scp.autofix.runner_phases import post_fix_verify


CANONICAL_PATCH = """<<<<<<< SEARCH
def add(a, b):
    return a - b
=======
def add(a, b):
    return a + b
>>>>>>> REPLACE"""

ORIGINAL = "def add(a, b):\n    return a - b\n"


def _bug(path: Path, suggested_fix: str) -> BugReport:
    return BugReport(
        file=str(path),
        line=2,
        bug_type="SimpleImplementationBug",
        description="clear deterministic implementation correction",
        suggested_fix=suggested_fix,
        tier=BugTier.TIER_1_AUTO_FIX,
    )


def test_malformed_deterministic_only_candidate_does_not_write(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    target = tmp_path / "fixture.py"
    target.write_text(ORIGINAL, encoding="utf-8")
    engine = AutoFixEngine(data_dir=str(tmp_path / "data"))

    result = process_bug_with_llm(
        _bug(target, "plain prose without a safe patch marker"),
        engine,
        allow_llm=False,
    )

    assert result["action"] == "skipped"
    assert result["reason"] == "llm_disabled_deterministic_only"
    assert result["llm_generated"] is False
    assert target.read_text(encoding="utf-8") == ORIGINAL


def test_verified_regression_is_rolled_back_and_not_reported_fixed(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    target = tmp_path / "fixture.py"
    target.write_text(ORIGINAL, encoding="utf-8")
    engine = AutoFixEngine(data_dir=str(tmp_path / "data"))
    monkeypatch.setattr(
        engine,
        "_verify_fix",
        lambda filepath, bugs: (False, "synthetic regression detected"),
    )

    result = process_bug_with_llm(_bug(target, CANONICAL_PATCH), engine, allow_llm=False)

    assert result["action"] == "skipped"
    assert result["patched"] is False
    assert "rolled back" in result["reason"]
    assert target.read_text(encoding="utf-8") == ORIGINAL


def test_missing_post_fix_evidence_rolls_back_and_escalates_not_fixed(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.chdir(tmp_path)
    target = tmp_path / "fixture.py"
    target.write_text(ORIGINAL, encoding="utf-8")
    engine = AutoFixEngine(data_dir=str(tmp_path / "data"))
    monkeypatch.setattr(
        engine,
        "_verify_fix",
        lambda filepath, bugs: (True, "synthetic pre-verify passed"),
    )
    monkeypatch.setattr(
        post_fix_verify,
        "run_full_post_fix_verify",
        lambda **kwargs: {
            "ok": False,
            "escalate_to_tier3": True,
            "reason": "UNVERIFIED: no independently reviewed gold evidence",
            "phases": {"evidence_replay": {"ok": False, "status": "UNVERIFIED"}},
        },
    )

    result = process_bug_with_llm(_bug(target, CANONICAL_PATCH), engine, allow_llm=False)

    assert result["action"] == "skipped"
    assert result["patched"] is False
    assert result["verification_status"] == "UNVERIFIED"
    assert result["escalate_to_tier3"] is True
    assert "UNVERIFIED" in result["reason"]
    assert target.read_text(encoding="utf-8") == ORIGINAL
