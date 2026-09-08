# Scope: Remediation of R2, R3, R6 Critical Vulnerabilities

## Architecture
- **Capability Enforcement Subsystem (R2 - `PCController`, `HandsExecutor`, `pc_controller_routes.py`)**:
  - `PCController` acts as a Policy Enforcement Point (PEP) immediately in front of OS execution and file mutation drivers.
  - Requires valid, cryptographically signed `CapabilityToken` (HMAC-SHA256) issued by `CapabilityAuthority`.
  - Fail-closed: missing, expired, epoch-mismatched, or forged token raises `InvalidTokenSignatureError` / `PermissionError` and blocks execution before `_run_sync` or disk write.
  - `HandsExecutor` and `pc_controller_routes.py` propagate the `CapabilityToken` end-to-end to prevent execution bypass.
- **Provenance Verification Subsystem (R3 - `scp/core/verifier_receipt.py`, `TaskKernel`, Bridges)**:
  - Cryptographic `VerifierReceipt` signed with HMAC-SHA256 using `SCP_VERIFIER_SECRET` (fallback `SCP_CAPABILITY_SECRET`).
  - Canonical byte serialization prevents parameter tampering (task_id, verifier_id, verdict, evidence_ref, timestamp).
  - `TaskKernel.commit_verification_result()` and `commit_completed()` strictly enforce receipt signature verification before transitioning state to `COMPLETED`.
  - State machine fix: remove `RUNNING -> COMPLETED` backdoor (require `VERIFYING -> COMPLETED`).
  - SQLite event journal logs authentic `verifier_id` and receipt signature hash.
- **Cognitive Loop Perfect Isolation (R6 - `ShadowSnapshotManager`, `AutofixMixin`, `VerifyMixin`)**:
  - `ShadowSnapshotManager` at `scp/autofix/shadow_snapshot.py` manages filesystem-level transactions under `data/shadow/active/<tx_id>/`.
  - Pre-patch file snapshots with SHA256 hashes and metadata manifests are committed to disk before any mutation.
  - Elimination of volatile RAM-only backups (`ctx.pre_fix_content`) and ad-hoc in-tree backups (`.tier3bak`).
  - Strict Reality Test gate: pytest execution against target test suites, fail-closed on non-zero exit code or error.
  - Automatic rollback on test failure or syntax error; crash recovery on engine startup via `recover_abandoned_transactions()`.

## Feature Inventory
| # | Feature | Description | Milestone | Source |
|---|---------|-------------|-----------|--------|
| 1 | R2 PCController Token Enforcement | Add `CapabilityAuthority` verification to `PCController.execute()`, `write_file()`, `read_file()`, `rollback()`, `clear_kill_switch()` | M1 | Survey / ORIGINAL_REQUEST §R2 |
| 2 | R2 HandsExecutor Token Forwarding | Ensure `HandsExecutor` passes capability token to `PCController` across all execution channels | M1 | Survey / ORIGINAL_REQUEST §R2 |
| 3 | R2 Route Security Hardening | Update `pc_controller_routes.py` to validate capability tokens instead of static secret bypass | M1 | Survey / ORIGINAL_REQUEST §R2 |
| 4 | R2 Unit & Regression Tests | Add tests in `tests/T03_capability/test_pc_controller_token_pep.py` proving fail-closed token boundary | M1 | Survey / ORIGINAL_REQUEST §R2 |
| 5 | R3 VerifierReceipt Module | Implement `VerifierReceipt`, `canonical_receipt_bytes`, `sign_verifier_receipt`, `verify_verifier_receipt` in `scp/core/verifier_receipt.py` | M2 | Survey / ORIGINAL_REQUEST §R3 |
| 6 | R3 TaskKernel Receipt Verification | Enforce cryptographic signature verification in `TaskKernel.commit_verification_result()` and `commit_completed()` | M2 | Survey / ORIGINAL_REQUEST §R3 |
| 7 | R3 State Machine & Journal Fix | Require `VERIFYING` state before `COMPLETED` (close GAP-P1), log authentic verifier provenance in journal | M2 | Survey / ORIGINAL_REQUEST §R3 |
| 8 | R3 Bridge & Adapter Updates | Update `TaskKernelHandsBridge` and `AskKernelAdapter` to produce signed receipts | M2 | Survey / ORIGINAL_REQUEST §R3 |
| 9 | R3 Unit & Regression Tests | Add comprehensive tests in `tests/T04_kernel/test_verifier_receipt_provenance.py` covering valid/tampered/unsigned receipts | M2 | Survey / ORIGINAL_REQUEST §R3 |
| 10 | R6 ShadowSnapshotManager | Implement durable transaction manager at `scp/autofix/shadow_snapshot.py` storing backups in `data/shadow/` | M3 | Survey / ORIGINAL_REQUEST §R6 |
| 11 | R6 AutoFix Integration | Refactor `autofix_mixin.py` and `code_evolution_agent.py` to use `ShadowSnapshotManager`; eliminate RAM backups and `.tier3bak` | M3 | Survey / ORIGINAL_REQUEST §R6 |
| 12 | R6 Fail-Closed Pytest Gate | Update `verify_mixin.py` to enable pytest gate by default, target test suites, and fail-closed on errors | M3 | Survey / ORIGINAL_REQUEST §R6 |
| 13 | R6 Reality Test Auto-Rollback | Update `engine.py` `_auto_approve_tier3` to rollback if reality test is not PASS | M3 | Survey / ORIGINAL_REQUEST §R6 |
| 14 | R6 Crash Recovery | Implement `recover_abandoned_transactions()` on engine startup for crash resilience | M3 | Survey / ORIGINAL_REQUEST §R6 |
| 15 | R6 Unit & Regression Tests | Add tests in `tests/T07_learning/test_autofix_shadow_rollback.py` verifying snapshot, rollback, and crash recovery | M3 | Survey / ORIGINAL_REQUEST §R6 |
| 16 | Final Adversarial Hardening & Audit | Run Challengers for empirical boundary testing, Forensic Auditor for FA-01 to FA-13 integrity check, full test suite pass | M4 | ORIGINAL_REQUEST §4 |

## Milestones
| # | Name | Scope | Dependencies | Status |
|---|------|-------|-------------|--------|
| 1 | M1: R2 Execution Bypass Remediation | Enforce HMAC-SHA256 capability tokens in `PCController`, `HandsExecutor`, and API routes; fail-closed | none | PLANNED |
| 2 | M2: R3 Provenance Forgery Remediation | Implement `VerifierReceipt` HMAC signing & verify in `TaskKernel` before `COMPLETED`; fix state machine | none | PLANNED |
| 3 | M3: R6 AutoFix Rollback Remediation | Implement `ShadowSnapshotManager` (`data/shadow/`), fail-closed pytest gate, automatic rollback | none | PLANNED |
| 4 | M4: Adversarial Hardening & Final Gate | Run Challengers (R2/R3/R6), Forensic Auditor (Zero-Trust/Anti-Placebo), full pytest suite, final synthesis report | M1, M2, M3 | PLANNED |

## Interface Contracts
### R2: Capability Token Boundary (`scp/pc_control/pc_controller.py`)
- `PCController(..., capability_authority: CapabilityAuthority | None = None)`
- `execute(command: str, capability_token: CapabilityToken | str | None = None, capability_level: int = 0, approved: bool = False, timeout: int = 120)`
  - If token is missing, expired, tampered, or invalid: raises `InvalidTokenSignatureError` (subclass of `PermissionError`).
- `write_file(path: str, content: str, capability_token: CapabilityToken | str | None = None, ...)`
  - Enforces token verification before disk write.
- `read_file(path: str, capability_token: CapabilityToken | str | None = None, ...)`
- `rollback(backup_id: str, capability_token: CapabilityToken | str | None = None, ...)`
- `clear_kill_switch(capability_token: CapabilityToken | str | None = None, approved: bool = False)`

### R3: Verifier Receipt Contract (`scp/core/verifier_receipt.py`)
- `VerifierReceipt(task_id: str, verifier_id: str, verdict: str, evidence_ref: str, issued_at: float, signature: str = "")`
- `canonical_receipt_bytes(receipt: VerifierReceipt) -> bytes`:
  - `f"{receipt.task_id}:{receipt.verifier_id}:{receipt.verdict}:{receipt.evidence_ref}:{receipt.issued_at:.6f}".encode("utf-8")`
- `sign_verifier_receipt(receipt: VerifierReceipt, secret: str | None = None) -> VerifierReceipt`
- `verify_verifier_receipt(receipt: VerifierReceipt | dict, secret: str | None = None) -> bool`:
  - Uses `hmac.compare_digest`. Raises `InvalidReceiptSignatureError` if invalid/forged/unsigned.
- `TaskKernel.commit_verification_result(task_id: str, lease_id: str, verification_result: VerifierReceipt | dict) -> dict[str, Any]`
  - Validates `verify_verifier_receipt`. Requires state == `VERIFYING`.

### R6: Shadow Snapshot Contract (`scp/autofix/shadow_snapshot.py`)
- `ShadowSnapshotManager(shadow_dir: Path | str = "data/shadow")`
- `begin(target_files: list[Path | str], bug_id: str = "") -> str`:
  - Creates `data/shadow/active/<tx_id>/` containing file copies and `manifest.json`. Returns `tx_id`.
- `rollback(tx_id: str, reason: str = "") -> bool`:
  - Atomically restores all files from `data/shadow/active/<tx_id>/` via temp file + `os.replace`.
  - Moves tx directory to `data/shadow/rolled_back/<tx_id>/`.
- `commit(tx_id: str) -> bool`:
  - Moves `data/shadow/active/<tx_id>/` to `data/shadow/completed/<tx_id>/`.
- `recover_abandoned_transactions() -> list[str]`:
  - Scans `data/shadow/active/` at startup and rolls back any leftover transactions from prior crashes.

## Code Layout
- `scp/pc_control/pc_controller.py`: `PCController` token PEP. Owned by M1 Worker.
- `scp/hands/hands_executor.py`: `HandsExecutor` token forwarding. Owned by M1 Worker.
- `scp/api/routes/pc_controller_routes.py`: API route token check. Owned by M1 Worker.
- `tests/T03_capability/test_pc_controller_token_pep.py`: Unit and regression tests for R2. Owned by M1 Worker.
- `scp/core/verifier_receipt.py`: `VerifierReceipt` definition and HMAC functions. Owned by M2 Worker.
- `scp/task_kernel_parts/taskkernel.py`: `TaskKernel` verification enforcement. Owned by M2 Worker.
- `scp/hands/task_kernel_bridge.py`: Signed receipt generation. Owned by M2 Worker.
- `scp/ask_kernel_adapter.py`: Signed receipt generation. Owned by M2 Worker.
- `tests/T04_kernel/test_verifier_receipt_provenance.py`: Unit and regression tests for R3. Owned by M2 Worker.
- `scp/autofix/shadow_snapshot.py`: `ShadowSnapshotManager`. Owned by M3 Worker.
- `scp/autofix/engine_parts/autofix_mixin.py`: Transactional patch application. Owned by M3 Worker.
- `scp/autofix/engine_parts/verify_mixin.py`: Fail-closed pytest gate. Owned by M3 Worker.
- `scp/autofix/engine.py`: Reality test rollback. Owned by M3 Worker.
- `tests/T07_learning/test_autofix_shadow_rollback.py`: Unit and regression tests for R6. Owned by M3 Worker.
