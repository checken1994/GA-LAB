"""P2/P3 batch — speculative race, snapshot rollback, budget engine,
red-team agent, dependency resolver, file mutex, knowledge pruning."""
from __future__ import annotations

import json
import subprocess
import threading
import time
from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# #38 Speculative Execution
# ---------------------------------------------------------------------------
def _init_git_repo(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init"], cwd=str(root), capture_output=True, check=True)
    (root / "seed.txt").write_text("seed", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=str(root), capture_output=True, check=True)
    subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-m", "seed"],
                   cwd=str(root), capture_output=True, check=True)


def test_speculative_first_pass_wins(tmp_path):
    from scp.core.speculative import SpeculativeRace

    _init_git_repo(tmp_path / "repo")
    attempts_seen = []

    def solver(worktree, bug):
        with lock:
            attempts_seen.append(worktree)
        (worktree / "fix.txt").write_text(f"fix from {worktree.name}", encoding="utf-8")
        return f"patch-{worktree.name}"

    lock = threading.Lock()

    def verifier(worktree, result):
        # attempt 2 PASS, attempt 1 FAIL — attempt 3 phải bị skip (winner đã có)
        return "attempt-2" in str(result)

    race = SpeculativeRace(tmp_path / "repo", solver=solver, verifier=verifier, attempts=3)
    report = race.run({"bug": "hard bug"})
    assert report["verdict"] == "SOLVED"
    assert "attempt-2" in report["winner"]["worktree"]
    # loser worktrees dọn sạch, winner giữ lại
    remaining = list((tmp_path).glob("scp-speculative-*/speculative-attempt-*"))
    assert all("attempt-2" in str(p) for p in remaining)


def test_speculative_all_fail_is_unsolved_and_cleaned(tmp_path):
    from scp.core.speculative import SpeculativeRace

    _init_git_repo(tmp_path / "repo")

    def solver(worktree, bug):
        return "bad patch"

    race = SpeculativeRace(tmp_path / "repo", solver=solver, verifier=lambda w, r: False, attempts=2)
    report = race.run({"bug": "x"})
    assert report["verdict"] == "UNSOLVED"
    remaining = list(tmp_path.glob("scp-speculative-*/speculative-attempt-*"))
    assert remaining == []


# ---------------------------------------------------------------------------
# #39 Environment Snapshot
# ---------------------------------------------------------------------------
def test_snapshot_and_restore_roundtrip(tmp_path):
    from scp.core.environment_snapshot import SnapshotManager

    work = tmp_path / "work"
    work.mkdir()
    (work / "config.json").write_text('{"mode": "safe"}', encoding="utf-8")
    kernel_db = work / "kernel.sqlite3"
    import sqlite3
    conn = sqlite3.connect(str(kernel_db))
    conn.execute("CREATE TABLE t (v TEXT)")
    conn.execute("INSERT INTO t VALUES ('original')")
    conn.commit()
    conn.close()

    manager = SnapshotManager(tmp_path / "snapshots", retain=5)
    snap = manager.snapshot([work / "config.json", kernel_db], tag="pre-action")

    # Thảm họa xảy ra: ghi đè cả hai
    (work / "config.json").write_text('{"mode": "DESTROYED"}', encoding="utf-8")
    conn = sqlite3.connect(str(kernel_db))
    conn.execute("DELETE FROM t")
    conn.commit()
    conn.close()

    manager.restore(snap["snapshot_dir"])
    assert json.loads((work / "config.json").read_text(encoding="utf-8"))["mode"] == "safe"
    conn = sqlite3.connect(str(kernel_db))
    value = conn.execute("SELECT v FROM t").fetchone()[0]
    conn.close()
    assert value == "original"


def test_snapshot_rejects_tampered_manifest(tmp_path):
    from scp.core.environment_snapshot import SnapshotManager

    work = tmp_path / "work"
    work.mkdir()
    (work / "data.txt").write_text("precious", encoding="utf-8")
    manager = SnapshotManager(tmp_path / "snapshots")
    snap = manager.snapshot([work / "data.txt"], tag="t")

    # Giả mạo: sửa manifest sha256
    manifest_path = Path(snap["snapshot_dir"]) / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["files"][str(work / "data.txt")]["sha256"] = "sha256:fake"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(RuntimeError, match="integrity failed"):
        manager.restore(snap["snapshot_dir"])
    # Dữ liệu sống KHÔNG bị đè
    assert (work / "data.txt").read_text(encoding="utf-8") == "precious"


def test_snapshot_retention_prunes_old(tmp_path):
    from scp.core.environment_snapshot import SnapshotManager

    manager = SnapshotManager(tmp_path / "snapshots", retain=3)
    target = tmp_path / "f.txt"
    target.write_text("x", encoding="utf-8")
    for i in range(5):
        manager.snapshot([target], tag=f"round-{i}")
    assert len(list((tmp_path / "snapshots").iterdir())) == 3


# ---------------------------------------------------------------------------
# #40 Budget Engine
# ---------------------------------------------------------------------------
def test_budget_simple_task_routes_free_first():
    from scp.core.budget_engine import route_tier

    assert route_tier("fix the typo in the log comment", task="chat") == "free_first"


def test_budget_hard_task_routes_paid_first():
    from scp.core.budget_engine import route_tier

    hard = ("Fix race condition in the async event loop causing deadlock in the "
            "state machine architecture; the algorithm complexity must be optimized")
    assert route_tier(hard, task="judge") == "paid_first"


def test_budget_autofix_always_paid_first():
    from scp.core.budget_engine import route_tier

    assert route_tier("fix a typo", task="autofix") == "paid_first"


def test_budget_env_override_wins(monkeypatch):
    from scp.core.budget_engine import route_tier

    monkeypatch.setenv("SCP_BUDGET_TIER_JUDGE", "free_first")
    assert route_tier("very hard race condition deadlock", task="judge") == "free_first"


# ---------------------------------------------------------------------------
# #43 Red-Team Agent
# ---------------------------------------------------------------------------
def test_redteam_breaches_weak_candidate():
    from scp.security.red_team import RedTeamAgent

    def weak_executor(vector):
        value = str(vector.get("value", ""))
        if "rm -rf" in value:
            return {"safe": False, "detail": "command executed!"}  # bản vá yếu
        return {"safe": True, "detail": "ok"}

    result = RedTeamAgent(executor=weak_executor).attack({"candidate": "x"})
    assert result["verdict"] == "BREACHED"
    assert any(b["vector"] == "command_chaining" for b in result["breaches"])


def test_redteam_survives_strong_candidate():
    from scp.security.red_team import RedTeamAgent

    result = RedTeamAgent(executor=lambda v: {"safe": True, "detail": "held"}).attack({"candidate": "x"})
    assert result["verdict"] == "SURVIVED"
    assert result["breaches"] == []


def test_redteam_executor_crash_counts_as_breach():
    from scp.security.red_team import RedTeamAgent

    def crashing_executor(vector):
        raise ValueError("candidate exploded")

    result = RedTeamAgent(executor=crashing_executor).attack({"candidate": "x"})
    assert result["verdict"] == "BREACHED"
    assert "executor_crash" in result["breaches"][0]["detail"]


# ---------------------------------------------------------------------------
# #31 Dependency Resolver
# ---------------------------------------------------------------------------
def test_resolver_flags_missing_import():
    from scp.core.dependency_resolver import resolve

    report = resolve("import definitely_not_installed_xyz\nprint('x')", local_modules={"scp"})
    assert "definitely_not_installed_xyz" in report.missing_imports
    assert "definitely_not_installed_xyz" in report.missing_packages


def test_resolver_ignores_local_and_stdlib():
    from scp.core.dependency_resolver import resolve

    report = resolve("import json\nimport os\nfrom scp.task_kernel import TaskKernel")
    assert report.missing_imports == []
    assert "json" in report.installed or "json" in report.local_or_stdlib


def test_resolver_maps_import_to_package():
    from scp.core.dependency_resolver import resolve

    report = resolve("import yaml")
    if "yaml" in report.missing_imports:
        assert "pyyaml" in report.missing_packages


def test_resolver_syntax_error_returns_empty():
    from scp.core.dependency_resolver import resolve

    report = resolve("def broken(:")
    assert report.missing_imports == []


# ---------------------------------------------------------------------------
# #30 File Mutex
# ---------------------------------------------------------------------------
def test_mutex_acquire_and_release(tmp_path):
    from scp.core.file_mutex import FileMutex

    mutex = FileMutex(tmp_path)
    with mutex.acquire("kernel-write", timeout=2):
        assert (tmp_path / "kernel-write.lock").exists()
    assert not (tmp_path / "kernel-write.lock").exists()


def test_mutex_blocks_second_holder(tmp_path):
    from scp.core.file_mutex import FileMutex

    mutex = FileMutex(tmp_path)
    with mutex.acquire("resource", timeout=2):
        with pytest.raises(TimeoutError):
            with mutex.acquire("resource", timeout=0.2):
                pass  # không bao giờ vào được


def test_mutex_recovers_stale_lock(tmp_path):
    from scp.core.file_mutex import FileMutex

    mutex = FileMutex(tmp_path)
    stale = mutex._lock_path("stuck")
    stale.write_text("dead-holder", encoding="utf-8")
    old = time.time() - 3600
    import os as _os
    _os.utime(stale, (old, old))  # lock mồ côi 1 giờ tuổi
    with mutex.acquire("stuck", timeout=2):
        pass  # phải thu hồi được lock mồ côi


# ---------------------------------------------------------------------------
# #23 Knowledge Pruning
# ---------------------------------------------------------------------------
def test_prune_knowledge_removes_old_low_reputation(tmp_path):
    import time as _time
    from scp.core.top_systems_learning import TopSystemsLearner

    learner = TopSystemsLearner(data_dir=str(tmp_path))
    old_low = json.dumps({"name": "old-low", "reputation": "low",
                          "collected_at": _time.time() - 200 * 86400}, ensure_ascii=False)
    old_high = json.dumps({"name": "old-high", "reputation": "high",
                           "collected_at": _time.time() - 200 * 86400}, ensure_ascii=False)
    fresh = json.dumps({"name": "fresh", "reputation": "low",
                        "collected_at": _time.time()}, ensure_ascii=False)
    learner.ledger_path.write_text("\n".join([old_low, old_high, fresh]), encoding="utf-8")

    result = learner.prune_knowledge(keep_days=90)
    assert result["pruned"] == 1  # chỉ old-low bị xóa
    kept = [json.loads(l) for l in learner.ledger_path.read_text(encoding="utf-8").splitlines()]
    assert {r["name"] for r in kept} == {"old-high", "fresh"}
    assert (tmp_path / "top_systems_knowledge.jsonl.backup").exists()  # rollback path
