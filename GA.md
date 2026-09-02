# GA — SCP Session Authority + Current Handoff

> File duy nhất để bắt đầu/tiếp tục mọi phiên SCP. Mục tiêu là để người dùng chỉ cần nói: **“Đọc GA trên main rồi tiếp tục SCP.”**
>
> `GA.md` gồm hai phần: **SESSION RULES** (luật làm việc ổn định) và **CURRENT HANDOFF** (trạng thái công việc mới nhất). Chat history/model memory chỉ hỗ trợ continuity; không phải source of truth.

---

# A. SESSION RULES — Luật làm việc SCP

## A1. Authority order

Khi có mâu thuẫn, ưu tiên theo thứ tự:

1. Chỉ thị trực tiếp mới nhất của người dùng.
2. `AGENTS.md`.
3. `.agents/skills/scp-dna/SKILL.md` + `.agents/skills/scp-dna/references/dna-principles.md`.
4. `spec/complete_scp_reference.yaml`, protected invariants và implementation/test bindings hiện hành.
5. Skill chuyên biệt phù hợp task.
6. Live Git + runtime/test/evidence trên đúng SHA.
7. Phần `CURRENT HANDOFF` trong file này và task capsule/evidence liên quan.
8. Chat history/model memory.

Nếu memory/chat mâu thuẫn với repo/evidence hiện tại thì **repo/evidence thắng**.

## A2. Bootstrap bắt buộc cho task SCP không tầm thường

Trước substantial analysis/audit/code/test-verdict/release claim:

1. Đọc `AGENTS.md`.
2. Đọc `scp-dna` Skill.
3. Đọc DNA principles khi cần wording/invariant chính xác.
4. Đọc `spec/complete_scp_reference.yaml` nếu liên quan Complete SCP/P0/P1/P2/maturity/evidence/governance.
5. Đọc `.agents/skills/release-gate-skill-dna-bindings.json` nếu là mandatory gate/audit/release/customer handoff.
6. Chỉ load Skill chuyên biệt liên quan; không nạp toàn bộ Skill pack mặc định.
7. Đọc phần `CURRENT HANDOFF` bên dưới.
8. Refresh live Git branch/HEAD.
9. So sánh live HEAD với `work_snapshot_sha`. Nếu khác, xem commit/diff mới trước khi kế thừa trạng thái cũ.
10. Retrieve code/test/evidence theo dependency cone của task hiện tại; không đọc lại toàn repo mặc định.

## A3. Session Header nội bộ

Trước mutation hoặc audit đáng kể, agent phải tự xác định:

```text
branch: <live branch>
live_head: <live SHA>
work_snapshot_sha: <handoff SHA>
objective: <một mục tiêu chính>
loaded_authority: AGENTS + SCP DNA + relevant Skill(s) + Complete SCP Reference nếu cần
known_blockers: <...>
evidence_target: A/B/C/D hoặc scope tương ứng
mutation_scope: <files/subsystems>
main_mutation: FORBIDDEN trừ khi user chỉ thị rõ
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
main không merge/mutate code trừ khi người dùng chỉ thị rõ và release rules cho phép
```

## A7. Failure classification

Phân biệt rõ:

- `HARNESS_BROKEN`: test/harness đang mã hóa semantics sai/cũ hoặc fixture sai; sửa harness nhưng phải giữ hoặc tăng strictness.
- `PRODUCT_BLOCKED`: capability/evidence cần thiết chưa tồn tại hoặc chưa đủ để chạy/verify.
- `PRODUCT_FAIL`: production path chạy và không đạt contract.
- `BLOCKED`: thiếu evidence/authority; không suy diễn PASS.

## A8. Kết thúc mỗi session

Trước khi đóng một task lớn, cập nhật **chỉ phần `CURRENT HANDOFF`** của `GA.md` với:

```text
work_snapshot_sha
live development branch
objective vừa xử lý
changed files / relevant commits
focused/full test results thực tế
failure classification
new evidence refs/artifacts
open blockers
next exact task
known limitations
```

Không sửa SESSION RULES nếu luật làm việc SCP không thay đổi.

---

# B. CURRENT HANDOFF — Trạng thái SCP hiện tại

> Đây là continuity metadata, không phải release evidence authority. Phiên mới luôn phải refresh GitHub live trước khi làm.

## B1. Project

```text
project: SCP / GA-LAB
repository: checken1994/GA-LAB
development_branch: 26-p0-foundation-06-14
current_phase: 26-P0 Foundation
main_role: đồng bộ lên main để AI khác có thể kiểm tra
```

## B2. Technical work snapshot

```text
work_snapshot_sha: 8582a03147608442331967ef2b1d9c790e21695f
```

Đây là SHA code/test sau khi đã fix toàn bộ blocker và chạy Strict System Audit thành công.

## B3. Last recorded technical state at `work_snapshot_sha`

```text
P0-06 Source Identity              IMPLEMENTED / VERIFIED STRICT
P0-07 Lineage                      IMPLEMENTED / VERIFIED STRICT
P0-08 Prediction Ledger            IMPLEMENTED / VERIFIED STRICT
P0-09 Calibration                  IMPLEMENTED / VERIFIED STRICT
P0-10 Self-Model                   IMPLEMENTED / VERIFIED STRICT
P0-11 Drift Guard                  IMPLEMENTED / VERIFIED STRICT
P0-12 Privacy/Retention            IMPLEMENTED / VERIFIED STRICT
P0-13 Z0/Z1                        IMPLEMENTED / VERIFIED STRICT
P0-14 Z2/Z3                        IMPLEMENTED / VERIFIED STRICT
P0-14 Z4 bridge hardening          COMPLETED
Vertical Slice A/B                 COMPLETED
P0 freeze/full strict checkpoint   COMPLETED
```

Last recorded focused branch result:

```text
All 11 gates PASSED
overall_verdict: PASS_WITHIN_SCOPE
failed_gate_count: 0
blocked_gate_count: 0
harness_broken_count: 0
product_blocker_count: 0
```

## B4. Current P0 semantics

```text
max_cost_usd = 0
unknown/stale pricing = DENY
paid_fallback = false
free-by-name != pricing authority
privacy/data-class policy may deny even a free model
same-lineage sources cannot manufacture corroboration
confidence cannot override epistemic verdict
self-model maturity must derive from evidence, not class existence
protected invariants cannot be weakened by normal AutoFix/evolution
```

## B5. Next task

- Đồng bộ các thay đổi cuối cùng lên `main` để AI khác có thể kiểm tra.
- Xác nhận “26-P0 Foundation verified within P0 scope on SHA 8582a03147608442331967ef2b1d9c790e21695f.”
- Bắt đầu phase mới hoặc tiếp tục theo yêu cầu của user.

---

# C. Câu lệnh ngắn cho phiên mới

Người dùng chỉ cần nói:

> **“Đọc `GA.md` trên `main`, refresh GitHub live rồi tiếp tục SCP.”**

Agent phải tự dựng lại authority + current state theo file này, không yêu cầu người dùng kể lại lịch sử trừ khi nguồn hiện tại thực sự thiếu thông tin.
