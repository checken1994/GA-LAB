from __future__ import annotations

import shlex
import subprocess
import sys
from pathlib import Path

import scp.autofix.evidence_replay as evidence_replay_module
from scp.autofix.evidence_replay import EvidenceReplay, EvidenceRole
from scp.autofix.runner_phases.post_fix_verify import run_full_post_fix_verify


def _command(argv: list[str]) -> str:
    if sys.platform.startswith("win"):
        return subprocess.list2cmdline(argv)
    return shlex.join(argv)


def test_evidence_replay_accepts_windows_absolute_path_and_restores(tmp_path: Path) -> None:
    module_path = tmp_path / "smoke_module.py"
    test_code = "from smoke_module import answer; assert answer() == 1"
    command = _command([sys.executable, "-c", test_code])

    # Seed a candidate .pyc before replay. B/S/G must not reuse stale bytecode.
    original_source = "def answer() -> int:\n    return 1\n"
    module_path.write_text(original_source, encoding="utf-8")
    subprocess.run([sys.executable, "-c", test_code], cwd=str(tmp_path), check=True)

    replay = EvidenceReplay(working_dir=str(tmp_path))
    result = replay.classify_evidence(
        test_command=command,
        buggy_source="def answer() -> int:\n    return 0\n",
        candidate_source=original_source,
        gold_source=original_source,
        file_path=str(module_path),
    )

    assert result.role is EvidenceRole.GOLD_ALIGNED
    assert result.b_result[0] is False
    assert result.s_result[0] is True
    assert result.g_result[0] is True
    assert module_path.exists()
    assert module_path.read_text(encoding="utf-8") == original_source


def test_evidence_replay_timeout_is_not_success(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(evidence_replay_module, "_MAX_TEST_TIME_S", 0.05)
    command = _command([sys.executable, "-c", "import time; time.sleep(1)"])

    passed, snippet = EvidenceReplay(working_dir=str(tmp_path)).run_test(command, cwd=str(tmp_path))

    assert passed is False
    assert "TIMEOUT" in snippet


def test_missing_gold_is_unverified_not_ok(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    result = run_full_post_fix_verify(
        bug_id="contract-no-gold-20260826",
        file_path=str(tmp_path / "missing_target.py"),
        bug_type="contract-no-gold-unique-20260826",
        run_vulture=False,
        run_import=False,
        run_hypothesis=False,
        run_reality_exercise=False,
        run_completeness=False,
        run_evidence_replay=True,
    )

    evidence = result["phases"]["evidence_replay"]
    assert evidence["status"] == "UNVERIFIED"
    assert evidence["ok"] is False
    assert result["ok"] is False
    assert result["rollback"] is False
    assert result["escalate_to_tier3"] is True


def test_missing_semantic_baseline_is_unverified(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    result = run_full_post_fix_verify(
        bug_id="contract-no-baseline-20260826",
        file_path=str(tmp_path / "missing_target.py"),
        bug_type=None,
        run_vulture=False,
        run_import=False,
        run_hypothesis=False,
        run_reality_exercise=False,
        run_completeness=False,
        run_evidence_replay=False,
    )

    semantic = result["phases"]["semantic_equiv"]
    assert semantic["status"] == "UNVERIFIED"
    assert semantic["ok"] is False
    assert result["ok"] is False
    assert result["escalate_to_tier3"] is True
