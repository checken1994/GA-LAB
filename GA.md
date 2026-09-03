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
work_snapshot_sha: ff291fbc4d1a27da16821eb37564327a85111725
snapshot_role: independently audited product/test boundary before this GA handoff commit
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
explicit_claims: 47
TEST_BOUND_CONTRACT: 6
TEST_BOUND_PARTIAL: 41
UNPROVEN: 158
EVIDENCE_VERIFIED: 0
coverage_proven: false
current coverage verdict: TRACEABILITY_STRUCTURE_ONLY_NOT_COVERAGE_PROOF / TEST_COVERAGE_UNPROVEN
```

`TEST_BOUND_CONTRACT` là semantic test binding, không phải C/D Reality proof và không cho phép suy ra release readiness.

## B3. New commits absorbed since previous monitored snapshot

```text
74a78cf45f0879b27bb145c65f239492c24426cd
  feat(test,coverage): expand S10/X08 contract tests and bind 5 new claims
  - raised world.entity_identity, world.state_projection, risk.local_containment to TEST_BOUND_CONTRACT/B
  - bound world.change_detection + CE-X08-01 + CE-S10-03 + CE-S10-04 at PARTIAL/B

8ca6403cfe603656cf720048cbb97a23db2ef486
  docs: refresh GA after S10/X08 integration coverage commit
  - handoff rebound to 74a78cf; release remained forbidden

ac034d1..ff291fb (independent audit remediation chain)
  - X08 correction writes now require evidence_refs
  - identity links now require evidence_refs + actor provenance
  - identity resolution computes transitive evidence-backed closure and ignores legacy unaudited links
  - WorldStateProjection historical as_of reconstruction now evaluates supersession relative to cutoff time
  - WorldStateProjection exposes real append-only change detection instead of inferring a delta claim from current()
  - S10 adds production ContainmentCoordinator: owned-scope only, effect crosses CapabilityAuthority revocation, no direct Tool call
  - T02 adds regression proof for as_of-before-correction, evidenced/transitive identity and real changes()
  - T03 containment selector now calls the production ContainmentCoordinator rather than performing revocation only inside the test harness
```

## B4. Independent semantic audit / contradiction repair

Independent review found four material weaknesses in `74a78cf` semantics and repaired them at the product/test failure point instead of weakening coverage:

1. `world.entity_identity`: prior semantic note said explicit evidenced link, while production `link_identity` accepted no evidence and direct-neighbor resolution was not transitive. Fixed by requiring evidence refs + actor provenance and computing transitive closure over evidence-backed links.
2. `world.state_projection`: current-state restart parity was green, but historical `as_of_system_time` could hide an assertion because its later `superseded_by` value was read from present state. Fixed by comparing the superseder's system_time with the requested cutoff; regression test proves pre-correction history remains visible.
3. `risk.local_containment`: prior test created/revoked CapabilityAuthority directly in test code, so it did not prove a production Risk -> CapabilityAuthority path. Fixed with `ContainmentCoordinator`, which fails closed outside owned scope and performs containment only through CapabilityAuthority revocation.
4. `world.change_detection`: prior selector only proved two observations coexist and `current()` chooses the latest. Fixed with production `changes()` and a selector that asserts the actual delta while confirming history remains append-only.

No test was deleted/skipped/xfail'ed and no protected assertion/security threshold was relaxed. Coverage statuses remain 6 CONTRACT / 41 PARTIAL because the product and bound selectors were strengthened to satisfy the existing B-level semantic claims rather than downgrading bookkeeping.

## B5. Exact-SHA CI at snapshot

For code/test snapshot SHA `ff291fbc4d1a27da16821eb37564327a85111725`:

```text
GitHub combined status records observed: none
same-SHA CI PASS: NOT ESTABLISHED
EVIDENCE_VERIFIED: 0
release claim: FORBIDDEN
```

Absence of a GitHub status is UNKNOWN, never PASS. The changes above have been synchronized to `main` for independent checking, but must not be promoted to Runtime/Reality verification until mandatory gates execute on the same code/test SHA (or a later rebased SHA containing the same fixes) and blocker=0.

## B6. Current dependency cone

```text
1. Verify remediation on exact SHA
   - T00 integrity / target coverage validator
   - T02 World-State contract tests including as_of/evidence/transitivity/change delta
   - T03 Risk Intelligence contract tests including production containment bridge
   - migration/restart compatibility for 0002_identity_link_evidence

2. Run mandatory same-SHA CI/gates
   - classify every failure HARNESS/INFRA vs PRODUCT from evidence
   - repair at actual failure point; never weaken tests

3. Close edge-level integration evidence
   - CE-X08-01: T06/T09/T10 path beyond T02 B-level contract
   - CE-S10-03: T09 E2E containment path through governance/capability authority
   - CE-S10-04: T09/T11 approval + alert routing + evidence lineage

4. Continue remaining UNPROVEN target rows according to dependency cone
```

For each capability: Detect -> Why -> Fix product/harness at failure point -> Verify -> update traceability/evidence honestly -> sync to `main`.

## B7. Completion language

Allowed now:

> Independent audit defects in the S10/X08 B-level contract implementation were repaired on snapshot `ff291fbc...` and synchronized to main; traceability remains 47 explicit claims (6 CONTRACT/B, 41 PARTIAL/B, 158 UNPROVEN), EVIDENCE_VERIFIED remains 0, and same-SHA CI is not established.

Forbidden now:

> S10/X08 Reality-verified, SCP complete, P0 verified, CI green, or release ready.
