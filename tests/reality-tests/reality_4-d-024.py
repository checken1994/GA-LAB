#!/usr/bin/env python3
"""Reality contract 4-d-024: HUMAN_REVIEW must be a real durable boundary.

The original version of this test only checked for a ``pending_fixes/README.md``
and a historical count of three generated files. That folder was later removed as
workspace debris, so the presence test no longer measured the actual human-review
mechanism.

This contract now exercises the production TaskKernel directly.  It proves that
an uncertain task can be routed to HUMAN_REVIEW, that the decision survives a
close/reopen cycle with an intact journal, and that the task cannot silently jump
to COMPLETED without an explicit human-controlled transition back into the normal
execution lifecycle.

DNA #4: the human decides.
DNA #11: human-in-the-loop must be functional, not decorative.
DNA #22: PASS != TRUE; uncertainty must not become completion.
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scp.task_kernel import InvalidTransition, TaskKernel


def main() -> int:
    task_id = "reality-human-review-boundary"

    with tempfile.TemporaryDirectory(prefix="scp-reality-human-review-") as tmp:
        db_path = Path(tmp) / "kernel.sqlite3"

        kernel = TaskKernel(db_path)
        try:
            kernel.create_task(
                task_id,
                owner="reality-4-d-024",
                goal="prove that uncertain work cannot self-complete",
                risk_tier="R1",
            )
            for state in ("PLANNING", "READY", "QUEUED"):
                kernel.transition(
                    task_id,
                    state,
                    actor="reality-test",
                    reason="construct real execution lifecycle",
                )
            lease = kernel.claim(task_id, "reality-worker", ttl_seconds=30)
            kernel.start(task_id, lease.lease_id)
            kernel.transition(
                task_id,
                "VERIFYING",
                actor="reality-test",
                reason="execution produced evidence requiring verification",
            )
            kernel.transition(
                task_id,
                "HUMAN_REVIEW",
                actor="reality-test",
                reason="evidence is insufficient for autonomous completion",
                payload={"uncertainty": "explicit", "human_decision_required": True},
            )

            task = kernel.get_task(task_id)
            assert task["state"] == "HUMAN_REVIEW", task
            journal = kernel.verify_journal(task_id)
            assert journal.get("hash_chain_valid") is True, journal
            print("PASS [1/4]: production TaskKernel routes uncertainty to HUMAN_REVIEW")
            print("PASS [2/4]: HUMAN_REVIEW journal is hash-chain valid")
        finally:
            kernel.close()

        # Durability is part of the contract: review state must not live only in
        # process memory.
        reopened = TaskKernel(db_path)
        try:
            persisted = reopened.get_task(task_id)
            assert persisted["state"] == "HUMAN_REVIEW", persisted
            assert reopened.verify_journal(task_id).get("hash_chain_valid") is True
            print("PASS [3/4]: HUMAN_REVIEW survives close/reopen with intact evidence")

            # HUMAN_REVIEW -> COMPLETED is deliberately absent from the state
            # machine. Completion requires an explicit reviewed path back through
            # READY/QUEUED/execution/verification rather than an autonomous leap.
            try:
                reopened.transition(
                    task_id,
                    "COMPLETED",
                    actor="autonomous-system",
                    reason="attempt to bypass human decision",
                )
            except InvalidTransition:
                pass
            else:
                raise AssertionError(
                    "FAIL: HUMAN_REVIEW task transitioned directly to COMPLETED; "
                    "human review is decorative rather than an enforced boundary"
                )

            final_task = reopened.get_task(task_id)
            assert final_task["state"] == "HUMAN_REVIEW", final_task
            assert reopened.verify_journal(task_id).get("hash_chain_valid") is True
            print("PASS [4/4]: autonomous HUMAN_REVIEW -> COMPLETED bypass is rejected")
        finally:
            reopened.close()

    print("\nReality test 4-d-024 PASSED: human review is a durable behavioral boundary")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
