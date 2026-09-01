#!/usr/bin/env python3
"""Fail-closed verifier for the SCP Skill pack and SCP DNA release contract."""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

EXPECTED_SKILLS = (
    "scp-dna",
    "scp-capability-security-review",
    "scp-computer-use-recovery",
    "scp-gateway-resilience",
    "scp-learning-loop-guard",
    "scp-reality-verifier",
    "scp-release-evidence-gate",
    "scp-runtime-audit",
    "scp-safe-latency-optimizer",
    "scp-startup-troubleshooter",
    "scp-task-kernel-review",
    "scp-web-orchestration-safety",
    "scp-skill-review",
)
GATE_COMMAND = "python tools/verify_scp_skill_dna_gate.py"
MANDATORY_WORKFLOW_CALLS = {
    ".github/workflows/ci.yml": 1,
    ".github/workflows/scp-release-gate.yml": 1,
    ".github/workflows/scp-system-audit.yml": 1,
    ".github/workflows/scp-architecture-snapshot-audit.yml": 1,
}
INDEX_FILES = (
    ".agents/skills/README.md",
    ".agents/AGENTS.md",
    ".agents/GEMINI.md",
)


def _read(root: Path, relative: str, errors: list[str]) -> str:
    path = root / relative
    if not path.is_file():
        errors.append(f"missing required file: {relative}")
        return ""
    try:
        return path.read_text(encoding="utf-8")
    except Exception as exc:
        errors.append(f"cannot read {relative}: {exc}")
        return ""


def parse_frontmatter(text: str) -> dict[str, str]:
    """Parse the simple YAML frontmatter shape used by SCP SKILL.md files."""
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}
    try:
        end = next(i for i, line in enumerate(lines[1:], start=1) if line.strip() == "---")
    except StopIteration:
        return {}
    meta: dict[str, str] = {}
    for line in lines[1:end]:
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        meta[key.strip()] = value.strip()
    return meta


def dna_principle_numbers(text: str) -> list[int]:
    return [int(n) for n in re.findall(r"(?m)^##\s+(\d+)\.\s+", text)]


def verify(root: Path) -> dict[str, object]:
    root = root.resolve()
    errors: list[str] = []
    skills_dir = root / ".agents" / "skills"
    if not skills_dir.is_dir():
        errors.append("missing .agents/skills directory")
        discovered: set[str] = set()
    else:
        discovered = {
            path.parent.name
            for path in skills_dir.glob("*/SKILL.md")
            if path.is_file()
        }

    expected = set(EXPECTED_SKILLS)
    missing = sorted(expected - discovered)
    extra = sorted(discovered - expected)
    if missing:
        errors.append("missing SCP skills: " + ", ".join(missing))
    if extra:
        errors.append(
            "unreviewed SCP skills present; update the governed baseline first: "
            + ", ".join(extra)
        )

    skill_meta: dict[str, dict[str, str]] = {}
    for name in sorted(discovered):
        rel = f".agents/skills/{name}/SKILL.md"
        text = _read(root, rel, errors)
        meta = parse_frontmatter(text)
        skill_meta[name] = meta
        if meta.get("name") != name:
            errors.append(f"{rel}: frontmatter name must equal directory name")
        description = meta.get("description", "")
        if len(description) < 20:
            errors.append(f"{rel}: description is missing or too weak for discovery")

    index_status: dict[str, list[str]] = {}
    for relative in INDEX_FILES:
        text = _read(root, relative, errors)
        absent = [name for name in EXPECTED_SKILLS if name not in text]
        index_status[relative] = absent
        if absent:
            errors.append(f"{relative}: missing skill index entries: {', '.join(absent)}")

    dna_skill = _read(root, ".agents/skills/scp-dna/SKILL.md", errors)
    dna_ref = _read(root, ".agents/skills/scp-dna/references/dna-principles.md", errors)
    numbers = dna_principle_numbers(dna_ref)
    if numbers != list(range(1, 30)):
        errors.append(
            "SCP DNA principles must be exactly 1..29 once and in order; "
            f"found={numbers}"
        )
    for token in (
        "references/dna-principles.md",
        "PASS only means",
        "Reality has final authority",
        "independent lineage",
    ):
        if token not in dna_skill:
            errors.append(f"scp-dna/SKILL.md missing required operational contract: {token}")
    for token in (
        "PASS ≠ TRUE",
        "Reality có quyền cuối cùng",
        "Không tin một tác nhân",
        "Trí nhớ không phá hủy",
        "Sự tự chủ phân tán",
    ):
        if token not in dna_ref:
            errors.append(f"dna-principles.md missing required principle marker: {token}")

    review = _read(root, ".agents/skills/scp-skill-review/SKILL.md", errors)
    for dimension in ("C1", "C2", "C3", "C4", "C5", "C6"):
        if dimension not in review:
            errors.append(f"scp-skill-review missing dimension {dimension}")
    if "A–D" not in review and "A-D" not in review:
        errors.append("scp-skill-review missing A-D evidence-level contract")
    for verdict in ("VERIFIED", "INSUFFICIENT", "CONTRADICTED", "UNKNOWN", "HUMAN_REVIEW"):
        if verdict not in review:
            errors.append(f"scp-skill-review missing verdict {verdict}")

    workflow_calls: dict[str, int] = {}
    for relative, minimum in MANDATORY_WORKFLOW_CALLS.items():
        text = _read(root, relative, errors)
        count = text.count(GATE_COMMAND)
        workflow_calls[relative] = count
        if count < minimum:
            errors.append(
                f"{relative}: requires >= {minimum} SCP Skill+DNA gate call(s), found {count}"
            )

    arch = _read(root, ".github/workflows/scp-architecture-snapshot-audit.yml", errors)
    if "skill-dna-governance:" not in arch:
        errors.append("architecture audit must include mandatory skill-dna-governance job")
    for job in (
        "core-matrix",
        "semantic-acceptance",
        "security-mutation",
        "reality-runtime",
        "dashboard",
        "manifest-provenance",
        "snapshot-draft",
        "final-verdict",
    ):
        match = re.search(
            rf"(?ms)^  {re.escape(job)}:\n(.*?)(?=^  [A-Za-z0-9_-]+:\n|\Z)",
            arch,
        )
        if not match:
            errors.append(f"architecture audit missing mandatory job: {job}")
            continue
        block = match.group(1)
        needs_lines = "\n".join(
            line.strip() for line in block.splitlines() if line.strip().startswith("needs:")
        )
        if "skill-dna-governance" not in needs_lines:
            errors.append(
                f"architecture job {job} must depend on skill-dna-governance"
            )

    result: dict[str, object] = {
        "schema_version": "scp-skill-dna-gate-v1",
        "status": "PASS_WITHIN_SCOPE" if not errors else "FAIL",
        "skill_count": len(discovered),
        "expected_skill_count": len(EXPECTED_SKILLS),
        "dna_principle_count": len(numbers),
        "workflow_gate_calls": workflow_calls,
        "index_missing": index_status,
        "errors": errors,
        "rule": (
            "Mandatory test/release suites must load the governed SCP Skill pack "
            "and SCP DNA contract on the exact candidate SHA; uncertainty fails closed."
        ),
    }
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=".")
    parser.add_argument(
        "--report",
        default="reports/skill_dna/skill-dna-gate.json",
    )
    args = parser.parse_args()
    root = Path(args.root)
    result = verify(root)
    report = root / args.report
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] == "PASS_WITHIN_SCOPE" else 1


if __name__ == "__main__":
    raise SystemExit(main())
