# GA — SCP Session Authority + Current Handoff

> File duy nhất để bắt đầu/tiếp tục mọi phiên SCP. Người dùng chỉ cần nói: **“Đọc GA trên main, refresh GitHub live rồi tiếp tục SCP.”**
>
> `GA.md` gồm hai phần: **SESSION RULES** (luật làm việc ổn định) và **CURRENT HANDOFF** (trạng thái công việc mới nhất). Chat history/model memory chỉ hỗ trợ continuity; không phải source of truth.

---

# A. SESSION RULES — Luật làm việc SCP

## A1. Authority order

Khi có mâu thuẫn, ưu tiên theo thứ tự:

1. Chỉ thị trực tiếp mới nhất của người dùng.
2. `AGENTS.md`.
3. `.agents/skills/scp-dna/SKILL.md` + `.agents/skills/scp-dna/references/dna-principles.md`.
4. `spec/complete_scp_reference.yaml` + `spec/protected_invariants.yaml`.
5. `spec/implementation_bindings.yaml`, `.agents/skills/release-gate-skill-dna-bindings.json` và các binding machine-readable liên quan.
6. `spec/scp_future_cause_effect_matrix.yaml` cho **toàn bộ structural/cause-effect coverage của Complete SCP**.
7. Skill chuyên biệt phù hợp task.
8. Live Git + runtime/test/evidence trên đúng SHA để xác định trạng thái implementation/maturity thực tế.
9. Phần `CURRENT HANDOFF` trong file này và task capsule/evidence liên quan.
10. Chat history/model memory.

Normative requirement không bị vô hiệu chỉ vì implementation hiện tại chưa đạt. Ngược lại, matrix/spec không được dùng như runtime proof. Nếu memory/chat mâu thuẫn với repo/evidence hiện tại thì **repo/evidence thắng**.

## A2. Bootstrap bắt buộc cho task SCP không tầm thường

Trước substantial analysis/audit/code/test-verdict/release claim:

1. Đọc `GA.md` trên `main`.
2. Đọc `AGENTS.md`.
3. Đọc `scp-dna` Skill.
4. Đọc DNA principles khi cần wording/invariant chính xác.
5. Đọc `spec/complete_scp_reference.yaml` + protected invariants nếu task liên quan Complete SCP/maturity/evidence/governance.
6. Đọc `spec/scp_future_cause_effect_matrix.yaml` nếu task liên quan kiến trúc, roadmap, capability coverage, T00–T11 hoặc thiết kế test.
7. Đọc `.agents/skills/release-gate-skill-dna-bindings.json` nếu là mandatory gate/audit/release/customer handoff.
8. Chỉ load Skill chuyên biệt liên quan; không nạp toàn bộ Skill pack mặc định.
9. Refresh live Git branch/HEAD.
10. So sánh live HEAD với `work_snapshot_sha`; nếu khác, xem commit/diff mới trước khi kế thừa trạng thái cũ.
11. Retrieve code/test/evidence theo dependency cone của task hiện tại; không đọc lại toàn repo mặc định.

## A3. Session Header nội bộ

Trước mutation hoặc audit đáng kể, agent phải tự xác định:

```text
branch: <live branch>
live_head: <live SHA>
work_snapshot_sha: <handoff SHA>
objective: <một mục tiêu chính>
loaded_authority: GA + AGENTS + SCP DNA + Complete SCP Reference + Matrix/Skill nếu liên quan
known_blockers: <...>
evidence_target: A/B/C/D hoặc scope tương ứng
structural_coverage_target: <systems/capabilities/cause-effect edges>
test_coverage_status: <PROVEN / PARTIAL / UNPROVEN / BLOCKED>
mutation_scope: <files/subsystems>
main_sync_policy: SYNC_FOR_CROSS_AI_REVIEW_AFTER_RELEVANT_REALITY_CHECK
```

## A4. Một task lớn = một session

Mặc định:

> **Một task lớn = một cuộc hội thoại/agent session riêng = một decision boundary rõ ràng.**

Tiếp tục cùng session nếu vẫn xử lý cùng root cause. Khi task đạt exit condition hoặc BLOCKED với evidence rõ ràng thì cập nhật `CURRENT HANDOFF`, tạo evidence/capsule nếu cần rồi kết thúc session.

Không kéo thêm một task lớn khác vào cùng context chỉ để giữ continuity.

## A5. Context discipline — giảm token nhưng không giảm bằng chứng

Không nén bằng cách bỏ evidence. Nén bằng cách địa chỉ hóa evidence:

- Stable invariants: tham chiếu file/hash, không paste lại mỗi vòng.
- SHA-bound state: dùng SHA + diff + affected dependency cone.
- Test/log lớn: lưu artifact/evidence; context chỉ giữ finding + evidence ref; mở raw khi cần phản chứng.
- File không đổi và ngoài dependency cone: không đọc lại mặc định.
- Handoff phải ngắn nhưng truy ngược được về source/evidence gốc.

Mục tiêu là giảm **frontier-model-visible workload**, không làm mất provenance.

## A6. Invariants bắt buộc

```text
Reality > Model
PASS != TRUE
UNKNOWN != VERIFIED
Consensus != Truth
independent lineage required
UNKNOWN_INDEPENDENCE does not count as independent support
fail-closed khi thiếu authority/evidence quan trọng
same-SHA evidence cho mandatory verification/release claims
không delete/skip/xfail test để manufacture green
không hạ assertion/coverage/security/mutation/acceptance threshold
không đổi fail-closed thành fail-open chỉ để pass
không blind-retry uncertain external side effect; reconcile first
small + reversible + observable changes
External Data -> Evidence -> Epistemic Assessment -> Knowledge; không External Data -> Knowledge
Knowledge/Reasoning/Forecast/Risk -> Proposal -> Governance -> Execution; không direct side effect
confidence không được thay epistemic verdict
correlation/precedence không được tự biến thành causality
forecast không phải Reality fact cho tới khi được resolve độc lập
simulation PASS không phải production PASS
max_cost_usd=0; unknown/stale price=DENY; paid_fallback=false
future capability chưa implement vẫn phải tồn tại trong Complete-SCP structural/test model
12 gate directories T00–T11 != Complete-SCP test coverage
```

Sau code work, dọn file tạm/rác ở thư mục gốc trước khi đồng bộ lên `main` để giữ repo sạch.

## A7. Failure classification

Phân biệt rõ:

- `HARNESS_BROKEN`: test/harness đang mã hóa semantics sai/cũ hoặc fixture sai; sửa harness nhưng phải giữ hoặc tăng strictness.
- `PRODUCT_BLOCKED`: capability/evidence cần thiết chưa tồn tại hoặc chưa đủ để chạy/verify.
- `PRODUCT_FAIL`: production path chạy và không đạt contract.
- `STRUCTURAL_COVERAGE_GAP`: Complete-SCP matrix có requirement/capability/edge nhưng chưa có test obligation/mapping tương ứng.
- `TEST_COVERAGE_UNPROVEN`: có test/gate nhưng chưa có machine evidence chứng minh chúng bao phủ toàn bộ required structural inventory.
- `BLOCKED`: thiếu evidence/authority; không suy diễn PASS.

## A8. Complete-SCP Structural/Test Coverage Contract

`spec/scp_future_cause_effect_matrix.yaml` là **Complete SCP Structural Cause-Effect Matrix**, không còn là file riêng cho P2. Nó phải bao phủ toàn bộ SCP hoàn thiện, gồm core systems, cross-cutting systems, phases P0–P4, authority boundaries, dependency, forbidden paths, cause-effect, failure/recovery, evidence maturity và T00–T11 obligations.

Bộ test phải tiến tới **traceability hai chiều**:

```text
Complete-SCP requirement/capability/cause-effect edge
    -> one-or-more applicable T00–T11 gate obligations
    -> concrete test(s)/validator(s)
    -> required evidence level A/B/C/D
    -> same-SHA evidence when mandatory

và ngược lại:

concrete mandatory test
    -> exact matrix requirement/capability/cause-effect edge
```

Quy tắc bắt buộc:

1. Có đủ thư mục `tests/T00_integrity` ... `tests/T11_release` **không đủ** để kết luận Complete-SCP coverage.
2. Mỗi required capability/cause-effect edge trong matrix phải có machine-readable test mapping hoặc trạng thái coverage rõ ràng.
3. Capability chưa implement không được bỏ khỏi matrix/test model; test obligation có thể ở trạng thái `BLOCKED_MISSING_IMPLEMENTATION` cho tới khi product được xây.
4. T00 phải dần trở thành meta-audit phát hiện:
   - orphan capability,
   - orphan mandatory test,
   - missing matrix -> test mapping,
   - missing gate applicability,
   - missing required evidence level,
   - forbidden shortcut / authority bypass,
   - stale/mismatched SHA evidence.
5. Final Complete-SCP claim chỉ hợp lệ khi structural coverage gap = 0, mandatory test coverage gap = 0, blocker = 0 và maturity/evidence target của từng capability đạt trên đúng SHA.

## A9. Main synchronization policy

Chính sách hiện tại của người dùng:

> **Đồng bộ thay đổi đã qua relevant Reality check lên `main` để các AI khác có thể kiểm tra.**

`main` là nhánh cộng tác/kiểm tra hiện hành, không phải bằng chứng tự động rằng release đã hoàn tất. Mọi release claim vẫn phải tuân same-SHA mandatory gates, provenance và Reality verification.

## A10. Kết thúc mỗi session

Trước khi đóng một task lớn, cập nhật **phần `CURRENT HANDOFF`** của `GA.md` với:

```text
work_snapshot_sha
live branch/head
objective vừa xử lý
changed files / relevant commits
focused/full test results thực tế
structural/test coverage state
failure classification
new evidence refs/artifacts
open blockers
next exact task
known limitations
```

Chỉ sửa SESSION RULES khi luật làm việc SCP thực sự thay đổi.

---

# B. CURRENT HANDOFF — Trạng thái SCP hiện tại

> Đây là continuity metadata, không phải release evidence authority. Phiên mới luôn phải refresh GitHub live trước khi làm.

## B1. Project

```text
project: SCP / GA-LAB
repository: checken1994/GA-LAB
active_sync_branch: main
current_workstream: Complete SCP structural coverage alignment + test coverage expansion
main_role: nguồn đồng bộ hiện hành để nhiều AI kiểm tra cùng một trạng thái
```

## B2. Live structural snapshot at this handoff

```text
work_snapshot_sha: 18d998bc836ea0a55517192d7fc2648636ed8d58
matrix_file: spec/scp_future_cause_effect_matrix.yaml
matrix_schema: 4.0
matrix_blob_sha: ae821844a56b57000ef9348f3bdec121066486c8
matrix_scope: ENTIRE_COMPLETE_SCP
matrix_declared_core_systems: 12/12
matrix_declared_cross_cutting_systems: 8/8
matrix_declared_phases: 5/5 (P0-P4)
matrix_declared_test_gates: 12/12 (T00-T11)
matrix_declared_capabilities: 110
matrix_declared_cause_effect_edges: 38
matrix_structural_verdict: STRUCTURALLY_COMPLETE_BY_DECLARATION_PENDING_MACHINE_VALIDATION
runtime_verdict_from_matrix: NOT_DERIVED_FROM_THIS_FILE
```

Commit tạo matrix v4:

```text
18d998bc836ea0a55517192d7fc2648636ed8d58
spec: rebuild complete SCP structural cause-effect matrix v4
```

## B3. Current test architecture reality

Live repo hiện có taxonomy:

```text
T00_integrity
T01_boot
T02_contract
T03_capability
T04_kernel
T05_gateway
T06_verifier
T07_learning
T08_runtime
T09_golden_task
T10_recovery
T11_release
```

Nhưng trạng thái đúng hiện nay là:

```text
T00-T11 taxonomy exists: YES
Complete-SCP structural test coverage proven: NO
110 capability -> concrete test traceability proven: NO
38 cause-effect edge -> concrete test traceability proven: NO
bidirectional matrix <-> test traceability: NOT YET MACHINE-PROVEN
current_complete_scp_test_verdict: TEST_COVERAGE_UNPROVEN / INCOMPLETE
```

Do đó **không được** suy diễn từ việc các gate hiện tại PASS trong một scope cũ rằng bộ test đã bao phủ Complete SCP.

`.agents/skills/release-gate-skill-dna-bindings.json` hiện đã bind mandatory release gates với SCP DNA + specialized skills, nhưng binding này là **gate/skill contract**, không tự chứng minh 110 capability/38 cause-effect edge đã được test đầy đủ.

## B4. Current semantic/reference gap

`spec/complete_scp_reference.yaml` hiện vẫn machine-encode một tập capability nhỏ hơn nhiều so với structural inventory 110 capability của matrix v4. `spec/implementation_bindings.yaml` cũng chỉ bind subset implementation hiện hành.

Điều này không làm các capability tương lai biến mất khỏi Complete SCP; nó tạo một **reference-alignment debt** cần đóng:

```text
Complete SCP structural matrix
    -> complete_scp_reference semantic inventory
    -> implementation bindings / self-model
    -> test coverage bindings
    -> product/runtime
    -> Reality evidence
```

Cho tới khi các lớp này được đồng bộ và machine-validated, không được gọi toàn hệ thống là Complete SCP verified.

## B5. Historical P0 evidence — giữ để truy vết, không dùng cho current main

Historical checkpoint đã từng ghi:

```text
last_recorded_p0_verified_snapshot: 8582a03147608442331967ef2b1d9c790e21695f
historical_verdict: PASS_WITHIN_SCOPE
```

Đây chỉ là evidence của **SHA cũ / P0 scope cũ**. Theo same-SHA rule, nó không chứng minh current `main` ở `18d998bc...`, vì `main` đã có thêm P1/code/spec commits sau checkpoint đó.

Recent `main` history đã có các commit P1 như Cognitive Orchestrator, Learning Loop Authorities và EpistemicBoundary integration, nhưng maturity/Complete-SCP coverage của chúng phải được đánh giá lại bằng current matrix + current tests + same-SHA evidence; không suy diễn VERIFIED từ commit message hoặc class existence.

## B6. Current global verdict

```text
Complete-SCP structural matrix: DECLARED COMPLETE, PENDING MACHINE VALIDATION
Complete-SCP implementation: NOT CLAIMED COMPLETE
Complete-SCP test coverage: INCOMPLETE / NOT MACHINE-PROVEN
Complete-SCP runtime verification: NOT ESTABLISHED
Complete-SCP release readiness: NOT ESTABLISHED
```

## B7. Open blockers / missing pieces

1. Chưa có machine validator chứng minh matrix v4 thật sự không thiếu core/cross-cutting/capability/edge/gate obligation.
2. `complete_scp_reference.yaml` chưa được mở rộng/aligned để machine-encode đầy đủ semantic inventory của Complete SCP như matrix v4.
3. Chưa có machine-readable **matrix -> T00–T11 -> concrete test -> evidence level** coverage binding cho toàn bộ inventory.
4. T00 chưa được chứng minh có thể fail-closed khi một required capability/cause-effect edge không có test coverage.
5. Bộ test hiện tại chưa được chứng minh bao phủ đủ toàn bộ 110 capability và 38 cause-effect edges.
6. Current `main` chưa có full same-SHA Complete-SCP verification run tương ứng với matrix v4.

## B8. Next exact task

Ưu tiên tiếp theo:

```text
1. Tạo machine-readable Complete-SCP test coverage binding/manifest.
2. Map toàn bộ matrix requirements/capabilities/cause-effect edges -> T00–T11 applicability -> concrete tests -> evidence target.
3. Nâng T00 meta-audit để fail khi có structural/test coverage gap.
4. Mở rộng/correct test suite theo matrix; missing product => PRODUCT_BLOCKED, không omit/skip để giữ green.
5. Đồng bộ complete_scp_reference.yaml với structural inventory ở mức WHAT, không nhét implementation HOW vào reference.
6. Khi coverage gap = 0 mới chạy full strict/safety/mutation/acceptance/Reality/recovery trên cùng SHA và tạo manifest/provenance.
```

---

# C. Câu lệnh ngắn cho phiên mới

Người dùng chỉ cần nói:

> **“Đọc `GA.md` trên `main`, refresh GitHub live rồi tiếp tục SCP.”**

Agent phải tự dựng lại authority + current state theo file này, đặc biệt phải nhớ:

> **Matrix v4 bao phủ Complete SCP ở mức structural declaration; bộ test hiện tại chưa được chứng minh bao phủ tương ứng. Nhiệm vụ là đóng structural/test coverage gap, không được lấy PASS scope cũ làm Complete-SCP PASS.**
