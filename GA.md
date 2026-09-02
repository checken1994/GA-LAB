# GA — SCP Session Authority + Current Handoff

> File bootstrap duy nhất cho mọi phiên SCP. Người dùng chỉ cần nói: **“Đọc GA trên main, refresh GitHub live rồi tiếp tục SCP.”**
>
> `GA.md` gồm **SESSION RULES** và **CURRENT HANDOFF**. Chat history/model memory chỉ hỗ trợ continuity; không phải source of truth.

---

# A. SESSION RULES

## A1. Authority order

Khi có mâu thuẫn, ưu tiên:

1. Chỉ thị trực tiếp mới nhất của người dùng.
2. `AGENTS.md`.
3. `.agents/skills/scp-dna/SKILL.md` + `.agents/skills/scp-dna/references/dna-principles.md`.
4. `spec/complete_scp_reference.yaml` + `spec/protected_invariants.yaml`.
5. Skill chuyên biệt phù hợp task.
6. `spec/scp_future_target_manifest.yaml` và **effective target spec** mà manifest compose.
7. `spec/implementation_bindings.yaml`, `.agents/skills/release-gate-skill-dna-bindings.json` và binding machine-readable liên quan.
8. Live Git + runtime/test/evidence trên đúng SHA để xác định implementation/maturity thực tế.
9. `CURRENT HANDOFF` trong file này và evidence/task capsule liên quan.
10. Chat history/model memory.

Normative target requirement không bị xóa chỉ vì implementation hiện tại thiếu. Ngược lại, target spec không phải runtime proof. Nếu memory/chat mâu thuẫn với repo/evidence live thì **repo/evidence thắng**.

### Effective Target Architecture

Không đọc `spec/scp_future_cause_effect_matrix.yaml` riêng lẻ như baseline hiện hành.

```text
spec/scp_future_target_manifest.yaml
    -> base: spec/scp_future_cause_effect_matrix.yaml @ revision 4.0.1
    -> overlay: spec/scp_future_cause_effect_matrix_v4_0_2.overlay.json
    -> effective SCP Future Target Architecture revision 4.0.2
```

Base + overlay phải được compose đúng một lần theo manifest. Overlay không tự đứng một mình; base 4.0.1 cũng không còn là effective target baseline khi làm architecture task.

## A2. Bootstrap bắt buộc cho task SCP không tầm thường

Trước substantial analysis/audit/code/test-verdict/release claim:

1. Đọc `GA.md` trên `main`.
2. Đọc `AGENTS.md`.
3. Đọc SCP DNA Skill; đọc DNA principles khi cần wording/invariant chính xác.
4. Đọc `complete_scp_reference.yaml` + protected invariants nếu liên quan target/maturity/evidence/governance.
5. Nếu liên quan kiến trúc/roadmap/test coverage: đọc `spec/scp_future_target_manifest.yaml`, rồi compose base + overlay theo manifest.
6. Đọc Skill chuyên biệt liên quan; không nạp toàn bộ Skill pack mặc định trừ khi task thật sự là cross-Skill architecture review.
7. Đọc release-gate Skill/DNA bindings nếu là mandatory gate/release/customer handoff.
8. Refresh live Git branch/HEAD.
9. So sánh live HEAD với `work_snapshot_sha`; nếu khác, xem commit/diff mới trước khi kế thừa trạng thái cũ.
10. Retrieve code/test/evidence theo dependency cone; không đọc lại toàn repo mặc định.

## A3. Session Header nội bộ

```text
branch: <live branch>
live_head: <live SHA>
work_snapshot_sha: <handoff SHA>
objective: <một mục tiêu chính>
loaded_authority: GA + AGENTS + DNA + Complete Reference + Target Manifest/Skill nếu liên quan
known_blockers: <...>
evidence_target: A/B/C/D hoặc scope tương ứng
structural_coverage_target: <systems/capabilities/cause-effect edges>
test_coverage_status: <PROVEN / PARTIAL / UNPROVEN / BLOCKED>
mutation_scope: <files/subsystems>
main_sync_policy: SYNC_FOR_CROSS_AI_REVIEW_AFTER_RELEVANT_REALITY_CHECK
```

## A4. Một task lớn = một session

Mặc định: **một task lớn = một cuộc hội thoại/agent session riêng = một decision boundary rõ ràng**. Tiếp tục cùng session nếu vẫn xử lý cùng root cause. Khi đạt exit condition hoặc BLOCKED với evidence rõ ràng thì cập nhật handoff và kết thúc; không kéo thêm task lớn khác chỉ để giữ continuity.

## A5. Context discipline

Không nén bằng cách bỏ evidence. Nén bằng địa chỉ hóa evidence:

- Stable invariants: tham chiếu file/hash.
- SHA-bound state: dùng SHA + diff + affected dependency cone.
- Log/test lớn: lưu artifact/evidence; context chỉ giữ finding + evidence ref.
- File không đổi ngoài dependency cone: không đọc lại mặc định.
- Handoff ngắn nhưng phải truy ngược được về source/evidence.

## A6. Invariants bắt buộc

```text
Reality > Model
PASS != TRUE
UNKNOWN != VERIFIED
Consensus != Truth
independent lineage required
UNKNOWN_INDEPENDENCE does not count as independent support
fail-closed khi thiếu authority/evidence quan trọng
same-SHA evidence cho mandatory verification/release claim
không delete/skip/xfail test để manufacture green
không hạ assertion/coverage/security/mutation/acceptance threshold
không đổi fail-closed thành fail-open chỉ để pass
không blind-retry uncertain external side effect; reconcile first
small + reversible + observable changes
External Data -> Evidence -> Epistemic Assessment -> Knowledge
Knowledge/Reasoning/Forecast/Risk -> Proposal -> Governance -> Execution
confidence không thay epistemic verdict
correlation/precedence không tự biến thành causality
forecast != Reality fact cho tới khi resolve độc lập
simulation PASS != production PASS
max_cost_usd=0; unknown/stale price=DENY; paid_fallback=false
future capability chưa implement vẫn phải tồn tại trong target structural/test model
12 gate directories T00–T11 != Complete-SCP test coverage
sandbox/browser/workspace/process state phải task-scoped; không reuse state bẩn/cross-task
open port/stale log != service readiness
latency optimization không được bỏ policy/capability/revocation/egress/verifier/recovery/high-risk approval
gateway failover không được hạ privacy/zero-cost/epistemic/retry safety
Skill count/index tự khai chỉ là giả thuyết; phải recount khi Skill pack đổi
```

Sau code work, dọn file tạm/rác ở root trước khi đồng bộ `main`.

## A7. Failure classification

- `HARNESS_BROKEN`: test/harness mã hóa semantics sai/cũ; sửa harness nhưng giữ hoặc tăng strictness.
- `PRODUCT_BLOCKED`: capability/evidence cần thiết chưa tồn tại hoặc chưa đủ để verify.
- `PRODUCT_FAIL`: production path chạy và không đạt contract.
- `STRUCTURAL_COVERAGE_GAP`: target spec có requirement/capability/edge nhưng test obligation/mapping thiếu.
- `TEST_COVERAGE_UNPROVEN`: gate/test tồn tại nhưng chưa có machine evidence chứng minh đủ coverage.
- `BLOCKED`: thiếu evidence/authority; không suy diễn PASS.

## A8. Structural/Test Coverage Contract

Bộ test phải tiến tới traceability hai chiều:

```text
Target requirement/capability/cause-effect edge
    -> applicable T00–T11 gate
    -> concrete test/validator
    -> required evidence A/B/C/D
    -> same-SHA evidence khi mandatory

và ngược lại:
mandatory concrete test -> exact target requirement/capability/edge
```

Có đủ `tests/T00_integrity` ... `tests/T11_release` không đủ để kết luận coverage. Capability chưa implement vẫn nằm trong target model; test obligation có thể `BLOCKED_MISSING_IMPLEMENTATION`. T00 phải dần fail-closed cho orphan capability/test, missing mapping/evidence, forbidden shortcut và stale/mismatched SHA evidence.

Final Complete-SCP claim chỉ hợp lệ khi structural coverage gap = 0, mandatory test coverage gap = 0, blocker = 0 và maturity/evidence target đạt trên đúng SHA.

## A9. Bounded architecture audit / baseline freeze

Effective target baseline hiện là **4.0.2**. Sau bounded structural checks + cross-Skill traceability trong declared scope, **dừng architecture-audit và build SCP theo baseline**.

Chỉ reopen target architecture khi có một trong các trigger:

- direct user architecture change;
- DNA hoặc normative Skill thay đổi;
- Reality evidence mới phát hiện missing piece/contradiction;
- implementation chứng minh target contract hiện tại không thể dung hòa;
- security/recovery evidence phủ định assumption kiến trúc.

Không reopen chỉ vì muốn audit thêm, vì validator PASS rồi muốn thêm validator không có evidence mới, hoặc vì implementation detail không làm đổi target WHAT contract.

## A10. Main synchronization + session close

Chính sách hiện tại: **đồng bộ thay đổi đã qua relevant Reality check lên `main` để AI khác kiểm tra**. `main` là nguồn cộng tác hiện hành, không tự động là release proof.

Trước khi đóng task lớn, cập nhật `CURRENT HANDOFF` với SHA live, objective, changed files/commits, test/evidence thực tế, structural/test coverage state, blockers, next exact task và limitations.

---

# B. CURRENT HANDOFF

> Continuity metadata, không phải release evidence authority. Phiên mới luôn refresh GitHub live trước khi làm.

## B1. Project

```text
project: SCP / GA-LAB
repository: checken1994/GA-LAB
active_sync_branch: main
current_workstream: SCP Future Target Architecture baseline 4.0.2 -> implementation/test alignment
main_role: nguồn đồng bộ hiện hành để nhiều AI kiểm tra cùng một trạng thái
```

## B2. Effective future-target architecture baseline

```text
effective_target_revision: 4.0.2
target_manifest: spec/scp_future_target_manifest.yaml
base_file: spec/scp_future_cause_effect_matrix.yaml
base_revision: 4.0.1
base_blob_sha: 0954c3002dfcc8d688efb1b826cfa509e71516e6
overlay_file: spec/scp_future_cause_effect_matrix_v4_0_2.overlay.json
overlay_blob_sha: 9e82a9c7d26e4a8f7f96a4db61b01c9eea4c48cd
composition: BASE_PLUS_OVERLAY_BY_UNIQUE_ID
scope: WHOLE_FUTURE_TARGET_ARCHITECTURE
core_systems: 12
cross_cutting_systems: 8
phases: 5 (P0-P4)
test_gates: 12 (T00-T11)
capabilities: 138
cause_effect_edges: 60
global_invariants: 34
normative_scp_skills: 13
runtime_verdict_from_target_spec: NOT_DERIVED_FROM_TARGET_SPEC
epistemic_completeness: OPEN_TO_NEW_REALITY_MISSING_PIECES
baseline_status: ACTIVE_BASELINE_FOR_BUILD
```

Relevant synchronization commits:

```text
65d9702c855efe834b9d586caef47c20ca5734dd  spec: complete SCP future target matrix v4
d2f85381c75cd99bc749a7c936164bf19039c2a2  spec: add SCP target v4.0.2 overlay
b79172a63c53e373ed7aa82bba510267bcd27780  spec: activate SCP future target v4.0.2 baseline
```

## B3. What v4.0.2 added over v4.0.1

V4.0.2 keeps the same 12 core + 8 cross-cutting systems and P0–P4 phases, but closes Skill-derived architecture gaps before deep implementation:

- durable task state machine, append-only journal/projection, lease fencing, checkpoint/idempotency;
- sandbox/workspace/process/browser task isolation and verified cleanup;
- service lifecycle/readiness contract based on configured-vs-observed Reality;
- gateway circuit breaker, bounded jitter backoff, privacy/zero-cost-safe fallback and disagreement→UNKNOWN;
- DOM visibility sanitization, injection guard, browser egress enforcement and hard timeout semantics;
- performance spans + safety metrics + bounded concurrency/fairness contract;
- Skill contract integrity and 13/13 Skill -> structural target -> T00–T11 traceability;
- 5 new global invariants G30–G34 and open questions OQ16–OQ19.

## B4. Current test/reference reality

```text
T00-T11 taxonomy exists: YES
Target architecture effective revision: 4.0.2
138 capability -> concrete test traceability proven: NO
60 cause-effect edge -> concrete test traceability proven: NO
bidirectional target <-> concrete test traceability: NOT YET MACHINE-PROVEN
complete_scp_reference aligned to all 138 target capabilities: NO
implementation bindings cover full target: NO (expected during development)
current_complete_scp_test_verdict: TEST_COVERAGE_UNPROVEN / INCOMPLETE
```

`complete_scp_reference.yaml` và implementation bindings hiện chỉ machine-encode subset nhỏ hơn target inventory. Đây là reference/test alignment debt; **không được xóa target capability chỉ vì chưa implement hoặc chưa có reference binding**.

## B5. Historical P0 evidence

```text
last_recorded_p0_verified_snapshot: 8582a03147608442331967ef2b1d9c790e21695f
historical_verdict: PASS_WITHIN_SCOPE
```

Đây chỉ là evidence SHA/P0 scope cũ. Không dùng nó làm current-main hoặc Complete-SCP proof.

## B6. Current global verdict

```text
SCP Future Target Architecture 4.0.2: ACTIVE BASELINE FOR BUILD
Target internal content review: COMPLETED FOR CURRENT DECLARED SCOPE
Absolute/no-missing-piece completeness: NOT CLAIMED / UNPROVABLE BY DESIGN
Current implementation: NOT CLAIMED COMPLETE
Current concrete test coverage: INCOMPLETE / NOT MACHINE-PROVEN
Current runtime verification: NOT ESTABLISHED FOR COMPLETE SCP
Current release readiness: NOT ESTABLISHED FOR COMPLETE SCP
```

Không tiếp tục mở rộng đặc tả chỉ để “audit thêm”. Từ đây mặc định **build theo baseline 4.0.2**; chỉ reopen theo trigger ở A9.

## B7. Open implementation/alignment work

1. Tạo machine-readable target test coverage binding: 138 capabilities / 60 edges -> T00–T11 -> concrete test -> evidence target.
2. Nâng T00 meta-audit để fail-closed khi coverage binding thiếu/sai.
3. Đồng bộ `complete_scp_reference.yaml` với target WHAT inventory mà không nhét implementation HOW.
4. Xây/sửa product theo baseline; missing implementation = `PRODUCT_BLOCKED`, không omit/skip để giữ green.
5. Khi từng phase/scope đủ implementation, chạy bounded same-SHA verification đúng evidence target.

Đây là **build work**, không phải lý do tự động reopen architecture baseline.

## B8. Next exact task

```text
Build against effective target revision 4.0.2.
Ưu tiên đóng machine-readable target -> concrete-test traceability và tiếp tục P1/P2 implementation theo dependency order.
Không quay lại architecture audit trừ khi một A9 reopen trigger xuất hiện.
```

---

# C. Câu lệnh ngắn cho phiên mới

> **“Đọc `GA.md` trên `main`, refresh GitHub live rồi tiếp tục SCP.”**

Agent phải nhớ:

> **Effective target architecture = manifest 4.0.2 = base 4.0.1 + overlay 4.0.2. Đây là baseline để BUILD, không phải runtime/release proof; không audit đặc tả vô hạn nếu không có reopen trigger.**
