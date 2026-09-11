# MC-GREEN-3 — M14 v106 Audit/Self-model (closure, resume)

- Ngày: 2026-09-11 (session resume, chạy liền sau M13 trong cùng session)
- Nhánh: `audit/runtime-guard-AUDIT-20260909`; pin: `cf34778` (sau fix(M13) `76b7624` + docs(M13) `8d42593`)
- Skills bắt buộc: scp-dna + scp-runtime-audit + scp-reality-verifier + scp-release-evidence-gate (SHA256 trong `M14-closure.json`)

## Phát hiện lớn

1. **PRODUCT_FAIL — cả 2 endpoint v106 mở hoàn toàn (BFLA)**: `/v106/audit/reports` và `/v106/capabilities/{cap_id}` không có `verify_admin`, probe-proven trả **200 không cần token** tại runtime pin trước fix (V1/V2 trong `M13-evidence/D3-m13-probe2.txt`). Lộ danh sách audit report và self-model capability matrix; GET còn tự tạo dir/sqlite trong container.
2. **Harness flow_17 pin contract không an toàn**: 1 test duy nhất gọi endpoint mở và assert 200 — đúng kiểu "harness vuông contract cũ" như M10/M11. Đã de-vacuous theo FA-01: golden qua admin override + 2 negative pin 401 mới (1 → 3 tests, exit 0).
3. **"Audit Engine" là report-listing stub**: route chỉ list tên file trong `scp/audit_r8`, `scp/audit_r9`; thư mục `scp/audit_engine/` không còn file source nào trong git (chỉ `__pycache__` stale của `contract_adapter/gate/models/oracle` từ 4772cbd) — response "Audit engine active" quá lạc quan.
4. **Capability maturity chỉ là static recompute**: `STATIC_PRESENT/DECLARED` từ spec/binding, `tested_sha="HEAD"` hard-code, `last_runtime_verified_at=null` — chưa nối evidence runtime thật (A–D).

## Fix & bằng chứng

- Fix `cf34778`: thêm `dependencies=[Depends(verify_admin)]` vào cả 2 route v106; flow_17 de-vacuous.
- D1: flow_17 **3/3 exit 0** + T11_release **69/69 exit 0** (khớp baseline 69P).
- D2: build `--build-arg SCP_GIT_SHA=cf34778…` EXIT=0; probe container ephemeral full-profile :8012; `/health` 200 `service_identity.commit` == pin.
- D3 (7/7): no-auth → 401 cả 2 endpoint; admin → 200 audit reports thật + capability matrix thật (`self.capability_map` M2, `execution.task_kernel` M1); unknown id → graceful UNKNOWN/M0; M13 consolidate regression vẫn 200.

## Kết luận

`CLOSED_WITH_KNOWN_GAP` tại pin `cf34778` — chi tiết D0–D8, root cause, known_gaps (G1–G8), falsification_status: `M14-closure.json`. Không đọc thành "audit engine hoạt động đầy đủ" (G1/G2).
