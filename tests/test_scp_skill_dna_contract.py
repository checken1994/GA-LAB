from __future__ import annotations

import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SKILLS_ROOT = ROOT / ".agents" / "skills"
DNA_SKILL = SKILLS_ROOT / "scp-dna" / "SKILL.md"
DNA_PRINCIPLES = SKILLS_ROOT / "scp-dna" / "references" / "dna-principles.md"
RELEASE_SKILL = SKILLS_ROOT / "scp-release-evidence-gate" / "SKILL.md"
GATE_BINDINGS = SKILLS_ROOT / "release-gate-skill-dna-bindings.json"
RC_WORKFLOW = ROOT / ".github" / "workflows" / "scp-rc-promotion.yml"
STRICT_AUDIT = ROOT / "scripts" / "run_system_audit_strict.py"

REQUIRED_RELEASE_GATES = {
    "compile_import",
    "unit_integration",
    "semantic_parity",
    "skill_scp_dna_contract",
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
}


def _read(path: Path) -> str:
    assert path.is_file(), f"required SCP artifact missing: {path.relative_to(ROOT)}"
    return path.read_text(encoding="utf-8")


def _frontmatter_name(text: str) -> str | None:
    match = re.search(r"(?m)^name:\s*([^\n]+)\s*$", text)
    return match.group(1).strip() if match else None


def _load_bindings() -> dict:
    payload = json.loads(_read(GATE_BINDINGS))
    assert payload.get("schema_version") == "scp-release-gate-skill-dna-v1"
    assert isinstance(payload.get("policy"), dict)
    assert isinstance(payload.get("gates"), dict)
    return payload


def test_every_scp_skill_has_named_skill_manifest() -> None:
    assert SKILLS_ROOT.is_dir(), ".agents/skills must exist"
    skill_dirs = sorted(path for path in SKILLS_ROOT.iterdir() if path.is_dir())
    assert skill_dirs, "SCP skill catalog must not be empty"
    for skill_dir in skill_dirs:
        manifest = skill_dir / "SKILL.md"
        text = _read(manifest)
        assert text.startswith("---\n"), f"{manifest} must start with YAML frontmatter"
        assert _frontmatter_name(text) == skill_dir.name, (
            f"{manifest} frontmatter name must match directory {skill_dir.name!r}"
        )


def test_scp_dna_is_exactly_29_principles_with_release_critical_invariants() -> None:
    skill = _read(DNA_SKILL)
    principles = _read(DNA_PRINCIPLES)

    assert "29 core principles" in skill
    assert "full 26-principle" not in skill.lower(), "stale 26-principle wording weakens DNA contract"
    assert "Reality has final authority (DNA #26)" in skill
    assert "PASS only means" in skill

    headings = [int(n) for n in re.findall(r"(?m)^##\s+(\d+)\.\s+", principles)]
    assert headings == list(range(1, 30)), f"expected ordered DNA #1..#29, got {headings}"

    critical = {
        5: ("lineage", "đồng thuận"),
        22: ("PASS", "Goodhart"),
        26: ("Reality", "quyền cuối cùng"),
        28: ("rollback", "Tier-1 Guard"),
        29: ("Planner", "Judge", "Kernel"),
    }
    for number, needles in critical.items():
        block_match = re.search(
            rf"(?ms)^##\s+{number}\.\s+.*?(?=^##\s+\d+\.|\Z)", principles
        )
        assert block_match, f"DNA #{number} block missing"
        block = block_match.group(0)
        for needle in needles:
            assert needle in block, f"DNA #{number} lost invariant {needle!r}"


def test_release_evidence_skill_is_fail_closed_and_reality_grounded() -> None:
    release = _read(RELEASE_SKILL)
    for required in (
        "Static",
        "Runtime",
        "Golden task",
        "Chaos",
        "Security",
        "Reproducibility",
        "BLOCKED",
        "Reality",
    ):
        assert required in release, f"release evidence skill lost {required!r}"
    assert "Một gate thiếu evidence là `BLOCKED`" in release


def test_every_mandatory_release_gate_has_domain_skill_and_scp_dna_binding() -> None:
    payload = _load_bindings()
    policy = payload["policy"]
    gates = payload["gates"]

    assert set(gates) == REQUIRED_RELEASE_GATES, (
        "Skill/DNA binding manifest must cover exactly the mandatory RC gates; "
        f"missing={sorted(REQUIRED_RELEASE_GATES - set(gates))}, "
        f"extra={sorted(set(gates) - REQUIRED_RELEASE_GATES)}"
    )
    assert policy.get("mandatory_skill") == "scp-dna"
    mandatory_dna = set(policy.get("mandatory_dna_invariants", []))
    assert mandatory_dna == {22, 26}, "PASS≠TRUE and Reality authority must be universal"

    for gate, binding in gates.items():
        skills = binding.get("skills")
        dna = binding.get("dna")
        assert isinstance(skills, list) and len(skills) >= 2, (
            f"{gate}: bind SCP DNA plus at least one domain-specific Skill"
        )
        assert skills[0] == "scp-dna", f"{gate}: scp-dna must be the first governing Skill"
        assert len(skills) == len(set(skills)), f"{gate}: duplicate Skill binding"
        for skill_name in skills:
            skill_path = SKILLS_ROOT / skill_name / "SKILL.md"
            text = _read(skill_path)
            assert _frontmatter_name(text) == skill_name, f"{gate}: invalid Skill {skill_name}"

        assert isinstance(dna, list) and dna, f"{gate}: missing DNA invariants"
        assert dna == sorted(set(dna)), f"{gate}: DNA list must be sorted and unique"
        assert all(isinstance(n, int) and 1 <= n <= 29 for n in dna), (
            f"{gate}: DNA references must be in #1..#29"
        )
        assert mandatory_dna.issubset(dna), (
            f"{gate}: every mandatory gate must include DNA #22 PASS≠TRUE and #26 Reality authority"
        )


def test_rc_verdict_cannot_claim_pass_for_an_unbound_gate() -> None:
    rc = _read(RC_WORKFLOW)
    payload = _load_bindings()

    for gate in payload["gates"]:
        marker = f"'{gate}': 'PASS'"
        assert rc.count(marker) >= 2, (
            f"{gate}: both frozen RC and fresh main handoff verdicts must record this gate"
        )


def test_mandatory_release_paths_execute_skill_and_dna_contract() -> None:
    rc = _read(RC_WORKFLOW)
    strict = _read(STRICT_AUDIT)
    test_path = "tests/test_scp_skill_dna_contract.py"

    assert test_path in rc, "RC workflow must execute the Skill + SCP DNA contract explicitly"
    assert "skill_scp_dna_contract" in rc, "RC verdict must record the Skill + SCP DNA gate"
    assert test_path in strict, "strict system audit must execute Skill + SCP DNA explicitly"
    assert "skill_scp_dna_contract" in strict, "strict audit report must name the Skill + SCP DNA gate"
    assert str(GATE_BINDINGS.relative_to(ROOT)).replace("\\", "/") in _read(GATE_BINDINGS) or GATE_BINDINGS.is_file()
