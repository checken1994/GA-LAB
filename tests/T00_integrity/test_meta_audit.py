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
