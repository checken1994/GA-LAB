# Delta Audit Handoff Report: HandsExecutor & Capability Authority

## 1. Observation
- Target: `scp/hands/hands_executor.py` and adjacent components in `scp/security/capability_epoch.py`, `scp/hands/task_kernel_bridge.py`, `scp/api/routes/hands_routes.py`, `scp/hands/planner.py`.
- Static AST inspection and execution tracing revealed that `HandsExecutor.execute` (line 111) and `HandsExecutor.rollback` (line 326) execute:
  `capability_token = capability_token or self.capability_authority.issue(f"hands:{action}")`
- When callers omit `capability_token`, the executor mints its own token and validates it immediately, bypassing Zero-Trust policy enforcement.
- Upstream callers (`hands_routes.py`, `task_kernel_bridge.py`, `planner.py`) drop or omit capability tokens entirely.
- `CapabilityAuthority.validate` checks only epoch integer and revocation status, ignoring `token.subject`.
- Live adversarial probe execution (`tools/probes/probe_hands_authority_flaws.py`) deterministically reproduced the vulnerability (writing files to disk without caller tokens and accepting read-only tokens for write actions).
- Anti-Placebo testing proved that baseline code fails invariant checks (RED), whereas invariant-preserving PEP guards pass (GREEN).
- Forensic auditor confirmed that ZERO production code files under `scp/` were modified (`git diff` clean).

## 2. Logic Chain
- A Policy Enforcement Point (PEP) must never be its own Policy Decision Point (PDP) or Authority Issuer (Rule FA-05).
- In the current implementation, `HandsExecutor` is colocated with `self.capability_authority`.
- If the executor issues tokens for itself when none are provided, the PEP check `_check_capability` is tautological and always succeeds.
- This creates an illusion of security (`PASS != TRUE` per DNA #22) where tests pass because the system operates on self-granted authority.
- The 5 phases of SCP Delta Audit were executed to model the target invariants (Phase 1), map the exact call graph (Phase 2), identify the causal gaps (Phase 3), design and execute an anti-placebo empirical probe (Phase 4), and define the architectural evolution path (Phase 5).

## 3. Caveats
- Production code in `scp/` was deliberately not modified during this audit phase, in strict compliance with the audit mandate.
- Modifying `HandsExecutor` to strictly fail-closed on missing tokens without updating `TaskKernelHandsBridge` and `hands_routes.py` will break existing tests and API callers until the complete Evolution Path is applied.
- Token unification between `scp/core/capability_token.py` (HMAC JWT) and `scp/security/capability_epoch.py` (epoch JSON) remains an open architectural decision for the implementation phase.

## 4. Conclusion
- The suspected vulnerability ("Tử huyệt bạo chúa" / FA-05 breach) is **CONFIRMED PROVEN**.
- The entire SCP platform's tool execution currently relies on self-granting authority.
- The 10-section Delta Audit Report has been compiled at `c:\Users\check\Downloads\scp\.agents\orchestrator_4\DELTA_AUDIT_HANDS_EXECUTOR.md`.
- All acceptance criteria from `ORIGINAL_REQUEST.md` have been met with authentic empirical evidence.

## 5. Verification Method
- Probe Script: `tools/probes/probe_hands_authority_flaws.py`
- Terminal Execution Command: `python tools/probes/probe_hands_authority_flaws.py`
- Forensic Audit Verdict: `CLEAN` (verified by `teamwork_preview_auditor` in `c:\Users\check\Downloads\scp\.agents\auditor_forensic_1\audit_report.md`).
- Meta-Audit Command: `python tools/t00_meta_audit.py` (Exit code 0).
