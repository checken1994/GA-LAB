import os
import subprocess
import sys

def main():
    print("=== Auditor M2 Forensic Probes ===")
    
    # Probe 1: Unset SCP_CAPABILITY_SECRET in clean subprocess
    env1 = {k: v for k, v in os.environ.items() if k != 'SCP_CAPABILITY_SECRET'}
    p1 = subprocess.run(
        [sys.executable, '-c', 'import scp.core.capability_token'],
        env=env1,
        capture_output=True,
        text=True
    )
    assert p1.returncode != 0, f"Expected non-zero returncode when unset, got {p1.returncode}"
    assert "MissingSecretError" in p1.stderr, f"MissingSecretError not in stderr: {p1.stderr}"
    assert "SCP_CAPABILITY_SECRET environment variable is missing or empty" in p1.stderr
    print("PROBE 1 (Unset) PASS: Raised MissingSecretError fail-closed")

    # Probe 2: Empty string SCP_CAPABILITY_SECRET
    env2 = dict(os.environ)
    env2['SCP_CAPABILITY_SECRET'] = ''
    p2 = subprocess.run(
        [sys.executable, '-c', 'import scp.core.capability_token'],
        env=env2,
        capture_output=True,
        text=True
    )
    assert p2.returncode != 0, f"Expected non-zero returncode when empty, got {p2.returncode}"
    assert "MissingSecretError" in p2.stderr, f"MissingSecretError not in stderr: {p2.stderr}"
    print("PROBE 2 (Empty string) PASS: Raised MissingSecretError fail-closed")

    # Probe 3: Whitespace only
    for ws in ['   ', '\t\n', '  \r\n\t  ']:
        env3 = dict(os.environ)
        env3['SCP_CAPABILITY_SECRET'] = ws
        p3 = subprocess.run(
            [sys.executable, '-c', 'import scp.core.capability_token'],
            env=env3,
            capture_output=True,
            text=True
        )
        assert p3.returncode != 0, f"Expected non-zero returncode when whitespace, got {p3.returncode}"
        assert "MissingSecretError" in p3.stderr, f"MissingSecretError not in stderr: {p3.stderr}"
    print("PROBE 3 (Whitespace variations) PASS: Raised MissingSecretError fail-closed")

    # Probe 4: Valid key & crypto check
    env4 = dict(os.environ)
    env4['SCP_CAPABILITY_SECRET'] = 'my-valid-secret-key-1234567890'
    code4 = (
        "import scp.core.capability_token as ct\n"
        "assert ct._SECRET == b'my-valid-secret-key-1234567890'\n"
        "token = ct.mint_token('test-issuer', '*', 1)\n"
        "res = ct.verify_token(token)\n"
        "assert res['valid'] is True\n"
        "forged = token[:-4] + 'ffff'\n"
        "res2 = ct.verify_token(forged)\n"
        "assert res2['valid'] is False\n"
        "print('PROBE_4_INTERNAL_SUCCESS')\n"
    )
    p4 = subprocess.run(
        [sys.executable, '-c', code4],
        env=env4,
        capture_output=True,
        text=True
    )
    assert p4.returncode == 0, f"Failed on valid key check: {p4.stderr}"
    assert "PROBE_4_INTERNAL_SUCCESS" in p4.stdout
    print("PROBE 4 (Valid key import & token verification) PASS")

    # Probe 5: Confirm MissingSecretError inherits from RuntimeError
    sys.path.insert(0, os.path.abspath("."))
    os.environ["SCP_CAPABILITY_SECRET"] = "dummy-for-probe-5-runtime-check"
    from scp.core.capability_token import MissingSecretError
    assert issubclass(MissingSecretError, RuntimeError)
    print("PROBE 5 (Inheritance check: MissingSecretError -> RuntimeError) PASS")

    # Probe 6: Non-ASCII UTF-8 secret stress test
    env6 = dict(os.environ)
    env6['SCP_CAPABILITY_SECRET'] = 'khóa-bí-mật-chữ-ký-bảo-mật-utf8-123456'
    code6 = (
        "import scp.core.capability_token as ct\n"
        "token = ct.mint_token('utf8-iss', 'write', 60)\n"
        "res = ct.verify_token(token)\n"
        "assert res['valid'] is True\n"
        "print('PROBE_6_UTF8_SUCCESS')\n"
    )
    p6 = subprocess.run(
        [sys.executable, '-c', code6],
        env=env6,
        capture_output=True,
        text=True
    )
    assert p6.returncode == 0, f"Failed on UTF-8 secret: {p6.stderr}"
    assert "PROBE_6_UTF8_SUCCESS" in p6.stdout
    print("PROBE 6 (UTF-8 secret resilience) PASS")

    print("ALL 6 AUDITOR FORENSIC PROBES PASSED EMPIRICALLY!")

if __name__ == "__main__":
    main()
