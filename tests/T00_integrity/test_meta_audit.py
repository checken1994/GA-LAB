import os
import glob

def test_meta_audit_no_skip_in_mandatory_tests():
    # Enforce that no mandatory tests are skipped for reasons other than OS incompatibility.
    root_dir = os.path.dirname(os.path.dirname(__file__))
    mandatory_dirs = ['T03_capability', 'T04_kernel', 'T05_gateway', 'T10_recovery']
    for d in mandatory_dirs:
        dir_path = os.path.join(root_dir, d)
        for filepath in glob.glob(os.path.join(dir_path, '*.py')):
            if filepath == __file__: continue
            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read()
                # If there's a skip, it MUST be OS-conditional.
                if 'pytest.skip' in content and 'platform.system' not in content:
                    assert False, f"Mandatory test {filepath} contains pytest.skip(). Mandatory tests must FAIL if blocked, unless OS-specific."

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
