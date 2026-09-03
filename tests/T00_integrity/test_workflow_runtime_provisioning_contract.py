from __future__ import annotations

from pathlib import Path
import yaml


def _load_yaml(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def test_rc_promotion_runtime_provisioning_contract() -> None:
    """Ensure runtime provisioning steps in scp-rc-promotion.yml run on push and workflow_dispatch."""
    root = Path(__file__).resolve().parents[2]
    workflow_path = root / ".github" / "workflows" / "scp-rc-promotion.yml"
    assert workflow_path.is_file(), f"Missing workflow {workflow_path}"

    data = _load_yaml(workflow_path)
    triggers = data.get("on") if "on" in data else data.get(True, {})
    assert "push" in triggers, "Expected scp-rc-promotion to trigger on push"

    jobs = data.get("jobs", {})

    # platform-gates must provision Python 3.12 and Node 20 unconditionally
    platform_job = jobs.get("platform-gates")
    assert platform_job is not None, "platform-gates job missing"
    platform_steps = platform_job.get("steps", [])

    setup_python = next((s for s in platform_steps if "actions/setup-python" in s.get("uses", "")), None)
    assert setup_python is not None, "setup-python step missing in platform-gates"
    assert "if" not in setup_python, "setup-python in platform-gates must run unconditionally on push"
    assert setup_python.get("with", {}).get("python-version") == "3.12"

    setup_node = next((s for s in platform_steps if "actions/setup-node" in s.get("uses", "")), None)
    assert setup_node is not None, "setup-node step missing in platform-gates"
    assert "if" not in setup_node, "setup-node in platform-gates must run unconditionally on push"
    assert setup_node.get("with", {}).get("node-version") == "20"

    setup_bun = next((s for s in platform_steps if "setup-bun" in s.get("uses", "")), None)
    assert setup_bun is not None, "setup-bun step missing in platform-gates"

    # manifest-provenance must also provision Python 3.12 unconditionally
    manifest_job = jobs.get("manifest-provenance")
    assert manifest_job is not None, "manifest-provenance job missing"
    manifest_steps = manifest_job.get("steps", [])
    manifest_python = next((s for s in manifest_steps if "actions/setup-python" in s.get("uses", "")), None)
    assert manifest_python is not None, "setup-python missing in manifest-provenance-gate"
    assert "if" not in manifest_python, "setup-python in manifest-provenance-gate must run unconditionally"


def test_no_workflows_skip_runtime_setup_on_push_triggers() -> None:
    """Invariant: No workflow with push triggers can guard setup-node/python with workflow_dispatch."""
    root = Path(__file__).resolve().parents[2]
    workflow_dir = root / ".github" / "workflows"

    for wf_file in workflow_dir.glob("*.yml"):
        data = _load_yaml(wf_file)
        triggers = data.get("on") if "on" in data else data.get(True, {})
        if not (triggers == "push" or "push" in triggers or (isinstance(triggers, list) and "push" in triggers)):
            continue

        for job_name, job_def in data.get("jobs", {}).items():
            for step in job_def.get("steps", []):
                uses = step.get("uses", "")
                if "actions/setup-node" in uses or "actions/setup-python" in uses:
                    cond = step.get("if", "")
                    assert "workflow_dispatch" not in cond or "push" in cond, (
                        f"Workflow {wf_file.name} job {job_name} guards runtime setup '{uses}' "
                        f"with condition '{cond}', which would skip setup on push events!"
                    )
