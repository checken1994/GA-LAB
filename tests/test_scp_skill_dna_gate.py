from __future__ import annotations

from pathlib import Path

from tools.verify_scp_skill_dna_gate import ARCH_MANDATORY_SUITES, EXPECTED_SKILLS, GATE_COMMAND, verify


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _make_valid_tree(root: Path) -> None:
    names = list(EXPECTED_SKILLS)
    for name in names:
        _write(
            root / ".agents" / "skills" / name / "SKILL.md",
            "---\n"
            f"name: {name}\n"
            "description: Deterministic SCP skill description with explicit audit trigger.\n"
            "---\n\n"
            f"# {name}\n",
        )

    _write(
        root / ".agents" / "skills" / "scp-dna" / "SKILL.md",
        "---\n"
        "name: scp-dna\n"
        "description: Apply SCP DNA for evidence-driven release verification and audit.\n"
        "---\n\n"
        "references/dna-principles.md\n"
        "PASS only means scoped evidence passed.\n"
        "Reality has final authority.\n"
        "Use an independent lineage.\n",
    )
    principles = []
    for i in range(1, 30):
        title = f"Principle {i}"
        if i == 21:
            title = "Không tin một tác nhân"
        elif i == 22:
            title = "PASS ≠ TRUE"
        elif i == 26:
            title = "Reality có quyền cuối cùng"
        elif i == 28:
            title = "Trí nhớ không phá hủy"
        elif i == 29:
            title = "Sự tự chủ phân tán"
        principles.append(f"## {i}. {title}\ntext\n")
    _write(
        root / ".agents" / "skills" / "scp-dna" / "references" / "dna-principles.md",
        "\n".join(principles),
    )
    _write(
        root / ".agents" / "skills" / "scp-skill-review" / "SKILL.md",
        "---\n"
        "name: scp-skill-review\n"
        "description: Review the SCP skill pack with deterministic governance evidence.\n"
        "---\n\n"
        "C1 C2 C3 C4 C5 C6\nA–D\n"
        "VERIFIED INSUFFICIENT CONTRADICTED UNKNOWN HUMAN_REVIEW\n",
    )

    index_text = "\n".join(names)
    for relative in (".agents/skills/README.md", ".agents/AGENTS.md", ".agents/GEMINI.md"):
        _write(root / relative, index_text)

    for relative in (
        ".github/workflows/ci.yml",
        ".github/workflows/scp-release-gate.yml",
        ".github/workflows/scp-system-audit.yml",
    ):
        _write(root / relative, f"run: {GATE_COMMAND}\n")

    architecture = []
    for job in ARCH_MANDATORY_SUITES:
        architecture.append(f"  {job}:\n    steps:\n      - run: {GATE_COMMAND}\n")
    architecture.append(
        "  final-verdict:\n"
        "    needs: [core-matrix, semantic-acceptance, security-mutation, reality-runtime, dashboard, manifest-provenance, snapshot-draft]\n"
    )
    _write(root / ".github/workflows/scp-architecture-snapshot-audit.yml", "".join(architecture))


def test_valid_contract_passes(tmp_path: Path) -> None:
    _make_valid_tree(tmp_path)
    result = verify(tmp_path)
    assert result["status"] == "PASS_WITHIN_SCOPE", result["errors"]


def test_missing_skill_fails_closed(tmp_path: Path) -> None:
    _make_valid_tree(tmp_path)
    (tmp_path / ".agents" / "skills" / EXPECTED_SKILLS[0] / "SKILL.md").unlink()
    result = verify(tmp_path)
    assert result["status"] == "FAIL"
    assert any("missing SCP skills" in err for err in result["errors"])


def test_dna_numbering_gap_fails_closed(tmp_path: Path) -> None:
    _make_valid_tree(tmp_path)
    path = tmp_path / ".agents" / "skills" / "scp-dna" / "references" / "dna-principles.md"
    path.write_text(path.read_text(encoding="utf-8").replace("## 17. Principle 17\ntext\n", ""), encoding="utf-8")
    result = verify(tmp_path)
    assert result["status"] == "FAIL"
    assert any("exactly 1..29" in err for err in result["errors"])


def test_index_drift_fails_closed(tmp_path: Path) -> None:
    _make_valid_tree(tmp_path)
    path = tmp_path / ".agents" / "AGENTS.md"
    path.write_text(path.read_text(encoding="utf-8").replace(EXPECTED_SKILLS[-1], ""), encoding="utf-8")
    result = verify(tmp_path)
    assert result["status"] == "FAIL"
    assert any(".agents/AGENTS.md" in err for err in result["errors"])


def test_workflow_without_skill_dna_gate_fails_closed(tmp_path: Path) -> None:
    _make_valid_tree(tmp_path)
    path = tmp_path / ".github" / "workflows" / "scp-release-gate.yml"
    path.write_text("name: broken\n", encoding="utf-8")
    result = verify(tmp_path)
    assert result["status"] == "FAIL"
    assert any("scp-release-gate.yml" in err for err in result["errors"])


def test_mandatory_suite_without_own_gate_fails_closed(tmp_path: Path) -> None:
    _make_valid_tree(tmp_path)
    path = tmp_path / ".github" / "workflows" / "scp-architecture-snapshot-audit.yml"
    text = path.read_text(encoding="utf-8")
    text = text.replace(
        f"  reality-runtime:\n    steps:\n      - run: {GATE_COMMAND}\n",
        "  reality-runtime:\n    steps:\n      - run: echo missing-governance\n",
    )
    path.write_text(text, encoding="utf-8")
    result = verify(tmp_path)
    assert result["status"] == "FAIL"
    assert any("architecture suite reality-runtime" in err for err in result["errors"])


def test_repository_contract_is_self_checked() -> None:
    root = Path(__file__).resolve().parents[1]
    result = verify(root)
    assert result["status"] == "PASS_WITHIN_SCOPE", result["errors"]
