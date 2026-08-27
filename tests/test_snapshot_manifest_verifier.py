from __future__ import annotations

import importlib.util
from pathlib import Path


_MODULE_PATH = Path(__file__).parents[1] / "tools" / "verify_snapshot_manifest.py"
_SPEC = importlib.util.spec_from_file_location("verify_snapshot_manifest", _MODULE_PATH)
assert _SPEC is not None and _SPEC.loader is not None
_MODULE = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_MODULE)


def test_verification_target_uses_captured_commit_when_it_is_head() -> None:
    assert _MODULE.verification_target("head", "head", []) == (
        "head",
        "captured_git_tree",
    )


def test_verification_target_uses_captured_commit_when_it_is_direct_parent() -> None:
    assert _MODULE.verification_target("head", "captured", ["captured"]) == (
        "captured",
        "captured_git_tree",
    )


def test_verification_target_handles_squash_merge_head() -> None:
    """A PR merge ref may not retain the manifest's captured commit as a parent."""
    assert _MODULE.verification_target("squash-merge-head", "older-head", ["base"]) == (
        "squash-merge-head",
        "current_tree_excluding_manifest",
    )
