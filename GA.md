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
active_sync_branch: integration/experiment-god-split-and-providers -> guarded PR -> main
work_snapshot_sha: f0ed761511beb3e2e23830fcbdb828cfe9208f82
snapshot_role: bounded dashboard-audit recovery and immutable post-merge handoff repair; new freeze required
active_target_revision: 4.0.2
baseline_status: ACTIVE_BASELINE_FOR_BUILD
runtime/release_verdict: BLOCKED_PENDING_SAME_SHA_GITHUB_GATES
```

`work_snapshot_sha` là commit sản phẩm trước commit handoff này; luôn resolve full SHA
từ live Git trước khi dùng. Không kế thừa SHA, branch state hoặc verdict trong phần
này nếu chưa refresh GitHub.

## B2. Release task scope hiện hành

```text
1. Sửa lỗi initialization/product/harness được GitHub-hosted runner chứng minh.
2. Chỉ tạo manifest-only freeze sau khi mandatory gates xanh trên candidate tree.
3. RC_DONE chỉ hợp lệ khi mọi required gate PASS trên đúng frozen SHA và blockers=0.
4. Merge integration -> main chỉ qua guarded workflow khi remote head vẫn đúng frozen SHA.
5. Sau merge, chạy lại full-system customer-handoff trên chính merge SHA của main.
6. Không khởi động SCP/service/runtime trên PC người dùng trong task này.
```

Các claim coverage/architecture trước đây không được dùng thay cho same-SHA release
evidence. Authority machine-readable vẫn là target manifest, test-skill binding,
complete reference và protected invariants được nêu trong phần A.

## B3. Live lineage đã hấp thụ vào candidate

```text
origin/main at task refresh: ac68ba9bfb4d8955c9cfa20e574113feb8f0102b
candidate product snapshot: fc272cf (resolve full SHA live)

candidate contains main plus:
  b94cba0  close missing authoritative TaskKernel paths and acceptance races
  f975210  provision Bun in authoritative RC platform/security jobs
  fc272cf  restore strict TaskKernel HUMAN_REVIEW semantics; isolate acceptance
             pricing proofs; keep multi-provider crosscheck enabled
```

## B4. Root-cause classification và correction

```text
HARNESS_BROKEN:
  main RC referenced deleted/non-existent TaskKernel durability test paths.
  Candidate points the workflow to extant strict durability/recovery tests.

PRODUCT_FAIL / ACCEPTANCE INTEGRATION:
  main acceptance failed verified completion, provider fallback, duplicate
  idempotency and parallel durability behavior.
  Candidate contains the AskKernelAdapter race correction and deterministic
  loopback provider evidence required to exercise those paths.

REJECTED WEAKENING IN EARLIER CANDIDATE:
  Do not accept f975210 as RC evidence by itself. Its acceptance harness disabled
  SCP_MULTI_LLM_CROSSCHECK, wrote fixture proof into shared repository state,
  swallowed proof errors, and excluded HUMAN_REVIEW from in_flight_count.
  fc272cf removes those weakenings and adds regression contracts.
```

Không có test nào bị delete/skip/xfail, không hạ threshold, không ignore exit code,
và không đổi fail-closed thành fail-open để tạo màu xanh.

## B5. Evidence đã quan sát trong task

```text
main ac68ba9 diagnostic rerun:
  baseline: PASS
  authoritative RC: FAIL
    - TaskKernel durability gate: missing workflow test path
    - behavioral acceptance: A03/A05/A08/A11 failed
  conclusion: main is not releasable; runner initialization was not the only issue

candidate fc272cf local non-runtime evidence:
  py_compile of changed executable/tests: PASS
  tests/T04_kernel + tests/T05_gateway + tests/T11_release: 85 PASS
  SCP process/service started on user PC: NO

candidate same-SHA GitHub mandatory gates: PENDING
manifest-only freeze: PENDING
RC_DONE/blockers=0: NOT YET DERIVED
main merge and fresh customer handoff: PENDING
```

Local PASS chỉ có nghĩa không thấy lỗi trong scope đã nêu; nó không thay thế GitHub
multi-platform, acceptance, mutation, security, manifest hoặc customer-handoff gate.

## B6. Finite next sequence

```text
1. Push candidate và fast-forward designated integration branch only after live refresh.
2. Let GitHub-hosted mandatory gates test the exact candidate SHA.
3. If a gate fails, classify and repair product/harness at the failure point.
4. When pre-freeze gates pass, allow workflow to create exactly one manifest-only child.
5. Verify every mandatory gate and blockers=0 on that frozen child SHA.
6. Dispatch guarded merge with frozen-head equality check.
7. Require a fresh full-system customer-handoff PASS on resulting main merge SHA.
```

## B7. Completion language

Allowed now:

> Candidate strict-correction đã qua 85 unit-contract test local không chạy SCP service; release vẫn BLOCKED cho tới khi toàn bộ mandatory gate PASS trên cùng frozen SHA, blockers=0, guarded merge thành công và customer-handoff mới PASS trên merge SHA của main.

Forbidden now:

> Candidate/main đã DONE, RC/release-ready, production-ready hoặc customer-handoff hoàn tất trước khi có đúng chuỗi evidence nêu trên.

## B8. RC continuation — 2026-09-04, registry and handoff closure

- Frozen `f2ded72de8a13e92dc28ae06649ed83f3e1d5bad` reached `RC_DONE`, blockers=0
  in run `33843699788`. The approved promotion run `33845108898` then failed
  Ubuntu dashboard audit twice, both with npm registry `E503` at the quick-audit
  endpoint. No PR or main merge occurred. Earlier green evidence is retained,
  but is not reused for a changed candidate.
- `f0ed761` repairs the harness with at most three bounded native npm audit
  attempts, retries only transient registry/network failures, keeps
  `--omit=dev --audit-level=high`, rejects missing/invalid reports and records
  command, exits, exact SHA, lockfile hash and Skill/DNA hashes. `npm ci` no longer
  performs its duplicate best-effort advisory query; the separate mandatory
  audit and dashboard build both remain blocking.
- Bot-token writes do not trigger a fresh GitHub push workflow. Promotion now
  explicitly dispatches the complete handoff on main with `handoff_merge_sha`.
  The lineage gate requires live main == checkout == dispatched merge SHA,
  exactly one merged integration PR and byte-identical Git trees between main
  and the immutable frozen PR head (including the manifest). Linear squash
  lineage is supported to preserve the live main ruleset; for a two-parent
  merge, the PR head must additionally equal the second parent.
  Unknown/mismatched lineage blocks handoff.
- Local non-runtime verification: `python -m pytest -q tests/T11_release --tb=short`
  returned 59 passed; focused Ruff, py_compile and Skill/DNA contract passed.
  This is only patch verification, not current-SHA release evidence.
- Remaining sequence: run GitHub mandatory gates on the new candidate, create a
  manifest-only child, verify that exact frozen child, guarded PR merge, then
  fresh full-system handoff on the actual main merge SHA. No SCP service/runtime
  is to be launched on the user's PC. The user's root checkout is preserved;
  the existing RC branch is being worked in `scp-rc-promotion-fix` worktree.
- Rollback is a reviewed Git revert of the scoped harness changes; never remove
  a mandatory gate or lower a security/mutation threshold as a rollback shortcut.
- Continuation findings: Windows npm can emit registry timeout without
  `error.code`; the exact observed audit-endpoint messages are now retryable
  errors, never success. Main requires linear history and the `p0-baseline`
  check. Use SHA-guarded squash merge without changing that ruleset. After
  freeze, sync its exact SHA to the existing RC branch to obtain baseline CI;
  create the integration PR through the authorized user session if bot PR
  creation is unavailable, then let the guarded workflow find and merge it.
- Frozen run on `0856490` exposed the legacy npm 10 Quick Audit fallback returning
  400 from the retired endpoint. The auditor is now pinned to npm 11.19.1 in the
  GitHub runner's task-local directory (Node 20.20.2 satisfies its ^20.17.0 engine).
  Its upstream source uses Bulk Advisory only; no 400 response is treated as a
  pass or generic retry. Response headers/cookies are redacted from new audit
  artifacts. Ref: https://github.com/npm/cli/blob/v11.19.1/workspaces/arborist/lib/audit-report.js
