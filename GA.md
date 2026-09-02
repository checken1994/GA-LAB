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

Baseline effective:

```text
12 core systems
8 cross-cutting systems
5 phases P0-P4
12 gates T00-T11
138 capabilities
60 cause-effect edges
34 global invariants
13 normative SCP Skills
```

Target 4.0.2 là baseline BUILD, không phải bằng chứng SCP runtime đã hoàn thiện.

## A3. Bootstrap cho substantial SCP task

1. Đọc `GA.md` live trên `main`.
2. Đọc `AGENTS.md`.
3. Đọc SCP DNA Skill/principles.
4. Đọc Complete Reference + protected invariants khi liên quan authority/evidence/governance.
5. Nếu liên quan architecture/coverage, compose target 4.0.2 theo manifest.
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

`spec/scp_target_test_coverage.yaml` chỉ lưu reviewed concrete-test claims. Effective universe 138 capability + 60 edge được derive từ target 4.0.2; target chưa bind phải hiện `UNPROVEN`, không được bỏ khỏi report.

Test tồn tại không tự thành Reality proof. `TEST_BOUND_PARTIAL`/`TEST_BOUND_CONTRACT` khác `EVIDENCE_VERIFIED`. `EVIDENCE_VERIFIED` cần scope + evidence level + snapshot SHA + evidence refs đúng contract.

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

Target architecture 4.0.2 đã freeze làm baseline BUILD. Không mở lại chỉ để audit thêm hoặc tạo validator của validator.

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
workstream: SCP Future Target 4.0.2 -> P0 Execution OS implementation
work_snapshot_sha: 1096e5255049ca381d0994ac68535294facb6ed0
snapshot_role: product/test/coverage boundary before this GA handoff commit
baseline_status: ACTIVE_BASELINE_FOR_BUILD
runtime/release_verdict: NOT_DERIVED / NOT CLAIMED
```

Always refresh `main`; other AIs are actively committing to the same branch.

## B2. Target / machine guards

```text
target_manifest: spec/scp_future_target_manifest.yaml
target_validator: tools/verify_scp_future_target.py
target_T00_guard: tests/T00_integrity/test_scp_future_target.py
coverage_binding: spec/scp_target_test_coverage.yaml
coverage_validator: tools/verify_scp_target_test_coverage.py
coverage_T00_guard: tests/T00_integrity/test_scp_target_test_coverage.py
coverage_universe: 138 capabilities + 60 edges
coverage_proven: false
EVIDENCE_VERIFIED: 0
current test coverage verdict: TEST_COVERAGE_UNPROVEN / INCOMPLETE
```

Coverage remains non-duplicative: target inventory comes from composed 4.0.2; the coverage file records only reviewed concrete bindings.

## B3. P0 Execution OS — lease/idempotency root cause CLOSED AT CODE+TEST-BINDING LEVEL

Root cause found:

```text
TaskKernel already fenced checkpoint/dispatch/final commit,
but idempotency_claim/idempotency_complete originally lacked lease authority.
Then a second hole remained: a worker whose lease expired while an external driver ran
could call transition() before the watchdog swept the lease, mutating task projection/journal.
```

Fixes now on main ancestry:

```text
de067c5c414dfa2e4f58e55e2ad025ae53d40f17  fix: fence TaskKernel idempotency writes by active lease
8a164eddaa3daf368291ca7f95bce10f83051b92  test: prove stale lease cannot mutate idempotency ledger
f32c5248996c4a14ba4e66e096b903412ee0fc0c  fix: fence bound-lease task transitions
73fb605251bd5e013394c2c644c12b2a58687b7c  test: prove expired unswept lease cannot transition
1096e5255049ca381d0994ac68535294facb6ed0  spec: bind transition lease fencing coverage
```

Current semantics:

- successful `claim`/`claim_next` binds exact lease to execution context;
- idempotency create/retry/complete re-check exact lease inside write transaction;
- once a lease is bound, ordinary `transition()` re-checks that lease in the same state+event transaction;
- wall-clock expiry blocks state/event mutation even before `expire_leases()` watchdog sweep;
- boot recovery temporarily suppresses dead-worker lease context only during replay, then restores stale context so dead worker does not regain mutation rights;
- fresh recovery process may read duplicate idempotency status without creating/retrying/completing it.

Regression tests:

```text
tests/T04_kernel/test_lease_fencing_idempotency.py
tests/T04_kernel/test_transition_lease_fencing.py
```

Coverage binding remains deliberately:

```text
execution.lease_fencing -> TEST_BOUND_PARTIAL / B
execution.checkpoint_idempotency -> TEST_BOUND_PARTIAL / B
CE-S01-05 -> TEST_BOUND_PARTIAL / B
```

No C/D/runtime promotion was made.

## B4. Concurrent work already absorbed

Other AI commits were preserved, not overwritten. Relevant recent ancestry includes reconciliation completion and sandbox/process work:

```text
3ba77105e18917eb9e77c55d9db97f59368ab33e  complete durable reconciliation outcome contract
9fa2b5cbdb928887d60d8c1f737bb92041bd2d74  accept complete Hands reconciliation outcome set
087695feff7063c7d92c71c2330a6f88242c592d  PARTIAL/CONFLICT fail-closed tests
318e180ba9bedab361f9e1450656db8029fa8055  fresh recovery duplicate probe
7b8fe6fbae5fc8dfcf730e2708071304769f2d6c  PARTIAL API-boundary regression
3eeb8127feeece10af106bc01c893170b07503e7  bind reconciliation coverage
8a323785d10af91b5bb948c4181a480dc1cee100  isolate managed process workspace and environment
```

Do not revert/reimplement these blindly; inspect live diff first.

## B5. Reality / blockers at snapshot

For SHA `1096e5255049ca381d0994ac68535294facb6ed0` GitHub created 7 check runs. At last refresh all were `queued`, including platform gates, main-lineage, security-mutation-durability and pre-RC jobs.

Therefore:

```text
same-SHA CI PASS: NOT OBSERVED
product FAIL from CI: NOT ESTABLISHED
current CI classification: BLOCKED / QUEUED INFRASTRUCTURE
release claim: FORBIDDEN
```

Do not reuse historical green status for this SHA.

## B6. Next exact dependency cone

Continue P0 Execution OS, but first refresh live main because `8a323...` already changed sandbox/process handling.

Priority order:

```text
1. execution.sandbox_isolation
   - inspect 8a323 live implementation + T03/T04/T10 tests
   - prove task-scoped workspace/process tree/environment + cleanup/reuse semantics
   - fix root cause only if contract still missing
2. execution.browser_session_isolation
   - profile/cookie/localStorage/task identity isolation
   - egress + cleanup before reuse
3. execution.service_lifecycle_readiness
   - configured-vs-observed manifest
   - dependency-aware startup
   - current PID/timestamp/endpoint evidence
   - port-open/stale-log must not equal READY
```

Do not add another validator layer. For each capability: Detect -> Why -> Fix -> Verify -> Learn/traceability, then sync to `main`.

## B7. Completion language

Allowed now:

> P0 lease/idempotency fencing root cause has code + regression-test + target-binding coverage on main, pending same-SHA runtime execution.

Forbidden now:

> P0 Execution OS verified / SCP complete / release ready.
