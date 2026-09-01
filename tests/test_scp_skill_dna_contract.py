from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SKILLS_ROOT = ROOT / ".agents" / "skills"
DNA_SKILL = SKILLS_ROOT / "scp-dna" / "SKILL.md"
DNA_PRINCIPLES = SKILLS_ROOT / "scp-dna" / "references" / "dna-principles.md"
RELEASE_SKILL = SKILLS_ROOT / "scp-release-evidence-gate" / "SKILL.md"
RC_WORKFLOW = ROOT / ".github" / "workflows" / "scp-rc-promotion.yml"
STRICT_AUDIT = ROOT / "scripts" / "run_system_audit_strict.py"


def _read(path: Path) -> str:
    assert path.is_file(), f"required SCP artifact missing: {path.relative_to(ROOT)}"
    return path.read_text(encoding="utf-8")


def _frontmatter_name(text: str) -> str | None:
    match = re.search(r"(?m)^name:\s*([^\n]+)\s*$", text)
    return match.group(1).strip() if match else None


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


def test_mandatory_release_paths_execute_skill_and_dna_contract() -> None:
    rc = _read(RC_WORKFLOW)
    strict = _read(STRICT_AUDIT)
    test_path = "tests/test_scp_skill_dna_contract.py"

    assert test_path in rc, "RC workflow must execute the Skill + SCP DNA contract explicitly"
    assert "skill_scp_dna_contract" in rc, "RC verdict must record the Skill + SCP DNA gate"
    assert test_path in strict, "strict system audit must execute Skill + SCP DNA explicitly"
    assert "skill_scp_dna_contract" in strict, "strict audit report must name the Skill + SCP DNA gate"
