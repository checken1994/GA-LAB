#!/usr/bin/env python3
"""Fail-closed validation that mandatory SCP test gates are bound to SCP DNA + skills."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PROFILE = ROOT / "tests" / "scp_required_test_skills.json"
SKILL_ROOT = ROOT / ".agents" / "skills"
DNA_REFERENCE = SKILL_ROOT / "scp-dna" / "references" / "dna-principles.md"
AGENT_GUIDANCE = ROOT / "AGENTS.md"

REQUIRED_GATE_IDS = {
    "compile_import",
    "unit_integration",
    "semantic_parity",
    "acceptance",
    "fail_closed",
    "bandit_security",
    "mutation",
    "provider_failover_timeout",
    "taskkernel_durability_recovery",
    "reality_tests",
    "bounded_runtime_smoke",
    "dashboard_build_audit",
    "manifest_provenance",
    "final_release_verdict",
}


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def git_head() -> str:
    return subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True, encoding="utf-8"
    ).strip()


def frontmatter_name(text: str) -> str | None:
    if not text.startswith("---"):
        return None
    lines = text.splitlines()
    if len(lines) < 3 or lines[0].strip() != "---":
        return None
    for line in lines[1:]:
        if line.strip() == "---":
            break
        if line.startswith("name:"):
            return line.split(":", 1)[1].strip()
    return None


def dna_principle_numbers(text: str) -> list[int]:
    numbers: list[int] = []
    for line in text.splitlines():
        match = re.match(r"^##\s+(\d+)\.\s+", line)
        if match:
            numbers.append(int(match.group(1)))
    return numbers


def load_profile(path: Path = DEFAULT_PROFILE) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def validate_contract(path: Path = DEFAULT_PROFILE) -> dict[str, Any]:
    errors: list[str] = []
    if not path.is_file():
        raise FileNotFoundError(f"mandatory SCP test-skill profile missing: {path}")

    profile = load_profile(path)
    if profile.get("schema_version") != 1:
        errors.append("schema_version must be 1")

    gates = profile.get("mandatory_gates")
    if not isinstance(gates, list) or not gates:
        errors.append("mandatory_gates must be a non-empty list")
        gates = []

    gate_ids: list[str] = []
    referenced_skills: set[str] = set()
    normalized_gates: list[dict[str, Any]] = []
    for gate in gates:
        if not isinstance(gate, dict):
            errors.append("every mandatory gate entry must be an object")
            continue
        gate_id = str(gate.get("id", "")).strip()
        skills = gate.get("required_skills")
        if not gate_id:
            errors.append("mandatory gate has an empty id")
            continue
        gate_ids.append(gate_id)
        if not isinstance(skills, list) or not all(isinstance(item, str) and item for item in skills):
            errors.append(f"{gate_id}: required_skills must be a non-empty string list")
            continue
        if len(skills) != len(set(skills)):
            errors.append(f"{gate_id}: duplicate skill binding")
        if "scp-dna" not in skills:
            errors.append(f"{gate_id}: scp-dna is mandatory")
        if len(set(skills) - {"scp-dna"}) < 1:
            errors.append(f"{gate_id}: at least one specialized SCP skill is mandatory")
        referenced_skills.update(skills)
        normalized_gates.append({"id": gate_id, "required_skills": list(skills)})

    if len(gate_ids) != len(set(gate_ids)):
        errors.append("mandatory gate ids must be unique")
    gate_set = set(gate_ids)
    missing_gates = sorted(REQUIRED_GATE_IDS - gate_set)
    extra_gates = sorted(gate_set - REQUIRED_GATE_IDS)
    if missing_gates:
        errors.append(f"missing mandatory gates: {', '.join(missing_gates)}")
    if extra_gates:
        errors.append(f"unknown mandatory gates: {', '.join(extra_gates)}")

    failure_policy = profile.get("failure_policy")
    if not isinstance(failure_policy, dict):
        errors.append("failure_policy must be present")
        failure_policy = {}
    if failure_policy.get("fix_reality_where_it_fails") is not True:
        errors.append("failure policy must require fixing reality where the test fails")
    if failure_policy.get("harness_fix_must_preserve_or_increase_strictness") is not True:
        errors.append("harness fixes must preserve or increase strictness")
    forbidden = failure_policy.get("forbidden_shortcuts")
    required_forbidden = {
        "delete_test",
        "skip_test",
        "xfail_test",
        "loosen_assertion",
        "lower_threshold",
        "lower_security_policy",
        "lower_mutation_score",
        "drop_acceptance_gate",
        "ignore_exit_code",
        "fail_open_instead_of_fail_closed",
    }
    if not isinstance(forbidden, list) or not required_forbidden.issubset(set(forbidden)):
        errors.append("failure_policy does not forbid every required test-weakening shortcut")

    skill_evidence: dict[str, dict[str, Any]] = {}
    for skill in sorted(referenced_skills):
        skill_path = SKILL_ROOT / skill / "SKILL.md"
        if not skill_path.is_file():
            errors.append(f"required skill missing: {skill_path.relative_to(ROOT)}")
            continue
        text = skill_path.read_text(encoding="utf-8")
        declared = frontmatter_name(text)
        if declared != skill:
            errors.append(f"skill frontmatter mismatch: expected {skill}, got {declared!r}")
        skill_evidence[skill] = {
            "path": str(skill_path.relative_to(ROOT)).replace("\\", "/"),
            "sha256": sha256_file(skill_path),
            "declared_name": declared,
        }

    if not DNA_REFERENCE.is_file():
        errors.append("scp-dna principle reference is missing")
        dna_numbers: list[int] = []
    else:
        dna_text = DNA_REFERENCE.read_text(encoding="utf-8")
        dna_numbers = dna_principle_numbers(dna_text)
        expected = list(range(1, 30))
        if dna_numbers != expected:
            errors.append(
                "scp-dna reference must contain exactly principles 1..29 in order; "
                f"observed={dna_numbers}"
            )

    if not AGENT_GUIDANCE.is_file():
        errors.append("AGENTS.md guidance is missing")
    else:
        guidance = AGENT_GUIDANCE.read_text(encoding="utf-8")
        if "tests/scp_required_test_skills.json" not in guidance:
            errors.append("AGENTS.md must point to the mandatory SCP test-skill profile")
        if "scp-dna" not in guidance:
            errors.append("AGENTS.md must require scp-dna")

    try:
        commit = git_head()
    except Exception as exc:  # pragma: no cover - CI/repo contract
        errors.append(f"cannot resolve exact Git HEAD: {exc}")
        commit = "UNKNOWN"

    evidence: dict[str, Any] = {
        "status": "PASS_WITHIN_SCOPE" if not errors else "FAIL",
        "commit": commit,
        "profile": str(path.relative_to(ROOT)).replace("\\", "/"),
        "profile_sha256": sha256_file(path),
        "required_gate_count": len(REQUIRED_GATE_IDS),
        "observed_gate_count": len(gate_set),
        "dna_principle_count": len(dna_numbers),
        "skills": skill_evidence,
        "gate_bindings": normalized_gates,
        "errors": errors,
    }
    return evidence


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", type=Path, default=DEFAULT_PROFILE)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    try:
        evidence = validate_contract(args.profile.resolve())
    except Exception as exc:
        evidence = {
            "status": "FAIL",
            "commit": "UNKNOWN",
            "profile": str(args.profile),
            "errors": [f"validator exception: {type(exc).__name__}: {exc}"],
        }

    rendered = json.dumps(evidence, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.output:
        output = args.output
        if not output.is_absolute():
            output = ROOT / output
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0 if evidence.get("status") == "PASS_WITHIN_SCOPE" else 1


if __name__ == "__main__":
    raise SystemExit(main())
