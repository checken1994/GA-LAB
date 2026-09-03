from __future__ import annotations

from pathlib import Path

import yaml


WORKFLOW = Path(".github/workflows/scp-rc-promotion.yml")


def _step_using(steps: list[dict], action_prefix: str) -> dict:
    matches = [step for step in steps if str(step.get("uses", "")).startswith(action_prefix)]
    assert len(matches) == 1, f"expected exactly one {action_prefix} step, found {len(matches)}"
    return matches[0]


def test_push_release_gates_provision_declared_runtimes_unconditionally() -> None:
    workflow = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    jobs = workflow["jobs"]

    platform_steps = jobs["platform-gates"]["steps"]
    platform_python = _step_using(platform_steps, "actions/setup-python@")
    platform_node = _step_using(platform_steps, "actions/setup-node@")

    assert platform_python["with"]["python-version"] == "3.12"
    assert "if" not in platform_python
    assert str(platform_node["with"]["node-version"]) == "20"
    assert "if" not in platform_node

    manifest_steps = jobs["manifest-provenance"]["steps"]
    manifest_python = _step_using(manifest_steps, "actions/setup-python@")
    assert manifest_python["with"]["python-version"] == "3.12"
    assert "if" not in manifest_python
