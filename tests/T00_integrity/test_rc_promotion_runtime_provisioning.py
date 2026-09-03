"""Regression proof: runtime provisioning must never be skipped while its version check runs.

Root cause (RC-AUTHORITY-01 failure 1, HARNESS/INFRA): platform-gates pinned
``actions/setup-python`` (3.12) and ``actions/setup-node`` (20) behind
``if: workflow_dispatch && github-hosted``, but the workflow also triggers on
``push`` and the ``Verify Python/Node runtime`` assertions run unconditionally.
On push the provisioners were skipped while the version checks still ran, so
the gate failed on whatever runtime the runner happened to ship.

Invariant enforced here: in jobs that assert a pinned runtime, the matching
``setup-*`` step must exist WITHOUT an event-gated ``if``. The contract
itself (Python 3.12, Node 20) is preserved, never widened.
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github" / "workflows" / "scp-rc-promotion.yml"

# job -> {provisioner use-prefix -> pinned version that must be asserted}
PINNED_RUNTIMES: dict[str, dict[str, str]] = {
    "platform-gates": {
        "actions/setup-python": "3.12",
        "actions/setup-node": "20",
    },
    "manifest-provenance": {
        "actions/setup-python": "3.12",
    },
}


def _workflow() -> dict:
    import yaml

    assert WORKFLOW.is_file(), f"RC promotion workflow must exist: {WORKFLOW}"
    return yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))


def test_runtime_provisioners_are_not_event_gated():
    data = _workflow()
    jobs = data.get("jobs", {})
    for job_name, expected in PINNED_RUNTIMES.items():
        assert job_name in jobs, f"job {job_name!r} must exist in scp-rc-promotion.yml"
        steps = jobs[job_name].get("steps", [])
        for use_prefix, pinned in expected.items():
            provisioners = [s for s in steps if str(s.get("uses", "")).startswith(use_prefix)]
            assert provisioners, f"{job_name}: missing {use_prefix} provisioner"
            ungated = [s for s in provisioners if "if" not in s]
            assert ungated, (
                f"{job_name}: {use_prefix} is event-gated by 'if' "
                f"({provisioners[0].get('if')}) while the Verify runtime step runs "
                "unconditionally — push would skip provisioning but still assert "
                f"the pinned {pinned} runtime"
            )


def test_pinned_versions_and_assertions_are_preserved():
    data = _workflow()
    jobs = data.get("jobs", {})
    steps = jobs["platform-gates"].get("steps", [])
    dumped = "\n".join(str(s.get("uses", "")) + str(s.get("with", "")) for s in steps)
    assert "3.12" in dumped, "Python 3.12 pin must be preserved, not removed"
    assert "'20'" in dumped or '"20"' in dumped or "20" in dumped, (
        "Node 20 pin must be preserved, not removed"
    )
    runs = "\n".join(str(s.get("run", "")) for s in steps)
    assert "sys.version_info[:2] == (3, 12)" in runs, "Python 3.12 assertion must stay strict"
    assert "process.versions.node.split('.')[0] !== '20'" in runs, (
        "Node 20 assertion must stay strict — accepting 22/24 would weaken the contract"
    )
