"""Bounded process wrapper for SCP evolution runs.

The evolution engine can call provider/analysis code that is not reliably
cancellable from a thread. This wrapper makes the run externally bounded and
fail-closed: a timed-out child is terminated, no partial result is reported as
success, and the parent records a sanitized TIMEOUT ledger row.
"""
from __future__ import annotations

import json
import logging
import multiprocessing as mp
import queue
import time
from datetime import datetime, timezone
from typing import Any

from scp.core.learning_run_ledger import record_learning_run

logger = logging.getLogger("scp.autofix.bounded_evolution")


def _utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _evolution_child(result_queue: Any, max_bugs: int, data_dir: str) -> None:
    """Run evolution in a spawn-safe child process."""
    try:
        from scp.autofix.evolution import get_evolution_engine

        engine = get_evolution_engine(data_dir=data_dir)
        result = engine.evolve_cycle(max_bugs=max_bugs)
        result_queue.put({"ok": True, "result": result})
    except BaseException as exc:  # propagate sanitized failure to parent
        result_queue.put(
            {
                "ok": False,
                "error_class": type(exc).__name__,
                "error_summary": str(exc)[:300],
            }
        )


def _terminate_child(process: mp.Process) -> None:
    if not process.is_alive():
        process.join(timeout=1)
        return
    process.terminate()
    process.join(timeout=5)
    if process.is_alive():
        process.kill()
        process.join(timeout=5)


def run_bounded_evolution(
    *,
    max_bugs: int = 20,
    timeout_seconds: float = 300.0,
    data_dir: str = "data",
) -> dict[str, Any]:
    """Run one evolution cycle with a hard parent-owned deadline."""
    timeout_seconds = float(timeout_seconds)
    if timeout_seconds <= 0 or timeout_seconds != timeout_seconds:
        raise ValueError("timeout_seconds must be a positive finite number")
    started_at = _utc_iso()
    context = mp.get_context("spawn")
    result_queue = context.Queue(maxsize=1)
    process = context.Process(
        target=_evolution_child,
        args=(result_queue, int(max_bugs), str(data_dir)),
        name="scp-evolution-child",
    )
    process.start()
    child_pid = process.pid
    process.join(timeout=timeout_seconds)

    if process.is_alive():
        _terminate_child(process)
        error = TimeoutError(
            f"stage=child_evolve_cycle; child_pid={child_pid}; "
            f"timeout_seconds={timeout_seconds:g}"
        )
        record_learning_run(
            mode="evolution",
            started_at=started_at,
            ended_at=_utc_iso(),
            result=None,
            error=error,
        )
        return {
            "action": "timed_out",
            "status": "TIMEOUT",
            "stage": "child_evolve_cycle",
            "timeout_seconds": timeout_seconds,
            "child_pid": child_pid,
        }

    try:
        message = result_queue.get(timeout=1)
    except queue.Empty:
        return {
            "action": "failed",
            "status": "PROVIDER_FAILED",
            "stage": "child_result_collection",
            "child_pid": child_pid,
            "error_class": "ChildResultMissing",
            "error_summary": "child exited without a result message",
        }
    finally:
        result_queue.close()
        result_queue.join_thread()

    if message.get("ok"):
        result = message.get("result")
        if isinstance(result, dict):
            bugs_found = int(result.get("bugs_found", 0) or 0)
            bugs_fixed = int(result.get("bugs_fixed", 0) or 0)
            if result.get("action") == "skipped" or bugs_found == 0:
                result.setdefault("status", "NO_NEW_FACTS")
            elif bugs_fixed == 0:
                result.setdefault("status", "PROVIDER_FAILED")
            else:
                result.setdefault("status", "SUCCESS")
        return result if isinstance(result, dict) else {"action": "evolved", "status": "SUCCESS", "result": result}

    return {
        "action": "failed",
        "status": "PROVIDER_FAILED",
        "stage": "child_evolve_cycle",
        "child_pid": child_pid,
        "error_class": message.get("error_class", "ChildEvolutionError"),
        "error_summary": message.get("error_summary", "child evolution failed"),
    }


if __name__ == "__main__":
    print(json.dumps(run_bounded_evolution(), sort_keys=True, default=str))
