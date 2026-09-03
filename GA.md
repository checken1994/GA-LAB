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
work_snapshot_sha: 55346f2958c96b4d8f804523d080a160f5e396fa
snapshot_role: analyzed live main boundary before this GA handoff commit
active_target_revision: 4.0.2
baseline_status: ACTIVE_BASELINE_FOR_BUILD
runtime/release_verdict: NOT_DERIVED / NOT CLAIMED
```

Always refresh `main`; other AIs are actively committing to the same branch.

## B2. Target / coverage authority at snapshot

```text
target_manifest: spec/scp_future_target_manifest.yaml
coverage_binding: spec/scp_target_test_coverage.yaml
coverage_universe: 138 capabilities + 67 edges
explicit_claims: 42
TEST_BOUND_CONTRACT: 3
TEST_BOUND_PARTIAL: 39
UNPROVEN: 163
EVIDENCE_VERIFIED: 0
coverage_proven: false
current coverage verdict: TRACEABILITY_STRUCTURE_ONLY_NOT_COVERAGE_PROOF / TEST_COVERAGE_UNPROVEN
```

`TEST_BOUND_CONTRACT` là semantic test binding, không phải C/D Reality proof và không cho phép suy ra release readiness.

## B3. New commits absorbed since previous monitored snapshot

Từ `a12ca48e22ee9dfbccfbcc28d631bcf5e132800c` đến snapshot này có 2 commit:

```text
1dbee4adb27d487229252afe72a98371e5568772
  feat(S10,X08): implement Risk Intelligence + World-State authorities; 4 contract reds -> green
  - adds scp/risk_intelligence authorities: classifier, evidence bundle, alert router, incident state machine
  - adds scp/world_state authorities: bitemporal temporal authority, entity/event authority, deterministic projection
  - upgrades 6 prior BLOCKED_MISSING_IMPLEMENTATION claims to TEST_BOUND_PARTIAL/B
  - does not claim EVIDENCE_VERIFIED or runtime/release proof

55346f2958c96b4d8f804523d080a160f5e396fa
  coverage semantic review
  - epistemic.evidence -> TEST_BOUND_CONTRACT/B
  - governance.drift_guard -> TEST_BOUND_CONTRACT/B
  - world.temporal_state -> TEST_BOUND_CONTRACT/B
  - remaining claims stay PARTIAL/UNPROVEN; EVIDENCE_VERIFIED remains 0
```

## B4. Semantics / contradiction review

- `AGENTS.md`, SCP DNA, active target manifest and protected invariants were not modified in this two-commit diff; their authority remains unchanged.
- S10 implementation preserves owner-locked fail-closed semantics: social/syndication volume alone cannot manufacture PR4/PR5; high-risk qualification requires official/independent lineage or owned-sensor exception; unconfigured alert routing emits bundle only; forbidden public-broadcast operations remain denied.
- X08 implementation preserves bitemporal/append-only semantics and prevents predictor self-promotion from PREDICTED to OBSERVED.
- The six formerly blocked S10/X08 claims are only `TEST_BOUND_PARTIAL/B`; implementation existence + green contract nodes does not imply Reality verification.
- The three `TEST_BOUND_CONTRACT/B` promotions are stronger traceability claims only. `world.temporal_state` covers the temporal subset of CE-X08-01; `same_name_entity_merge` belongs to the entity-identity side of the same edge and remains separately bound. Do not reinterpret this as whole-edge C proof.
- No skip/xfail/test weakening, protected-invariant relaxation, or target revision change was observed in these commits.

## B5. Exact-SHA CI at snapshot

For SHA `55346f2958c96b4d8f804523d080a160f5e396fa`, GitHub created 7 check runs.

Observed at refresh:

```text
p0-baseline: FAILURE
platform-gates ubuntu: QUEUED
platform-gates windows: QUEUED
main-lineage-authority: QUEUED
security-mutation-durability: QUEUED
other same-SHA checks: not yet concluded
same-SHA CI PASS: NOT ESTABLISHED
release claim: FORBIDDEN
```

The failed `p0-baseline` job completed before test steps were exposed through the connector; its decoded log was unavailable, so root-cause classification is not yet established. Treat it as a real exact-SHA blocker, not as product failure until evidence identifies the failure class.

## B6. Current dependency cone

Do not revert concurrent S10/X08 work. Refresh `main` again before coding.

```text
1. Diagnose exact-SHA p0-baseline failure
   - classify HARNESS/INFRA vs PRODUCT from job evidence when available
   - fix at the actual failure point; never weaken tests

2. S10 Risk Intelligence integration depth
   - prove containment crosses CapabilityAuthority rather than direct Tool authority
   - verify approval/pre-authorization boundaries and evidence lineage under integration/reality tests

3. X08 World State integration depth
   - test entity identity + same-name non-merge together with temporal history
   - exercise persistence/restart/rebuild and independent resolver path

4. Continue open P0 isolation/readiness capabilities still UNPROVEN
   - sandbox/process-tree cleanup semantics
   - browser session isolation
   - service lifecycle readiness
```

For each capability: Detect -> Why -> Fix product/harness at failure point -> Verify -> update traceability/evidence honestly -> sync to `main`.

## B7. Completion language

Allowed now:

> S10 Risk Intelligence and X08 World-State authorities are implemented and contract-bound on main at B-level traceability; three reviewed capabilities are TEST_BOUND_CONTRACT, while exact-SHA CI is not green and EVIDENCE_VERIFIED remains zero.

Forbidden now:

> S10/X08 Reality-verified, SCP complete, P0 verified, CI green, or release ready.
