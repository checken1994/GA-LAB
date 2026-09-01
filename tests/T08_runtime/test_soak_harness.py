from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_short_soak_produces_verified_completion_report(tmp_path: Path) -> None:
    output_dir = tmp_path / "soak-smoke"
    command = [
        sys.executable,
        "scripts/scp_soak_test.py",
        "--duration-seconds",
        "1.5",
        "--run-id",
        "pytest-smoke",
        "--output-dir",
        str(output_dir),
        "--workers",
        "2",
        "--batch-size",
        "2",
        "--interval-seconds",
        "0.1",
        "--integrity-interval-seconds",
        "0.4",
        "--report-interval-seconds",
        "0.25",
        "--min-free-mb",
        "0",
    ]
    completed = subprocess.run(
        command,
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )

    assert completed.returncode == 0, completed.stdout + completed.stderr
    report = json.loads((output_dir / "progress.json").read_text(encoding="utf-8"))
    assert report["status"] == "COMPLETED"
    assert report["counters"]["completed"] > 0
    assert report["counters"]["failed"] == 0
    assert report["last_integrity"]["quick_check"] == "ok"
    assert report["last_integrity"]["invalid_chains"] == []
    assert len(report["database_sha256"]) == 64
    assert (output_dir / "events.jsonl").is_file()


def test_soak_refuses_to_overwrite_existing_database(tmp_path: Path) -> None:
    output_dir = tmp_path / "existing"
    output_dir.mkdir()
    (output_dir / "kernel.sqlite3").write_bytes(b"keep-me")

    completed = subprocess.run(
        [
            sys.executable,
            "scripts/scp_soak_test.py",
            "--duration-seconds",
            "0.1",
            "--run-id",
            "no-overwrite",
            "--output-dir",
            str(output_dir),
            "--min-free-mb",
            "0",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )

    assert completed.returncode == 2
    assert "refusing to overwrite" in completed.stderr
    assert (output_dir / "kernel.sqlite3").read_bytes() == b"keep-me"
