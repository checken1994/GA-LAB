from __future__ import annotations

from pathlib import Path

import yaml


RC_WORKFLOW = Path(".github/workflows/scp-rc-promotion.yml")
PRE_RC_WORKFLOW = Path(".github/workflows/scp-release-gate.yml")


def _load(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _step_using(steps: list[dict], action_prefix: str) -> dict:
    matches = [step for step in steps if str(step.get("uses", "")).startswith(action_prefix)]
    assert len(matches) == 1, f"expected exactly one {action_prefix} step, found {len(matches)}"
    return matches[0]


def _step_named(steps: list[dict], name: str) -> dict:
    matches = [step for step in steps if step.get("name") == name]
    assert len(matches) == 1, f"expected exactly one {name!r} step, found {len(matches)}"
    return matches[0]


def test_push_release_gates_provision_declared_runtimes_unconditionally() -> None:
    jobs = _load(RC_WORKFLOW)["jobs"]

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


def test_pre_rc_mutation_budget_matches_authoritative_release_gate() -> None:
    rc_steps = _load(RC_WORKFLOW)["jobs"]["security-and-durability"]["steps"]
    pre_rc_steps = _load(PRE_RC_WORKFLOW)["jobs"]["pre-rc-verification"]["steps"]

    rc_command = str(_step_named(rc_steps, "Live mutation testing gate")["run"])
    pre_rc_command = str(_step_named(pre_rc_steps, "Bounded live mutation score gate")["run"])

    for command in (rc_command, pre_rc_command):
        assert "--max-mutants 15" in command
        assert "--min-score 0.40" in command
