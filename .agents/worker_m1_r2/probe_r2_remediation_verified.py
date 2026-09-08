#!/usr/bin/env python3
"""FA-12 Empirical Verification Script for R2 Remediation in PCController.

Verifies:
1. Exploit attempt without token -> fails closed with PermissionError.
2. Exploit attempt with forged signature -> fails closed with InvalidTokenSignatureError.
3. Exploit attempt with revoked epoch -> fails closed with PermissionError.
4. Genuine authorized execution with valid token -> executes allowlisted command.
5. Genuine authorized write_file with valid token -> mutates physical disk.
6. Reads and verifies physical runtime data: audit.jsonl records on disk.
"""
import asyncio
import json
import os
import sys
import tempfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

os.environ.setdefault("SCP_CAPABILITY_SECRET", "test-secret-32-chars-long-abcdef012345")

from scp.core.capability_token import InvalidTokenSignatureError
from scp.pc_control.pc_controller import CapabilityLevel, PCController
from scp.security.capability_epoch import CapabilityAuthority, CapabilityToken


async def run_empirical_verification():
    print("[FA-12 EMPIRICAL VERIFICATION START]")
    with tempfile.TemporaryDirectory() as tmp_dir:
        workspace = Path(tmp_dir) / "ws"
        workspace.mkdir(parents=True)
        cap_state = Path(tmp_dir) / "cap_state.json"
        authority = CapabilityAuthority(cap_state)
        controller = PCController(working_dir=workspace, capability_authority=authority)

        # 1. Verify missing token rejection
        print("\n--- 1. Testing Unauthenticated Execution ---")
        try:
            await controller.execute("whoami", capability_token=None)
            raise AssertionError("FAIL: execute allowed without token!")
        except PermissionError as exc:
            print(f"[OK] Blocked fail-closed: {exc}")

        # 2. Verify forged signature rejection
        print("\n--- 2. Testing Forged Signature ---")
        token = authority.issue("pc.execute")
        tampered_token = CapabilityToken(
            subject=token.subject,
            epoch=token.epoch,
            token_id=token.token_id,
            issued_at=token.issued_at,
            signature="deadbeef" * 8,
        )
        try:
            await controller.execute("whoami", capability_token=tampered_token)
            raise AssertionError("FAIL: execute allowed with forged signature!")
        except InvalidTokenSignatureError as exc:
            print(f"[OK] Blocked fail-closed: {exc}")

        # 3. Verify revoked epoch rejection
        print("\n--- 3. Testing Revoked Epoch ---")
        stale_token = authority.issue("pc.execute")
        authority.revoke(reason="compromised")
        try:
            await controller.execute("whoami", capability_token=stale_token)
            raise AssertionError("FAIL: execute allowed with revoked token!")
        except PermissionError as exc:
            print(f"[OK] Blocked fail-closed: {exc}")

        # 4. Restore authority and execute with genuine token
        print("\n--- 4. Testing Genuine Execution ---")
        authority.restore(reason="recovered")
        valid_exec_token = authority.issue("pc.execute")
        res = await controller.execute("whoami", capability_token=valid_exec_token)
        print(f"[OK] Genuine execution success={res.get('success')}, returnCode={res.get('returnCode')}")
        assert res.get("success") is True
        assert res.get("returnCode") == 0

        # 5. Verify authorized file write
        print("\n--- 5. Testing Genuine File Mutation ---")
        valid_write_token = authority.issue("pc.write_file")
        target_file = workspace / "test_empirical.txt"
        content = "FA-12 Verified Physical File Content"
        write_res = await controller.write_file(
            str(target_file),
            content,
            capability_token=valid_write_token,
            capability_level=CapabilityLevel.WORKSPACE,
            approved=True,
        )
        print(f"[OK] Genuine write success={write_res.get('success')}")
        assert target_file.exists()
        assert target_file.read_text(encoding="utf-8") == content

        # 6. Physical Audit Log Inspection (FA-12 step 4)
        print("\n--- 6. Examining Physical Audit Log Ledger ---")
        assert controller.audit_path.exists()
        audit_content = controller.audit_path.read_text(encoding="utf-8")
        audit_records = [json.loads(line) for line in audit_content.splitlines() if line.strip()]
        print(f"Total audit records committed to physical disk: {len(audit_records)}")

        rejected_events = [r for r in audit_records if r.get("event") == "TOKEN_REJECTED"]
        print(f"Rejections recorded: {len(rejected_events)}")
        for r in rejected_events:
            print(f"  - Rejection event: action={r.get('action')}, reason={r.get('reason')}")

        executed_events = [r for r in audit_records if r.get("event") == "EXECUTE"]
        print(f"Authorized executions recorded: {len(executed_events)}")
        for r in executed_events:
            print(f"  - Execution event: cmd={r.get('command')}, returnCode={r.get('returnCode')}, tokenId={r.get('tokenId')}")

        write_events = [r for r in audit_records if r.get("event") == "WRITE_FILE"]
        print(f"Authorized writes recorded: {len(write_events)}")
        for r in write_events:
            print(f"  - Write event: path={r.get('path')}, sha256={r.get('content_sha256')}, tokenId={r.get('tokenId')}")

        assert len(rejected_events) >= 3
        assert len(executed_events) >= 1
        assert len(write_events) >= 1

        print("\n" + "=" * 70)
        print("FA-12 EMPIRICAL VERIFICATION COMPLETE: ALL GATES PASS")
        print("=" * 70)


if __name__ == "__main__":
    asyncio.run(run_empirical_verification())
