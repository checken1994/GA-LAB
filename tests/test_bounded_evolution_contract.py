from __future__ import annotations

from pathlib import Path

from scp.core.bounded_evolution import run_bounded_evolution
from scp.core.learning_run_ledger import _status


def test_hard_timeout_terminates_child_and_is_fail_closed(tmp_path):
    result = run_bounded_evolution(
        max_bugs=1,
        timeout_seconds=0.001,
        data_dir=str(tmp_path),
    )
    assert result["status"] == "TIMEOUT"
    assert result["action"] == "timed_out"
    assert result["stage"] in {
        "unknown",
        "cycle_start",
        "scan_start",
        "scan_complete",
        "finding_start",
        "fix_start",
        "reflect_start",
    }
    assert isinstance(result["child_pid"], int)


def test_evolution_zero_fix_is_not_success():
    assert _status(
        "evolution",
        {"action": "evolved", "bugs_found": 1, "bugs_fixed": 0},
        None,
    ) == "PROVIDER_FAILED"
    assert _status(
        "evolution",
        {"action": "evolved", "bugs_found": 0, "bugs_fixed": 0},
        None,
    ) == "NO_NEW_FACTS"


def test_runner_exposes_true_scan_only_and_timeout_flags():
    source = Path(__file__).resolve().parents[1] / "scp" / "autofix" / "runner.py"
    text = source.read_text(encoding="utf-8")
    assert "--scan-only" in text
    assert "--evolution-timeout-seconds" in text
    assert "run_bounded_evolution" in text
