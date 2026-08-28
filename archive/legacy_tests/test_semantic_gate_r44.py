from __future__ import annotations

from pathlib import Path

from scp.history.semantic_gate import evaluate_candidate


def _write_source(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "sample.py"
    path.write_text(text, encoding="utf-8")
    return path


def test_missing_snapshot_is_rejected(tmp_path: Path):
    source = "def f():\n    try:\n        return 1\n    except:\n        pass\n"
    path = _write_source(tmp_path, source)
    decision = evaluate_candidate(
        source_path=path,
        source_snapshot=None,
        expected_source_sha256=None,
        bug_type="BareExceptPass",
        bug_line=4,
        patched_source=source.replace("except:", "except Exception:"),
        semantic_tests_passed=True,
        independent_external_evidence=True,
    )
    assert decision.promotion_allowed is False
    assert "REJECT_NO_SOURCE_SNAPSHOT" in decision.reasons


def test_classification_mismatch_is_rejected(tmp_path: Path):
    source = "def f():\n    try:\n        return 1\n    except Exception:\n        pass\n"
    path = _write_source(tmp_path, source)
    decision = evaluate_candidate(
        source_path=path,
        source_snapshot=source,
        expected_source_sha256=__import__("hashlib").sha256(source.encode()).hexdigest(),
        bug_type="BareExceptPass",
        bug_line=4,
        patched_source=source,
        semantic_tests_passed=True,
        independent_external_evidence=True,
    )
    assert decision.target_is_bare_except_pass is False
    assert "REJECT_CLASSIFICATION_MISMATCH" in decision.reasons
    assert decision.promotion_allowed is False


def test_missing_semantic_or_external_evidence_blocks(tmp_path: Path):
    source = "def f():\n    try:\n        return 1\n    except:\n        pass\n"
    path = _write_source(tmp_path, source)
    import hashlib

    digest = hashlib.sha256(source.encode()).hexdigest()
    patched = source.replace("except:", "except Exception:")
    decision = evaluate_candidate(
        source_path=path,
        source_snapshot=source,
        expected_source_sha256=digest,
        bug_type="BareExceptPass",
        bug_line=4,
        patched_source=patched,
        semantic_tests_passed=False,
        independent_external_evidence=False,
    )
    assert "REJECT_SEMANTIC_TEST_NOT_PROVEN" in decision.reasons
    assert "REJECT_NO_INDEPENDENT_EXTERNAL_EVIDENCE" in decision.reasons
    assert decision.promotion_allowed is False


def test_full_gate_can_be_eligible_only_with_all_evidence(tmp_path: Path):
    source = "def f():\n    try:\n        return 1\n    except:\n        pass\n"
    path = _write_source(tmp_path, source)
    import hashlib

    decision = evaluate_candidate(
        source_path=path,
        source_snapshot=source,
        expected_source_sha256=hashlib.sha256(source.encode()).hexdigest(),
        bug_type="BareExceptPass",
        bug_line=4,
        patched_source=source.replace("except:", "except Exception:"),
        semantic_tests_passed=True,
        independent_external_evidence=True,
    )
    assert decision.status == "PROMOTION_ELIGIBLE"
    assert decision.promotion_allowed is True
