# SCP Session Bootstrap — Hợp đồng khởi động phiên SCP

> **Mục đích:** bảo đảm mọi cuộc hội thoại/agent mới xử lý SCP theo cùng một hệ quy tắc mà không phụ thuộc vào chat history hoặc memory của một model.
>
> **Authority:** file này quy định *cách bắt đầu và cách làm việc*. Trạng thái công việc hiện tại nằm ở `docs/SCP_CURRENT_HANDOFF.md`.

## 1. Nguyên tắc authority

Thứ tự ưu tiên khi có mâu thuẫn:

1. Chỉ thị trực tiếp mới nhất của người dùng.
2. `AGENTS.md`.
3. `.agents/skills/scp-dna/SKILL.md` + `references/dna-principles.md`.
4. `spec/complete_scp_reference.yaml` và các protected invariants/bindings hiện hành.
5. Skill chuyên biệt phù hợp với task.
6. Live Git state + runtime/test/evidence trên đúng SHA.
7. `docs/SCP_CURRENT_HANDOFF.md` và task capsule.
8. Chat history / model memory chỉ là hỗ trợ continuity, **không phải source of truth**.

Nếu memory/chat mâu thuẫn với repo/evidence hiện tại, repo/evidence thắng.

## 2. Bootstrap bắt buộc cho mọi task SCP không tầm thường

Trước khi phân tích sâu, sửa code, audit, chạy test-verdict hoặc đưa ra release claim:

1. Đọc `AGENTS.md`.
2. Đọc `.agents/skills/scp-dna/SKILL.md`.
3. Đọc `.agents/skills/scp-dna/references/dna-principles.md` khi cần wording/invariant chính xác.
4. Đọc `spec/complete_scp_reference.yaml` khi task liên quan Complete SCP, maturity, P0/P1/P2, evidence/verdict/governance.
5. Đọc `.agents/skills/release-gate-skill-dna-bindings.json` nếu task là mandatory gate/audit/release/customer handoff.
6. Chọn **chỉ các Skill chuyên biệt liên quan** theo `AGENTS.md`; không nạp toàn bộ Skill pack nếu không cần.
7. Đọc `docs/SCP_CURRENT_HANDOFF.md`.
8. Refresh live branch/HEAD từ GitHub.
9. So sánh live HEAD với `work_snapshot_sha` trong handoff. Nếu khác, xem diff/commit mới trước khi dùng handoff làm trạng thái hiện tại.
10. Chỉ retrieve code/tests/evidence nằm trong dependency cone của task hiện tại; không đọc lại toàn repo mặc định.

## 3. Session Header — phải xác lập trước khi hành động

Trước mutation/substantial audit, agent phải tự xác định tối thiểu:

```text
SCP SESSION
branch: <live branch>
live_head: <live SHA>
work_snapshot_sha: <handoff SHA>
objective: <một mục tiêu chính>
loaded_authority:
  - AGENTS
  - SCP DNA
  - relevant Skill(s)
  - Complete SCP Reference (nếu liên quan)
known_blockers: <...>
evidence_target: A/B/C/D hoặc scope tương ứng
mutation_scope: <files/subsystems>
main_mutation: FORBIDDEN trừ khi user chỉ thị rõ
```

Không cần in toàn bộ header cho người dùng nếu không hữu ích, nhưng agent phải hành động theo nó.

## 4. Quy tắc một phiên / một mục tiêu

Mặc định:

> **Một task lớn = một cuộc hội thoại/agent session riêng = một decision boundary rõ ràng.**

Tiếp tục cùng session khi vẫn đang xử lý cùng root cause. Khi exit condition của task đã đạt hoặc task bị BLOCKED với evidence rõ ràng, tạo checkpoint/handoff rồi kết thúc session.

Không kéo thêm một task lớn không liên quan vào cùng context chỉ để giữ continuity.

## 5. Context discipline — giữ cốt lõi, giảm token

Không nén bằng cách bỏ bằng chứng. Nén bằng cách **địa chỉ hóa bằng chứng**:

- Stable invariants: tham chiếu file/hash, không paste lại mỗi vòng.
- SHA-bound state: dùng SHA + diff + affected dependency cone.
- Test/log lớn: lưu artifact/evidence; đưa vào context finding + vị trí/evidence ref, mở raw khi cần phản chứng.
- File không đổi và không nằm trong dependency cone: không đọc lại mặc định.
- Handoff/capsule phải ngắn, có thể truy ngược về source/evidence gốc.

Mục tiêu là giảm **frontier-model visible workload**, không làm mất provenance.

## 6. Invariant không được làm yếu

Mọi session phải giữ các nguyên tắc hiện hành trong `AGENTS.md` + SCP DNA, đặc biệt:

- `PASS != TRUE`.
- Reality có quyền cuối cùng.
- Consensus không đồng nghĩa truth; kiểm lineage/blind spot.
- Không delete/skip/xfail test để manufacture green.
- Không hạ assertion/coverage/security/mutation/acceptance threshold để làm xanh.
- Không đổi fail-closed thành fail-open ở authority/security/governance boundary.
- Fix product/config hoặc harness thực sự lỗi tại đúng điểm failure; harness fix phải giữ hoặc tăng strictness.
- External side effect không chắc chắn: reconcile trước, không blind retry.
- Change phải nhỏ, đảo ngược được, có Reality test và rollback phù hợp.
- Mandatory release/customer-handoff evidence phải bind đúng SHA + Skill/DNA contract.

## 7. Phân loại failure

Khi test đỏ, phân loại dựa trên evidence, không dựa trên mong muốn:

- `PRODUCT_FAIL`: production path tồn tại nhưng hành vi sai contract.
- `PRODUCT_BLOCKED`: capability/authority bắt buộc chưa tồn tại hoặc chưa đủ evidence để chạy contract.
- `HARNESS_BROKEN`: test/harness encode semantics đã bị supersede, fixture giả, hoặc bản thân harness vi phạm contract; sửa harness phải giữ/tăng strictness.
- `BLOCKED`: chưa đủ evidence/authority/runtime để phán quyết.

Không đổi nhãn chỉ để giảm blocker count.

## 8. Exact-SHA discipline

`docs/SCP_CURRENT_HANDOFF.md` là continuity metadata, **không phải release evidence authority**.

- `work_snapshot_sha` là SHA code/test mà handoff mô tả.
- Việc tạo/cập nhật handoff có thể tạo commit metadata mới; vì vậy session mới **luôn refresh live HEAD và diff**.
- Evidence của SHA X không được dùng để chứng minh SHA Y nếu gate yêu cầu same-SHA.
- Freeze/release manifest phải nằm ngoài cơ chế self-referential update hoặc được EvidenceAuthority bind đúng tested SHA.

## 9. Kết thúc session

Trước khi kết thúc một task lớn:

1. Refresh live branch/HEAD.
2. Ghi task outcome theo scope: PASS/BLOCKED/FAIL/HARNESS_BROKEN/PRODUCT_BLOCKED khi phù hợp.
3. Ghi tests/evidence đã thực sự chạy; không suy diễn.
4. Ghi files/commits thay đổi.
5. Ghi blockers/open questions còn lại.
6. Cập nhật `docs/SCP_CURRENT_HANDOFF.md` với **một next task cụ thể**.
7. Nếu cần chi tiết lớn, tạo task capsule riêng và chỉ link từ handoff.
8. **Không sửa file Bootstrap này** trừ khi chính luật làm việc/authority của SCP thay đổi.

## 10. Câu mở đầu chuẩn cho chat mới

Người dùng có thể chỉ cần nói:

> **Tiếp tục SCP theo `SCP_SESSION_BOOTSTRAP` + `SCP_CURRENT_HANDOFF` trong nguồn dự án. Refresh GitHub live trước khi làm.**

Agent phải tự dựng lại context theo các bước trên; không yêu cầu người dùng kể lại lịch sử nếu source có thể giải quyết.
