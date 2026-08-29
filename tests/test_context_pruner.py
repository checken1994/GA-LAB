"""Mảnh ghép #32/#44 — Context Pruner với AST heat scoring (hermetic)."""
from __future__ import annotations

from scp.core.context_pruner import build_context_from_file, prune_source, score_functions

SAMPLE = '''\
"""Module docstring — phải được giữ."""

import os


def cold_helper(x):
    """Totally unrelated helper."""
    return x * 2


def fetch_user_profile(user_id):
    """Loads and validates the user profile for authentication."""
    profile = {"id": user_id, "name": "a"}
    if not profile:
        raise ValueError("no profile")
    return profile


def another_cold():
    return "nothing relevant"


def validate_password_policy(password):
    """Authentication: password policy check — BUG IS HERE."""
    if len(password) < 8:
        raise ValueError("weak password")
    return True
'''


def test_bug_function_always_kept_verbatim():
    pruned = prune_source(SAMPLE, bug_line=0, description="anything")  # bug_line ngoài — không hàm chứa
    # validate_password_policy vẫn phải hiện diện vì chỉ có nó match... không: dùng bug_line trong hàm
    pruned = prune_source(SAMPLE, bug_line=SAMPLE.splitlines().index('    if len(password) < 8:') + 1, description="")
    assert "if len(password) < 8:" in pruned
    assert "raise ValueError" in pruned


def test_description_name_match_ranks_hot():
    scored = score_functions(SAMPLE, bug_line=0, description="fix password policy authentication bug")
    names = [s["name"] for s in scored[:2]]
    assert "validate_password_policy" in names
    top = scored[0]
    assert top["contains_bug"] is True or top["name"] == "validate_password_policy"


def test_cold_functions_are_folded_with_marker():
    pruned = prune_source(SAMPLE, bug_line=0, description="password policy authentication")
    assert "[folded: cold context" in pruned
    # hàm nóng giữ nguyên thân
    assert "raise ValueError(\"weak password\")" in pruned
    # hàm nguội bị gấp — thân biến mất
    assert "Totally unrelated helper." not in pruned
    assert "nothing relevant" not in pruned


def test_imports_and_docstring_survive():
    pruned = prune_source(SAMPLE, bug_line=0, description="password policy")
    assert "import os" in pruned
    assert "Module docstring" in pruned


def test_syntax_error_returns_source_unchanged():
    broken = "def broken(:\n    pass\n"
    assert prune_source(broken, 1, "x") == broken


def test_build_context_fallback_on_missing_file(tmp_path):
    result = build_context_from_file(str(tmp_path / "nope.py"), 10, "desc", fallback_lines=5)
    assert result == ""
