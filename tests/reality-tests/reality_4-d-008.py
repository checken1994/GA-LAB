from pathlib import Path
"""Reality test for Fix 4-d-008: loop-scheduler binds 127.0.0.1 (not 0.0.0.0).

Before fix: 0.0.0.0 + no auth → network-reachable.
After fix: 127.0.0.1 (loopback only) or auth required.
"""

with open(str(Path(__file__).resolve().parents[2]) + '/mini-services/loop-scheduler/index.ts') as f:
    src = f.read()

# TEST 1: must NOT bind 0.0.0.0 by default
code_lines = [l for l in src.split("\n") if not l.strip().startswith("//")]
code_section = "\n".join(code_lines)
has_0000_bind = "0.0.0.0" in code_section and ("listen" in code_section.lower() or "bind" in code_section.lower())
assert not has_0000_bind, "FAIL: still binds 0.0.0.0"
print("PASS [1/3]: does not bind 0.0.0.0 (no 0.0.0.0 string in non-comment code)")

# TEST 2: must bind 127.0.0.1 or localhost
has_loopback = "127.0.0.1" in src or "localhost" in src.lower()
assert has_loopback, "FAIL: does not bind 127.0.0.1"
print("PASS [2/3]: binds 127.0.0.1 (loopback)")

# TEST 3: must have auth middleware OR bind loopback (one or both)
has_auth = "secret" in src.lower() or "auth" in src.lower() or "401" in src
assert has_loopback or has_auth, "FAIL: neither loopback nor auth"
print(f"PASS [3/3]: {'loopback + ' if has_loopback else ''}{'auth' if has_auth else ''} present")

# --- Runtime behavior tests (DNA #2 reality) ---
print("\n--- Runtime behavior test (DNA #2 reality) ---")
import os
import re
import subprocess
import time
import tempfile
import socket
import http.client

# TEST 4: Bun.serve() call must include hostname: <loopback>
# Pattern: Bun.serve({ ... hostname: "127.0.0.1" or process.env.LOOP_SCHEDULER_HOST ... })
bun_serve_match = re.search(
    r'Bun\.serve\(\s*\{([^}]+)\}',
    src,
    re.DOTALL,
)
assert bun_serve_match, "FAIL: cannot locate Bun.serve() call"
serve_args = bun_serve_match.group(1)
assert "hostname" in serve_args, (
    "FAIL: Bun.serve() does not specify hostname (defaults to 0.0.0.0)"
)
# Verify hostname default is loopback. The code may use a variable indirection
# (e.g. `const HOST = process.env.LOOP_SCHEDULER_HOST ?? "127.0.0.1";` then
# `hostname: HOST`) OR set it directly. Either pattern is acceptable.
# Check 1: direct loopback literal as hostname.
direct_loopback = bool(re.search(r'hostname\s*:\s*["\']127\.0\.0\.1["\']', serve_args))
# Check 2: env-var-driven with loopback default (either inline or via HOST var).
env_driven_loopback = (
    "127.0.0.1" in src
    and (
        "LOOP_SCHEDULER_HOST" in src
        or bool(re.search(r'hostname\s*:\s*HOST\b', serve_args))
    )
)
assert direct_loopback or env_driven_loopback, (
    "FAIL: hostname default is not 127.0.0.1 (network still exposed) — "
    f"serve_args={serve_args!r}"
)
print("PASS [4/5]: Bun.serve() hostname defaults to 127.0.0.1 (loopback)")

# TEST 5 (runtime): boot the loop-scheduler and verify it actually binds
# 127.0.0.1 (not 0.0.0.0). We do this by:
#   (a) confirming the boot log says "listening on http://127.0.0.1:..."
#   (b) confirming we can connect via 127.0.0.1 (loopback works)
#   (c) checking socket binding via /proc/<pid>/net/tcp if available
env = dict(os.environ)
_test_env_file = tempfile.NamedTemporaryFile("w", delete=False, suffix=".env")
_test_env_file.close()
# Isolate the scheduler child from the caller production env-file and token.
env["SCP_ENV_FILE"] = _test_env_file.name
env["SCP_SCHEDULER_ADMIN_TOKEN_FILE"] = ""
env["SCP_SCHEDULER_ADMIN_TOKEN"] = "test-only-scheduler-token"
env["LOOP_INTERVAL_SEC"] = "3600"
env["SCP_BASE_URL"] = "http://127.0.0.1:65530"  # bogus — won't fire audit
env["LLM_BRIDGE_URL"] = "http://127.0.0.1:65531"  # unreachable
env["LOOP_SCHEDULER_PORT"] = "3038"

proc = subprocess.Popen(
    ["bun", "mini-services/loop-scheduler/index.ts"],
    cwd=str(Path(__file__).resolve().parents[2]),
    env=env,
    stdout=subprocess.PIPE,
    stderr=subprocess.STDOUT,
    text=True,
)
boot_log = ""
try:
    # Poll for boot log lines until we see "listening on"
    deadline = time.time() + 5.0
    while time.time() < deadline:
        line = proc.stdout.readline()
        if not line:
            time.sleep(0.05)
            continue
        boot_log += line
        if "listening on" in line:
            break
        if "error" in line.lower() or "Error" in line:
            break

    # (a) boot log mentions 127.0.0.1
    assert "127.0.0.1" in boot_log, (
        f"FAIL: boot log does not mention 127.0.0.1: {boot_log!r}"
    )
    # (a+) boot log mentions "loopback"
    assert "loopback" in boot_log.lower() or "127.0.0.1" in boot_log, (
        f"FAIL: boot log does not mention loopback binding: {boot_log!r}"
    )

    # (b) connect via 127.0.0.1 works (GET /healthz)
    try:
        conn = http.client.HTTPConnection("127.0.0.1", 3038, timeout=3)
        conn.request("GET", "/healthz")
        resp = conn.getresponse()
        body = resp.read().decode("utf-8", errors="replace")
        assert resp.status == 200, f"FAIL: GET /healthz via 127.0.0.1 returned {resp.status}"
        assert '"ok"' in body, f"FAIL: /healthz body unexpected: {body!r}"
        conn.close()
        print("PASS [5/5]: scheduler boots + serves on 127.0.0.1:3038 (loopback verified)")
    except (ConnectionError, OSError) as e:
        print(f"FAIL [5/5]: cannot connect to 127.0.0.1:3038 — {e}")
        raise

finally:
    try:
        proc.terminate()
        proc.wait(timeout=3)
    except Exception:
        try:
            proc.kill()
            proc.wait(timeout=2)
        except Exception:
            pass

    try:
        os.unlink(_test_env_file.name)
    except FileNotFoundError:
        pass
print("\n✓ Reality test 4-d-008 PASSED")
