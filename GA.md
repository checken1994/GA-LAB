# GA — SCP Session Authority + Current Handoff

> Bootstrap duy nhất cho phiên SCP. Câu gọi chuẩn: **“Đọc GA trên main, refresh GitHub live rồi tiếp tục SCP.”**
>
> Chat/memory chỉ hỗ trợ continuity. Repo + Reality evidence trên đúng SHA là source of truth.

---

# A. SESSION RULES

## A1. Authority order

Khi mâu thuẫn, ưu tiên:

1. Chỉ thị trực tiếp mới nhất của người dùng.
2. `AGENTS.md`.
3. `.agents/skills/scp-dna/SKILL.md` + DNA principles.
4. `spec/complete_scp_reference.yaml` + `spec/protected_invariants.yaml`.
5. Skill chuyên biệt phù hợp task.
6. `spec/scp_future_target_manifest.yaml` + effective target spec mà manifest compose.
7. Implementation/test/release bindings machine-readable.
8. Live Git + runtime/test/evidence trên đúng SHA.
9. CURRENT HANDOFF này.
10. Chat/model memory.

Target requirement không biến mất vì implementation thiếu; target spec cũng không phải runtime proof. **Reality > Model.**

## A2. Effective SCP Future Target

Không đọc `spec/scp_future_cause_effect_matrix.yaml` riêng lẻ như baseline hiện hành.

```text
spec/scp_future_target_manifest.yaml
  -> base: spec/scp_future_cause_effect_matrix.yaml @ 4.0.1
  -> overlay: spec/scp_future_cause_effect_matrix_v4_0_2.overlay.json
  -> effective SCP Future Target Architecture 4.0.2
```

Baseline effective theo live manifest:

```text
12 core systems
8 cross-cutting systems
5 phases P0-P4
12 gates T00-T11
138 capabilities
67 cause-effect edges
34 global invariants
13 normative SCP Skills
```

Target 4.0.2 là baseline BUILD, không phải bằng chứng SCP runtime đã hoàn thiện. Tên commit có thể mang nhãn `4.0.3`; authority revision hiện hành vẫn là giá trị machine-readable trong manifest/T00.

## A3. Bootstrap cho substantial SCP task

1. Đọc `GA.md` live trên `main`.
2. Đọc `AGENTS.md`.
3. Đọc SCP DNA Skill/principles.
4. Đọc Complete Reference + protected invariants khi liên quan authority/evidence/governance.
5. Nếu liên quan architecture/coverage, compose target theo manifest hiện hành.
6. Đọc Skill chuyên biệt đúng dependency cone; không nạp cả Skill pack nếu không cần.
7. Refresh live `main` ngay trước analysis quan trọng và ngay trước mutation.
8. Nếu HEAD khác `work_snapshot_sha`, đọc commit/diff chen ngang trước khi kế thừa.
9. Test/evidence claim phải gắn đúng scope/SHA.

## A4. Engineering invariants

```text
Reality > Model
PASS != TRUE
UNKNOWN != VERIFIED
Consensus != Truth
independent lineage required
fail-closed khi thiếu authority/evidence quan trọng
same-SHA evidence cho mandatory verification/release claim
không delete/skip/xfail hoặc hạ assertion/security/mutation/acceptance threshold để manufacture green
không đổi fail-closed thành fail-open để pass
không blind-retry uncertain external side effect; reconcile first
small + reversible + observable changes
max_cost_usd=0; unknown/stale price=DENY; paid_fallback=false
External Data -> Evidence -> Epistemic Assessment -> Knowledge
Knowledge/Reasoning/Risk -> Proposal -> Governance -> Execution
sandbox/browser/workspace/process state phải task-scoped; không reuse state bẩn/cross-task
open port/stale log != service readiness
latency optimization không được bỏ policy/capability/revocation/egress/verifier/recovery/high-risk approval
gateway failover không được hạ privacy/zero-cost/epistemic/retry safety
Skill count/index tự khai chỉ là giả thuyết; recount khi pack đổi
stale lease/worker không được commit task/idempotency state
recovery authority không được vô tình cấp lại quyền cho stale worker
RiskAuthority không được gọi Tool trực tiếp; containment phải qua CapabilityAuthority
prediction/forecast không được tự ghi thành OBSERVED
Golden task/test không được khai như production subsystem implementation
```

## A5. Test/evidence semantics

Traceability đích:

```text
target capability/edge
  -> T00-T11 gate
  -> concrete test
  -> required evidence A/B/C/D
  -> same-SHA evidence khi mandatory
```

`spec/scp_target_test_coverage.yaml` chỉ lưu explicit claims. Effective universe hiện là **138 capabilities + 67 edges**; target chưa bind phải hiện `UNPROVEN`, không được bỏ khỏi report.

Test tồn tại không tự thành Reality proof. `TEST_BOUND_PARTIAL`/`TEST_BOUND_CONTRACT` khác `EVIDENCE_VERIFIED`. `BLOCKED_MISSING_IMPLEMENTATION` biểu thị target bắt buộc nhưng product chưa có implementation; claim dạng này hợp lệ khi không có `concrete_tests`. `EVIDENCE_VERIFIED` cần scope + evidence level + snapshot SHA + evidence refs đúng contract.

Failure classes dùng thống nhất:

```text
HARNESS_BROKEN
PRODUCT_BLOCKED
PRODUCT_FAIL
STRUCTURAL_COVERAGE_GAP
TEST_COVERAGE_UNPROVEN
BLOCKED
```

## A6. Bounded verification / chống audit vô hạn

Target architecture hiện hành đã freeze làm baseline BUILD. Không mở lại chỉ để audit thêm hoặc tạo validator của validator.

Chỉ reopen khi có trigger thật:
- user đổi architecture requirement;
- DNA/normative Skill đổi;
- Reality phát hiện missing piece/contradiction;
- implementation chứng minh target contract không dung hòa;
- security/recovery evidence phủ định assumption kiến trúc.

Một verification round có finite scope + budget + exit condition. Hết budget/evidence => UNKNOWN/BLOCKED, không forced PASS và không loop vô hạn.

## A7. Main synchronization

Chính sách hiện tại: **đồng bộ relevant Reality-checked work lên `main` để AI khác kiểm tra cùng trạng thái**.

`main` là coordination source, không tự động là release proof. Trước write luôn refresh live HEAD; nếu AI khác đã commit thì reconcile/fast-forward, không overwrite concurrent work.

Một SHA chỉ DONE khi toàn bộ mandatory gate PASS trên chính SHA đó và blocker=0. Release/customer handoff còn cần full-system verification mới trên resulting `main` SHA.

---

# B. CURRENT HANDOFF

## B1. Snapshot

```text
project: SCP / GA-LAB
repository: checken1994/GA-LAB
active_sync_branch: main
work_snapshot_sha: bba8e60808530471ab15184df6eeab8688105188
snapshot_role: analyzed live main boundary before this GA handoff commit
active_target_revision: 4.0.2
baseline_status: ACTIVE_BASELINE_FOR_BUILD
runtime/release_verdict: NOT_DERIVED / NOT CLAIMED
```

Always refresh `main`; other AIs are actively committing to the same branch.

## B2. Target / coverage authority at snapshot

```text
target_manifest: spec/scp_future_target_manifest.yaml
target_validator: tools/verify_scp_future_target.py
target_T00_guard: tests/T00_integrity/test_scp_future_target.py
coverage_binding: spec/scp_target_test_coverage.yaml
coverage_validator: tools/verify_scp_target_test_coverage.py
coverage_T00_guard: tests/T00_integrity/test_scp_target_test_coverage.py
coverage_universe: 138 capabilities + 67 edges
explicit_claims: 42
TEST_BOUND_PARTIAL: 36
BLOCKED_MISSING_IMPLEMENTATION: 6
UNPROVEN: 163
EVIDENCE_VERIFIED: 0
coverage_proven: false
current coverage verdict: TRACEABILITY_STRUCTURE_ONLY_NOT_COVERAGE_PROOF / TEST_COVERAGE_UNPROVEN
```

Các con số claim/status trên là trạng thái traceability sau commit `a30386f8...`; không được nâng thành runtime/release proof.

## B3. New commits absorbed since previous monitored snapshot

Từ `0bbfd20335c7b3f6363f8dce6f19069bd7863168` đến snapshot này có 4 commit, đều được giữ nguyên:

```text
46758444c442dd5d0f4e953f4eb74f24d93f6acc
  coverage: bind execution.recovery_reconciliation + world.source_registry
  -> TEST_BOUND_PARTIAL/B; semantic review vẫn pending, không phải CONTRACT/VERIFIED.

a30386f8b94db0a22451409824fd2cec78686179
  tests/product: S04 firewall contract + firewall hardening; add RED contracts for S10 Risk Intelligence and X08 World State
  -> S04 adds deterministic injection/secret quarantine coverage.
  -> risk.assessment, risk.local_containment, risk.external_alert, risk.early_warning,
     world.temporal_state, world.event_model = BLOCKED_MISSING_IMPLEMENTATION.
  -> Golden C was added to complete reference, but was initially also (incorrectly) listed as an implementation binding.

64b40d703fca9a851f95e264e97a84d13536b688
  harness/product follow-up: reverse mapping tolerates BLOCKED claims with no concrete_tests;
  adds `/dev/(tcp|udp)/` scanner pattern.
  -> harness strictness is preserved for every claim that actually has concrete tests.

bba8e60808530471ab15184df6eeab8688105188
  binding correction: removes Golden C test from `implementation_bindings.yaml`.
  -> correct separation restored: golden task is acceptance/reference evidence, not a production subsystem implementation.
```

## B4. Semantics / contradiction review

- Live manifest remains `effective_revision: 4.0.2` with 138 capabilities / 67 edges / 34 invariants / 13 Skills. Commit labels containing `4.0.3` do **not** override machine authority.
- `a30386f8...` increased security strictness rather than weakening it; no skip/xfail/assertion relaxation was observed in the four-commit diff.
- S10/X08 tests are intentionally RED because product authorities do not exist. This is a product blocker, not a reason to weaken/remove the tests.
- `64b40d7...` changes T00 reverse mapping only for claims that legitimately have no `concrete_tests`; it still validates all selectors on claims that do have tests. Treat as harness compatibility, not coverage promotion.
- `bba8e60...` fixes the important modeling error introduced in `a30386f8...`: tests/golden tasks are not implementation modules.
- No new claim in this commit set is allowed to imply `EVIDENCE_VERIFIED`, full SCP completeness, release readiness, or same-SHA runtime green.

## B5. Exact-SHA CI at snapshot

For SHA `bba8e60808530471ab15184df6eeab8688105188`, GitHub created 7 check runs. At last refresh they were queued, including platform gates, security-mutation-durability, main-lineage-authority and pre-RC verification.

```text
same-SHA CI PASS: NOT OBSERVED
same-SHA CI FAIL: NOT OBSERVED
current CI classification: BLOCKED / QUEUED INFRASTRUCTURE
release claim: FORBIDDEN
```

Do not reuse historical green status for this SHA.

## B6. Current dependency cone

Do not revert concurrent work. Before coding, refresh `main` again.

Immediate blocker-driven order from the newest contract tests:

```text
1. S10 Risk Intelligence
   - RiskClassifier PR0-PR5 from independent evidence; volume alone never decides high risk
   - containment through CapabilityAuthority only; RiskAuthority -> Tool forbidden
   - Emergency Evidence Bundle + REPORT_ONLY/approval-gated AlertRouter
   - incident state machine + false-positive/missing-source handling

2. X08 World State / Temporal Model
   - bitemporal valid_time/system_time
   - append-only reconstructable history
   - corrections supersede; never rewrite history
   - PREDICTED cannot be written/promoted to OBSERVED by the originating predictor

3. Continue previously open P0 isolation/readiness cone where still UNPROVEN
   - execution.sandbox_isolation full task-scoped/process-tree/cleanup semantics
   - execution.browser_session_isolation
   - execution.service_lifecycle_readiness
```

For each capability: Detect -> Why -> Fix product/harness at failure point -> Verify -> update traceability/evidence honestly -> sync to `main`.

## B7. Completion language

Allowed now:

> Main contains additional S04 firewall hardening and explicit S10/X08 product-blocking contracts; coverage traceability is broader but remains unproven, with no EVIDENCE_VERIFIED claim.

Forbidden now:

> S10/X08 implemented, SCP complete, P0/P2 verified, CI green, or release ready.
