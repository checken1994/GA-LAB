# SCP Current Handoff — Trạng thái bàn giao hiện tại

> **Đọc cùng:** `docs/SCP_SESSION_BOOTSTRAP.md`.
>
> File này là continuity metadata để phiên mới dựng lại trạng thái nhanh. Nó **không phải** release evidence authority và không thay thế live Git/test/Reality evidence.

## 1. Project identity

| Trường | Giá trị |
|---|---|
| Project | SCP / GA-LAB |
| Repository | `checken1994/GA-LAB` |
| Development branch | `26-p0-foundation-06-14` |
| Main policy | `main` không được mutation/merge trừ khi người dùng chỉ thị rõ và release rules cho phép |
| Current phase | `26-P0 Foundation` |
| Complete SCP reference | `spec/complete_scp_reference.yaml` |

## 2. Snapshot được handoff mô tả

```text
work_snapshot_sha = 4177cee7aa1ec9069a49b3380acc082c465fe75d
```

Đây là SHA code/test gần nhất mà trạng thái kỹ thuật dưới đây dựa vào. Sau SHA này đã có commit tài liệu Bootstrap (`128b5e943376c2471a6535741f236716315e1434`) và chính việc cập nhật handoff cũng tạo commit metadata mới.

**Bắt buộc ở phiên mới:** refresh live branch HEAD và compare/diff với `work_snapshot_sha` trước khi tiếp tục. Không giả định live HEAD vẫn bằng SHA trên.

## 3. Trạng thái kỹ thuật đã ghi nhận tại `work_snapshot_sha`

Nguồn: commit message của `4177cee7...`; đây là **last-recorded state**, không phải một test run mới trong lúc tạo handoff.

```text
P0-06 Source Identity              IMPLEMENTED / UNVERIFIED STRICT
P0-07 Lineage                      IMPLEMENTED / UNVERIFIED STRICT
P0-08 Prediction Ledger            IMPLEMENTED
P0-09 Calibration                  IMPLEMENTED
P0-10 Self-Model                   IMPLEMENTED
P0-11 Drift Guard                  IMPLEMENTED + evolution path integration
P0-12 Privacy/Retention            IMPLEMENTED (major P0 scope)
P0-13 Z0/Z1                        IMPLEMENTED (major path)
P0-14 Z2/Z3                        IMPLEMENTED (canonical Python gateway)
P0-14 Z4 bridge hardening          COMPLETED at recorded snapshot
Vertical Slice A/B                 NOT YET COMPLETED
P0 freeze/full strict checkpoint   NOT YET RUN
Merge to main                      NOT DONE
```

Last recorded focused branch result:

```text
256 passed / 10 failed
```

Failure classification recorded at that snapshot:

```text
7 x T05 = HARNESS_BROKEN
    legacy/superseded paid-primary routing semantics
    must be rewritten to VERIFIED-FREE-ONLY semantics
    deletion/skip/xfail forbidden

3 x PRODUCT_BLOCKED
    T07  missing-piece / EpistemicBoundary
    T09B verified durable commit leg
    T11  EvidenceAuthority
```

## 4. Non-negotiable P0 semantics

Các session tiếp theo phải giữ ít nhất:

```text
Reality > Model
PASS != TRUE
UNKNOWN != VERIFIED
independent lineage required
UNKNOWN_INDEPENDENCE does not count as independent support
max_cost_usd = 0
unknown/stale pricing = DENY
paid_fallback = false
free-by-name is not pricing authority
privacy/data-class policy can deny even a free model
same-SHA evidence for mandatory verification/release claims
no test weakening / skip / xfail / threshold reduction
```

## 5. Next task — decision boundary tiếp theo

### Task 1: Rewrite 7 T05 → `VERIFIED-FREE-ONLY`

Mục tiêu:

```text
verified-free candidate A
    ↓ fail/429/timeout/invalid as relevant
verified-free candidate B
    ↓
verified-free candidate C
    ↓ exhausted
WAIT / BLOCKED

paid / unknown / stale-price candidate
    → no outbound authorization
    → no paid fallback
```

Giữ nguyên coverage của failure dimensions như timeout, 429, circuit breaker, provider failover, config attacks và privacy-safe fallback. Chỉ thay semantics cũ `paid-primary → free fallback` bằng `verified-free-only failover`.

Exit condition tối thiểu:

- 7 T05 harness failures được rewrite, không delete/skip/xfail.
- Focused T05 hermetic tests PASS.
- Có assertion machine-checkable rằng paid/unknown/stale candidate không tạo outbound inference request.
- Không tạo regression vào existing zero-cost/privacy/egress guards.
- Cập nhật handoff với SHA và evidence thực tế sau task.

## 6. Sau Task 1 — thứ tự đã thiết kế

```text
1. Rewrite 7 T05 → VERIFIED-FREE-ONLY
2. Vertical Slice A — epistemic foundation
   - Evidence / SourceIdentity / Lineage
   - Reality contradiction → EpistemicBoundary / MissingPieceFinding
   - EvidenceAuthority same-SHA binding
   - mục tiêu đóng T07 + T11 blocker
3. Vertical Slice B — governance/$0/evolution commit leg
   - ZeroCost + Privacy + DriftGuard
   - real reality-test commit/rollback path
   - mục tiêu đóng T09B blocker
4. T00 whole-branch meta-audit
5. Chỉ khi known PRODUCT_BLOCKED=0, HARNESS_BROKEN=0 và T00 PASS:
   freeze SHA X
6. T00–T11 full strict + compile/import + security + mutation + acceptance + Reality + dashboard/build + reproducibility
7. Manifest/EvidenceAuthority xác nhận toàn bộ mandatory evidence thuộc đúng X
8. Chỉ khi blocker_count=0:
   "26-P0 Foundation verified within P0 scope on SHA X."
```

Không đổi verdict trên thành `Complete SCP DONE`.

## 7. Failure-handling contract

Khi task/test đỏ:

- `PRODUCT_FAIL`: production behavior tồn tại nhưng sai contract → sửa production tại failure point.
- `PRODUCT_BLOCKED`: required production authority/capability/evidence chưa tồn tại → xây capability thật, không stub để làm xanh.
- `HARNESS_BROKEN`: harness encode semantics superseded hoặc fixture giả → sửa harness nhưng giữ/tăng strictness.
- `BLOCKED`: evidence/runtime chưa đủ để kết luận.

Mọi fix phải nhỏ, có rollback phù hợp và Reality test. Không manufacture green.

## 8. End-of-session update checklist

Trước khi đóng một chat/task lớn, cập nhật file này với:

```text
live branch
work_snapshot_sha mới của code/test được bàn giao
task vừa hoàn thành hoặc bị blocked
files/commits thay đổi
tests/evidence thực sự đã chạy
failure classification còn lại
open questions / limitations
một next task duy nhất
```

Nếu evidence/log quá lớn, tạo task capsule riêng dưới `reports/handoffs/` hoặc vị trí phù hợp rồi link/reference từ đây; không paste toàn bộ raw log vào handoff.

**Không cập nhật `SCP_SESSION_BOOTSTRAP.md` mỗi phiên.** Chỉ sửa Bootstrap khi authority/quy trình làm việc chung của SCP thực sự thay đổi.

## 9. Câu dùng để mở chat mới

> **Tiếp tục SCP theo `SCP_SESSION_BOOTSTRAP` + `SCP_CURRENT_HANDOFF` trong nguồn dự án. Refresh GitHub live trước khi làm.**
