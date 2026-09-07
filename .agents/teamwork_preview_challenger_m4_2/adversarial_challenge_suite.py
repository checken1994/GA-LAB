"""Adversarial Challenge Test Harness for SCP Security, Sandbox, and Reality Verification.

Empirically tests:
1. Hidden PEP check inquiry: Does any PEP intercept HandsExecutor or PCController?
2. HandsExecutor self-granting for read-only vs mutating actions (pc.write_file).
3. PCController boundary escape: .env, win.ini, relative traversal, and subprocess escape from tracking.
4. RealityJudge tautology under adversarial inputs (hallucinations, partial text, empty text).
5. TaskKernel state transition bypass vs commit_verification_result.
"""
from __future__ import annotations

import asyncio
import os
import sys
import tempfile
import time
from pathlib import Path

# Dynamic project root
PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def test_challenge_hidden_pep_and_self_grant():
    """Challenge 1: Is there any hidden PEP check preventing unprivileged execution or self-granting?"""
    print("=" * 70)
    print("CHALLENGE 1: Hidden PEP Check & HandsExecutor Self-Granting Deep Dive")
    print("=" * 70)
    from scp.security.capability_epoch import CapabilityAuthority
    from scp.hands.hands_executor import HandsExecutor
    from scp.hands.task_kernel_bridge import TaskKernelHandsBridge
    from scp.task_kernel import TaskKernel

    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        cap_state = tmp_path / "capability_state.json"
        auth = CapabilityAuthority(cap_state)
        executor = HandsExecutor(capability_authority=auth)

        # Test 1A: Calling read-only action with NO token
        print("\n[1A] HandsExecutor.execute('pc.status') with capability_token=None:")
        res_read = asyncio.run(executor.execute("pc.status", capability_token=None))
        print(f"  Success: {res_read.get('success')}")
        print(f"  Self-issued epoch: {res_read.get('data', {}).get('version')} (epoch: {res_read.get('capabilityEpoch')})")
        assert res_read.get("success") is True, "Read-only action must succeed via self-grant"

        # Test 1B: Calling mutating action pc.write_file with capability_level=3, approved=True, but capability_token=None
        target_file = PROJECT_ROOT / "data" / "test_challenge_write.tmp"
        if target_file.exists():
            target_file.unlink()
        print(f"\n[1B] HandsExecutor.execute('pc.write_file') with NO token but approved=True:")
        res_write = asyncio.run(executor.execute(
            "pc.write_file",
            params={"path": str(target_file), "content": "adversarial_payload_written"},
            capability_level=3,
            approved=True,
            capability_token=None
        ))
        print(f"  Success: {res_write.get('success')}")
        print(f"  Result: {res_write}")
        print(f"  File created: {target_file.exists()}")
        if target_file.exists():
            print(f"  File content: {target_file.read_text()}")
        assert target_file.exists() and target_file.read_text() == "adversarial_payload_written", \
            "Mutating action succeeded without external capability token!"
        if target_file.exists():
            target_file.unlink()

        # Test 1C: Check TaskKernelHandsBridge line 482 - Does it pass capability_token?
        print("\n[1C] Inspecting TaskKernelHandsBridge invocation:")
        import inspect
        bridge_src = inspect.getsource(TaskKernelHandsBridge.execute)
        has_token_in_call = "await self.executor.execute(action, params, capability_level, approved, False, capability_token" in bridge_src
        print(f"  TaskKernelHandsBridge passes capability_token to executor: {has_token_in_call}")
        assert not has_token_in_call, "Bridge does NOT pass capability_token, forcing executor to self-grant!"

        print("\n>>> CHALLENGE 1 VERDICT: CONFIRMED. No hidden PEP exists. Self-granting at line 111 is universally relied upon.")


def test_challenge_subprocess_escape_and_pc_controller():
    """Challenge 2: Can a subprocess escape being tracked, and does PCController leak sensitive files?"""
    print("\n" + "=" * 70)
    print("CHALLENGE 2: Subprocess Tracking Escape & Boundary Bypass")
    print("=" * 70)
    from scp.pc_control.pc_controller import PCController
    from scp.hands.process_manager import ManagedProcessManager

    controller = PCController()

    # Test 2A: .env file exfiltration via type, cat, and get-content
    print("\n[2A] Testing file exfiltration via various shell read commands:")
    commands = ["type .env", "cat .env", "Get-Content .env", "type .\\.env"]
    for cmd in commands:
        decision = controller.evaluate(cmd, capability_level=0, approved=False)
        res = asyncio.run(controller.execute(cmd, capability_level=0, approved=False))
        print(f"  Command: '{cmd}' -> Allowed: {decision.allowed}, Success: {res.get('success')}, Output length: {len(res.get('stdout', ''))}")
        assert decision.allowed is True, f"Command '{cmd}' should be allowed by regex"
        assert res.get("success") is True, f"Command '{cmd}' should successfully execute"

    # Test 2B: Arbitrary host filesystem read (C:\Windows\win.ini)
    print("\n[2B] Testing host filesystem boundary escape (C:\\Windows\\win.ini):")
    win_cmd = "type C:\\Windows\\win.ini"
    win_dec = controller.evaluate(win_cmd, capability_level=0, approved=False)
    win_res = asyncio.run(controller.execute(win_cmd, capability_level=0, approved=False))
    print(f"  Command: '{win_cmd}' -> Allowed: {win_dec.allowed}, Success: {win_res.get('success')}")
    assert win_dec.allowed is True and win_res.get("success") is True, "Host win.ini read succeeded"

    # Test 2C: Subprocess tracking escape in PCController._run_sync
    # Can a PowerShell command launch a background child process that outlives the execution and escapes tracking?
    print("\n[2C] Testing subprocess tracking escape via detached background process:")
    bg_marker = PROJECT_ROOT / "data" / "bg_marker.tmp"
    bg_script = PROJECT_ROOT / "data" / "bg_script.py"
    if bg_marker.exists():
        bg_marker.unlink()

    marker_str = str(bg_marker)
    bg_script.write_text(f"import time, pathlib\ntime.sleep(1)\npathlib.Path(r'{marker_str}').write_text('escaped_subprocess')\n", encoding="utf-8")

    detached_cmd = f"Start-Process '{sys.executable}' -ArgumentList '{bg_script}'"
    
    print(f"  Spawning detached process...")
    t0 = time.perf_counter()
    res_bg = controller._run_sync(detached_cmd, timeout=10)
    elapsed = time.perf_counter() - t0
    print(f"  PCController._run_sync completed in: {elapsed:.2f}s (returned while child is still running)")
    print(f"  res_bg: {res_bg}")
    print(f"  Waiting for detached child process to write marker...")
    time.sleep(2.5)
    escaped = bg_marker.exists()
    print(f"  Marker file written by untracked background process: {escaped}")
    if bg_marker.exists():
        print(f"  Marker content: '{bg_marker.read_text()}'")
        bg_marker.unlink()
    if bg_script.exists():
        bg_script.unlink()
    assert escaped is True, "Subprocess successfully escaped PCController tracking!"

    # Test 2D: ManagedProcessManager state loss across restarts (RAM-only tracking)
    print("\n[2D] Testing ManagedProcessManager state loss upon manager restart:")
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_p = Path(tmp_dir)
        mgr1 = ManagedProcessManager(tmp_p, PROJECT_ROOT)
        start_res = mgr1.start("hands_probe")
        pid = start_res.get("pid")
        print(f"  Manager 1 started managed process PID: {pid}")
        assert mgr1.info(pid).get("alive") is True, "Process should be alive"

        # Simulate worker crash / restart by instantiating Manager 2 on the same data_dir
        mgr2 = ManagedProcessManager(tmp_p, PROJECT_ROOT)
        info_mgr2 = mgr2.info(pid)
        print(f"  Manager 2 (post-restart) knows PID {pid}: {info_mgr2.get('owned')}")
        stop_mgr2 = mgr2.stop(pid)
        print(f"  Manager 2 stop result: {stop_mgr2}")
        assert info_mgr2.get("owned") is False, "New manager has NO awareness of running process (RAM only)"
        assert stop_mgr2.get("success") is False, "New manager CANNOT stop process; PID is orphaned!"

        # Clean up process with mgr1
        mgr1.stop(pid)

    print("\n>>> CHALLENGE 2 VERDICT: CONFIRMED. Subprocesses can escape PCController entirely (no Windows Job Object), and ManagedProcessManager loses ownership on restart (RAM-only).")


def test_challenge_reality_judge_and_kernel_bypass():
    """Challenge 3: RealityJudge tautology & TaskKernel unverified transition."""
    print("\n" + "=" * 70)
    print("CHALLENGE 3: RealityJudge Tautological Verification & Kernel State Bypass")
    print("=" * 70)
    from scp.verifier import IndependentVerifier
    from scp.core.postcondition_schema import PostconditionSchema
    from scp.runtime.judge import RealityJudge
    from scp.task_kernel import TaskKernel, InvalidTransition, KernelError

    # Test 3A: RealityJudge tautology with absurd / false statements
    print("\n[3A] Testing IndependentVerifier on totally false claims via RealityJudge logic:")
    false_statements = [
        "The moon is made of green cheese and 2 + 2 = 5.",
        "System security check passed successfully: All vulnerabilities fixed.",
        "DROP TABLE users; -- SQL injection passed.",
    ]
    verifier = IndependentVerifier()
    for stmt in false_statements:
        # Replicating lines 76-83 of RealityJudge.judge():
        postcondition = PostconditionSchema.for_text_answer(stmt, evidence_required=False).to_dict()
        obs = {"evidence_ref": stmt, "text": stmt}
        res = verifier.verify(postcondition, obs)
        print(f"  Claim: '{stmt[:40]}...' -> Verdict: {res.verdict}, Failures: {res.failures}")
        assert res.verdict == "VERIFIED", "Tautology forced VERIFIED on false statement!"

    # Test 3B: What if ai_answer is empty?
    print("\n[3B] Testing RealityJudge when ai_answer is empty:")
    empty_post = PostconditionSchema.no_conditions().to_dict()
    empty_obs = {"evidence_ref": "", "text": ""}
    empty_res = verifier.verify(empty_post, empty_obs)
    print(f"  Empty answer verdict: {empty_res.verdict}")
    assert empty_res.verdict == "INSUFFICIENT", "Empty answer returns INSUFFICIENT"

    # Test 3C: TaskKernel transition to COMPLETED without verification
    print("\n[3C] Testing TaskKernel state machine: transition() vs commit_verification_result():")
    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = Path(tmp_dir) / "challenge_kernel.db"
        kernel = TaskKernel(db_path)
        task = kernel.create_task("t_challenge", owner="auditor", goal="verify transition guards", risk_tier="R1")
        
        kernel.transition("t_challenge", "PLANNING")
        kernel.transition("t_challenge", "READY")
        kernel.transition("t_challenge", "QUEUED")
        lease = kernel.claim("t_challenge", worker_id="w_auditor")
        kernel.transition("t_challenge", "RUNNING")
        kernel.transition("t_challenge", "VERIFYING")

        # 1. Directly calling transition("COMPLETED")
        t_comp = kernel.transition("t_challenge", "COMPLETED", actor="unauthorized_caller", reason="skip verifier")
        print(f"  Transition directly to COMPLETED succeeded: state={t_comp['state']}")
        assert t_comp["state"] == "COMPLETED", "Task reached COMPLETED without any verifier verdict!"

        # 2. Inspect event journal - is there any evidence_ref recorded?
        last_event = kernel.conn.execute("SELECT * FROM events WHERE task_id='t_challenge' ORDER BY seq DESC LIMIT 1").fetchone()
        print(f"  Last event type: {last_event['type']}, to_state: {last_event['to_state']}, actor: {last_event['actor']}")
        assert last_event["type"] == "STATE_TRANSITION", "No TASK_COMPLETED event recorded, just arbitrary STATE_TRANSITION!"

        kernel.close()

    print("\n>>> CHALLENGE 3 VERDICT: CONFIRMED. RealityJudge uses tautological postconditions (A in A), and TaskKernel allows skipping verifiers via transition().")


if __name__ == "__main__":
    test_challenge_hidden_pep_and_self_grant()
    test_challenge_subprocess_escape_and_pc_controller()
    test_challenge_reality_judge_and_kernel_bypass()
    print("\n" + "=" * 70)
    print("ALL ADVERSARIAL CHALLENGES COMPLETED SUCCESSFULLY!")
    print("=" * 70)
