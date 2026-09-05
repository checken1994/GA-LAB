import ast
import os
import glob

def _pytestmark_skip_marks(value_node):
    # Names of pytest.mark.{skip,xfail,skipif} referenced inside a pytestmark
    # assignment value (call form or bare attribute form).
    marks = set()
    if value_node is None:
        return marks
    for node in ast.walk(value_node):
        attr_node = node.func if isinstance(node, ast.Call) else node
        if (
            isinstance(attr_node, ast.Attribute)
            and attr_node.attr in {'skip', 'xfail', 'skipif'}
            and isinstance(attr_node.value, ast.Attribute)
            and attr_node.value.attr == 'mark'
            and isinstance(attr_node.value.value, ast.Name)
            and attr_node.value.value.id == 'pytest'
        ):
            marks.add(attr_node.attr)
    return marks

def _pytestmark_assignment(tree):
    # Yields (marks) for module/class-level `pytestmark = pytest.mark.skip(...)`
    # assignments. Whole-file silent skips hide from per-call/per-decorator
    # detectors, so they must be caught at the assignment itself.
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            targets, value = node.targets, node.value
        elif isinstance(node, (ast.AnnAssign, ast.AugAssign)):
            targets, value = [node.target], node.value
        else:
            continue
        if not any(isinstance(t, ast.Name) and t.id == 'pytestmark' for t in targets):
            continue
        marks = _pytestmark_skip_marks(value)
        if marks:
            yield sorted(marks)

def test_meta_audit_no_skip_in_mandatory_tests():
    # Enforce that no mandatory tests are skipped for reasons other than OS
    # incompatibility. AST-based: a quoted "pytest.skip" token inside a drift-
    # guard deny list is NOT a real skip call - only actual Call nodes count.
    # Covers ALL 12 gates T00-T11 (plus any extra T* dir), and also catches
    # module-level `pytestmark = pytest.mark.skip(...)` whole-file skips and
    # skip/xfail/skipif decorators, which the per-call scan cannot see.
    import ast
    root_dir = os.path.dirname(os.path.dirname(__file__))
    mandatory_dirs = sorted(glob.glob(os.path.join(root_dir, 'T[0-9][0-9]*')))
    assert len(mandatory_dirs) >= 12, f"expected all 12 gate dirs, found {mandatory_dirs}"
    for dir_path in mandatory_dirs:
        for filepath in glob.glob(os.path.join(dir_path, '*.py')):
            if filepath == __file__: continue
            with open(filepath, 'r', encoding='utf-8') as f:
                source = f.read()
            tree = ast.parse(source, filename=filepath)
            has_real_skip = any(
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr in {'skip', 'importorskip'}
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id == 'pytest'
                for node in ast.walk(tree)
            )
            # If there's a real skip call, it MUST be OS-conditional.
            if has_real_skip and 'platform.system' not in source:
                assert False, f"Mandatory test {filepath} contains a real pytest.skip() call. Mandatory tests must FAIL if blocked, unless OS-specific."
            # A whole-file pytestmark skip is never an OS exception.
            for marks in _pytestmark_assignment(tree):
                assert False, (
                    f"Mandatory test {filepath} assigns pytestmark = pytest.mark.{marks[0]}(...), "
                    "which silently skips the entire file. Mandatory tests must FAIL if blocked."
                )
            # Decorator-based skip/xfail/skipif on any test/class in a mandatory
            # gate must be OS-conditional, same rule as real skip calls. The
            # attribute NAME is matched receiver-agnostic (@pytest.mark.xfail is
            # a pytest->mark->xfail Attribute chain, not a bare Name).
            for scoped in ast.walk(tree):
                if not isinstance(scoped, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                    continue
                for dec in scoped.decorator_list:
                    dec_func = dec.func if isinstance(dec, ast.Call) else dec
                    if (
                        isinstance(dec_func, ast.Attribute)
                        and dec_func.attr in {'skip', 'xfail', 'skipif'}
                        and 'platform.system' not in source
                    ):
                        assert False, (
                            f"Mandatory test {filepath} decorates {scoped.name} with "
                            f"pytest.mark.{dec_func.attr}. Mandatory tests must FAIL if "
                            "blocked, unless OS-specific."
                        )

def test_meta_audit_no_assert_true():
    # Enforce that no tests just assert True
    root_dir = os.path.dirname(os.path.dirname(__file__))
    for filepath in glob.glob(os.path.join(root_dir, 'T*', '*.py')):
        if filepath == __file__: continue
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
            if 'assert ' + 'True' + '\n' in content:
                assert False, f"Test {filepath} contains 'assert True', which is a placeholder and violates Evidence rules."

def test_meta_audit_architecture_coverage():
    # Enforce that all 12 T directories exist
    root_dir = os.path.dirname(os.path.dirname(__file__))
    expected_dirs = [f'T{str(i).zfill(2)}' for i in range(12)]
    found_dirs = [d for d in os.listdir(root_dir) if d.startswith('T')]
    for expected in expected_dirs:
        assert any(d.startswith(expected) for d in found_dirs), f"Missing architectural test layer: {expected}"


def test_meta_audit_no_zero_collected_test_files():
    # A test file that collects zero tests is not evidence (historical lesson #8).
    import ast
    root_dir = os.path.dirname(os.path.dirname(__file__))
    for filepath in sorted(glob.glob(os.path.join(root_dir, 'T*', 'test_*.py'))):
        with open(filepath, 'r', encoding='utf-8') as f:
            tree = ast.parse(f.read(), filename=filepath)
        has_tests = any(
            isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith('test_')
            for node in ast.walk(tree)
        )
        assert has_tests, f"Test file {filepath} would collect zero tests and proves nothing."


def test_meta_audit_bare_scp_imports_must_resolve_to_real_production_symbols():
    # Bare (not try-guarded) imports of scp.* must point at REAL production
    # modules and symbols. This catches invented-module harnesses such as the
    # fake EpistemicScanner/IndependentVerifier pair manufactured 2026-09-01.
    # try/except-wrapped imports are the intentional BLOCKED-probe pattern and
    # are allowed to reference absent code.
    import ast
    import importlib
    import importlib.util
    root_dir = os.path.dirname(os.path.dirname(__file__))
    for filepath in sorted(glob.glob(os.path.join(root_dir, 'T*', 'test_*.py'))):
        with open(filepath, 'r', encoding='utf-8') as f:
            tree = ast.parse(f.read(), filename=filepath)
        inside_try = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Try):
                for child in ast.walk(node):
                    if child is not node:
                        inside_try.add(id(child))
        for node in ast.walk(tree):
            if id(node) in inside_try:
                continue
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.startswith('scp.'):
                        assert importlib.util.find_spec(alias.name) is not None, (
                            f"{filepath}: bare import of nonexistent production module {alias.name}"
                        )
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module and node.module.startswith('scp.'):
                assert importlib.util.find_spec(node.module) is not None, (
                    f"{filepath}: bare import of nonexistent production module {node.module}"
                )
                module = importlib.import_module(node.module)
                for alias in node.names:
                    if hasattr(module, alias.name):
                        continue
                    # `from pkg import name` is also valid when `name` is a
                    # submodule of pkg, not an attribute of its __init__.
                    try:
                        importlib.import_module(f"{node.module}.{alias.name}")
                    except ImportError as exc:
                        assert False, (
                            f"{filepath}: bare import of nonexistent production symbol "
                            f"{node.module}.{alias.name} ({exc})"
                        )


def test_meta_audit_no_recursive_pytest_and_no_live_repo_git_mutation():
    # Recursive full-pytest self-audit (fork-bomb lesson) and live-checkout git
    # mutation (T11 lesson 2026-09-01) are both forbidden. git commit/reset in
    # a test file is only tolerated when the file demonstrably isolates itself
    # in a temp repo (tmp_path / TemporaryDirectory / --git-dir / -C).
    root_dir = os.path.dirname(os.path.dirname(__file__))
    isolation_markers = ('--git-dir', 'GIT_DIR', 'tmp_path', 'TemporaryDirectory', '"-C"', "'-C'")
    for filepath in sorted(glob.glob(os.path.join(root_dir, 'T*', 'test_*.py'))):
        if filepath == __file__:
            continue  # this file legitimately quotes the forbidden patterns
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
        if 'pytest.main(' in content:
            assert False, f"Test {filepath} invokes pytest.main() - recursive full-pytest self-audit."
        for pattern in ('"git", "commit"', "'git', 'commit'", '"git", "reset"', "'git', 'reset'"):
            if pattern in content and not any(marker in content for marker in isolation_markers):
                assert False, (
                    f"Test {filepath} runs git commit/reset against the live checkout without an "
                    "isolated temp repo. Mandatory tests must never mutate main-checkout HEAD."
                )
import os
import glob
import pytest

def test_meta_audit_t05_no_forbidden_semantic_patterns():
    # Enforce that T05 doesn't use old paid semantics
    forbidden = [
        "paid -> free fallback",
        "paid -> free fallback",
        "[free, paid]",
        "[\"free\", \"paid\"]",
        "paid primary",
        "try paid first"
    ]
    root_dir = os.path.dirname(os.path.dirname(__file__))
    dir_path = os.path.join(root_dir, 'T05_gateway')
    for filepath in glob.glob(os.path.join(dir_path, '*.py')):
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read().lower()
            for pattern in forbidden:
                if pattern.lower() in content:
                    assert False, f"Test {filepath} contains forbidden semantic pattern: {pattern}"

from unittest.mock import patch
from tools.t00_meta_audit import audit_content, main

def test_t00_fa01_historical_skip_unchanged_passes_as_debt():
    baseline = "import pytest\n@pytest.mark.skip\ndef test_a(): pass"
    candidate = baseline
    new_v, debt = audit_content(candidate, baseline, "tests/test_a.py")
    assert len(new_v) == 0, "Historical skip should not be a new violation"
    assert len(debt) == 1
    assert "FA-01" in debt[0]

def test_t00_fa01_newly_added_skip_fails():
    baseline = "def test_a(): pass"
    candidate = "import pytest\n@pytest.mark.skip\ndef test_a(): pass"
    new_v, debt = audit_content(candidate, baseline, "tests/test_a.py")
    assert len(new_v) == 1, "New skip must be flagged as new violation"
    assert "FA-01" in new_v[0]
    assert len(debt) == 0

def test_t00_fa01_newly_added_xfail_fails():
    baseline = "def test_a(): pass"
    candidate = "import pytest\n@pytest.mark.xfail\ndef test_a(): pass"
    new_v, debt = audit_content(candidate, baseline, "tests/test_a.py")
    assert len(new_v) == 1
    assert "FA-01" in new_v[0]
    
def test_t00_fa01_pytest_skip_call_fails():
    baseline = "def test_a(): pass"
    candidate = "import pytest\ndef test_a(): pytest.skip('reason')"
    new_v, debt = audit_content(candidate, baseline, "tests/test_a.py")
    assert len(new_v) == 1
    assert "FA-01" in new_v[0]

def test_t00_fa04_historical_manufactured_green_passes_as_debt():
    baseline = 'def do():\n    return {"status": "VERIFIED"}'
    candidate = baseline
    new_v, debt = audit_content(candidate, baseline, "scp/engine.py")
    assert len(new_v) == 0
    assert len(debt) == 1
    assert "FA-04" in debt[0]

def test_t00_fa04_new_manufactured_green_fails():
    baseline = 'def do():\n    return {"status": "PENDING"}'
    candidate = 'def do():\n    return {"status": "VERIFIED"}'
    new_v, debt = audit_content(candidate, baseline, "scp/engine.py")
    assert len(new_v) == 1
    assert "FA-04" in new_v[0]
    assert len(debt) == 0

def test_t00_removal_of_historical_violation_passes():
    baseline = "import pytest\n@pytest.mark.skip\ndef test_a(): pass"
    candidate = "def test_a(): pass"
    new_v, debt = audit_content(candidate, baseline, "tests/test_a.py")
    assert len(new_v) == 0, "Removing a violation should pass"
    assert len(debt) == 0, "Debt should be cleared"

def test_t00_set_delta_swap_skip():
    baseline = "import pytest\n@pytest.mark.skip\ndef test_a(): pass\n\ndef test_b(): pass"
    candidate = "import pytest\ndef test_a(): pass\n\n@pytest.mark.skip\ndef test_b(): pass"
    
    new_v, debt = audit_content(candidate, baseline, "tests/test_a.py")
    assert len(new_v) == 1, "The new skip on test_b should be flagged"
    assert "test_b" in new_v[0]
    assert len(debt) == 0, "test_a skip is gone, so 0 debt"

def test_scp_tests_is_protected():
    baseline = "def test_a(): pass"
    candidate = "import pytest\n@pytest.mark.skip\ndef test_a(): pass"
    new_v, debt = audit_content(candidate, baseline, "scp/tests/test_a.py")
    assert len(new_v) == 1, "Must protect scp/tests/ as well"

@patch('tools.t00_meta_audit.POLICY_FILE')
def test_missing_policy_fails_closed(mock_policy_file):
    mock_policy_file.exists.return_value = False
    with pytest.raises(SystemExit) as e:
        main()
    assert e.value.code == 1


def test_fa01_skipif_importorskip_asyncdef():
    baseline = ""
    candidate = "import pytest\n@pytest.mark.skipif(True, reason='foo')\nasync def test_async_a():\n    pytest.importorskip('os')"
    new_v, debt = audit_content(candidate, baseline, "tests/test_a.py")
    
    assert any("skipif in test_async_a" in v for v in new_v)
    assert any("importorskip() in test_async_a" in v for v in new_v)

from tools.t00_meta_audit import check_real_test_deletion

@patch('tools.t00_meta_audit.get_real_nodeids')
@patch('tools.t00_meta_audit.get_baseline_nodeids')
def test_fa02_normal_test_deletion(mock_base, mock_cand):
    mock_base.return_value = {"tests/a.py::test_1", "tests/a.py::test_2"}
    mock_cand.return_value = {"tests/a.py::test_1"}
    v = check_real_test_deletion("origin/main")
    assert len(v) == 1
    assert "tests/a.py::test_2" in v[0]

@patch('tools.t00_meta_audit.get_real_nodeids')
@patch('tools.t00_meta_audit.get_baseline_nodeids')
def test_fa02_class_method_deletion(mock_base, mock_cand):
    mock_base.return_value = {"tests/a.py::TestA::test_1", "tests/a.py::TestB::test_1"}
    mock_cand.return_value = {"tests/a.py::TestA::test_1"}
    v = check_real_test_deletion("origin/main")
    assert len(v) == 1
    assert "TestB::test_1" in v[0]

@patch('tools.t00_meta_audit.get_real_nodeids')
@patch('tools.t00_meta_audit.get_baseline_nodeids')
def test_fa02_parametrized_reduction(mock_base, mock_cand):
    mock_base.return_value = {"tests/a.py::test_1[case1]", "tests/a.py::test_1[case2]"}
    mock_cand.return_value = {"tests/a.py::test_1[case1]"}
    v = check_real_test_deletion("origin/main")
    assert len(v) == 1
    assert "[case2]" in v[0]

@patch('tools.t00_meta_audit.get_real_nodeids')
@patch('tools.t00_meta_audit.get_baseline_nodeids')
def test_fa02_unchanged_passes(mock_base, mock_cand):
    mock_base.return_value = {"tests/a.py::test_1"}
    mock_cand.return_value = {"tests/a.py::test_1"}
    v = check_real_test_deletion("origin/main")
    assert len(v) == 0

@patch('tools.t00_meta_audit.get_real_nodeids')
@patch('tools.t00_meta_audit.get_baseline_nodeids')
def test_fa02_added_tests_passes(mock_base, mock_cand):
    mock_base.return_value = {"tests/a.py::test_1"}
    mock_cand.return_value = {"tests/a.py::test_1", "tests/a.py::test_2"}
    v = check_real_test_deletion("origin/main")
    assert len(v) == 0

@patch('tools.t00_meta_audit.subprocess.run')
def test_fa02_collection_error_fails_closed(mock_run):
    class FakeRes:
        returncode = 1
        stdout = "error"
        stderr = "error"
    mock_run.return_value = FakeRes()
    with pytest.raises(SystemExit) as e:
        check_real_test_deletion("origin/main")
    assert e.value.code == 1


import tempfile
from pathlib import Path as _Path

from tools.t00_meta_audit import get_fa01_signatures
from tools.verify_scp_target_test_coverage import _node_exists


def test_fa01_module_level_pytestmark_skip_is_new_violation():
    baseline = "import pytest\n"
    candidate = (
        "import pytest\n"
        "pytestmark = pytest.mark.skip(reason='whole file skipped')\n"
        "def test_a():\n    assert 1\n"
    )
    new_v, debt = audit_content(candidate, baseline, "tests/test_a.py")
    assert len(new_v) == 1, new_v
    assert "FA-01" in new_v[0]
    assert "pytestmark skip" in new_v[0]
    assert len(debt) == 0

def test_fa01_historical_module_pytestmark_is_tracked_as_debt():
    baseline = "import pytest\npytestmark = pytest.mark.skipif(False, reason='x')\n"
    new_v, debt = audit_content(baseline, baseline, "tests/test_a.py")
    assert len(new_v) == 0
    assert len(debt) == 1
    assert "pytestmark skipif" in debt[0]

def test_fa01_bare_pytestmark_attribute_assignment_is_flagged():
    baseline = ""
    candidate = "import pytest\npytestmark = pytest.mark.xfail\n"
    new_v, _debt = audit_content(candidate, baseline, "tests/test_a.py")
    assert len(new_v) == 1
    assert "pytestmark xfail" in new_v[0]

def test_fa01_unrelated_pytestmark_mark_is_not_flagged():
    candidate = "import pytest\npytestmark = pytest.mark.slow\n"
    new_v, debt = audit_content(candidate, "", "tests/test_a.py")
    assert len(new_v) == 0
    assert len(debt) == 0

def test_node_exists_requires_executable_asserting_test_node():
    with tempfile.TemporaryDirectory() as tmp:
        path = _Path(tmp) / "sample_tests.py"
        path.write_text(
            "def test_placeholder():\n    pass\n\n"
            "def helper_with_assert():\n    assert 1\n\n"
            "def test_real():\n    assert 1 == 1\n\n"
            "def test_uses_raises():\n    import pytest\n"
            "    with pytest.raises(ValueError):\n        raise ValueError()\n\n"
            "def test_nested_assert_only():\n"
            "    def inner():\n        assert 0\n\n"
            "class TestGroup:\n"
            "    def test_inner(self):\n        assert 1\n\n"
            "class TestHollow:\n"
            "    def test_hollow_member(self):\n        pass\n",
            encoding="utf-8",
        )
        assert _node_exists(path, ["test_real"]) is True
        assert _node_exists(path, ["test_uses_raises"]) is True
        assert _node_exists(path, ["TestGroup", "test_inner"]) is True
        assert _node_exists(path, ["test_placeholder"]) is False, "pass-only test must not validate a coverage claim"
        assert _node_exists(path, ["helper_with_assert"]) is False, "helper without test_ prefix must not validate a coverage claim"
        assert _node_exists(path, ["test_nested_assert_only"]) is False, "assert locked inside a nested def proves nothing"
        assert _node_exists(path, ["TestHollow", "test_hollow_member"]) is False, "class of pass-only tests proves nothing"
        assert _node_exists(path, ["test_missing"]) is False

def test_fa01_signatures_covers_module_pytestmark_directly():
    sigs = get_fa01_signatures(
        "import pytest\npytestmark = pytest.mark.skip(reason='r')\n"
    )
    assert any("pytestmark skip" in key for key in sigs)
