# MC3 — Đóng Mạch 3 (OpenAI-compat & SWE-bench compat)

Date: 2026-09-11. Branch: `audit/runtime-guard-AUDIT-20260909`.
SHA pin: `3f29c180502fe71d92454f9ffcf699476a07f4ce` (commit fix M3).
Verdict: **CLOSED_WITH_KNOWN_GAP** — `reports/circuit-closures/M03-closure.json`.

## Tóm tắt công việc

1. **Baseline** (khớp `INVENTORY/M3.txt`): flow_03 = 7 failed / 21 passed; cộng
   1 failure `test_api_import_order_contract` thuộc M3 theo ghi chú M2 của ledger.
2. **Reality probe trước fix** (DNA #26): `M03-evidence/_probe_reality.py` +
   `_probe_failure_triggers.py` — quan sát thật: auth-first 401; malformed
   messages → 500 crash; judge REJECT_EMPTY → FAIL/KILL withheld; stream=true
   → JSON đơn; SWE-bench mount thật là `/swe-bench/v1`; không input thật nào
   chạm nhanh lỗi judge.
3. **Root-cause 8 test đỏ** (bảng đầy đủ trong `M03-closure.json → root_causes`):
   - HARNESS_BROKEN (6 test): patch thuộc tính không tồn tại (`LLMGateway`,
     `AgentOrchestrator`), phát minh contract (path top-level, 422-unauth,
     async pass-stub, instance_id-bắt-buộc). Sửa test: strictness CHỈ tăng,
     no-mock golden path (chạy RealityJudge thật), ERR-1 fault injection tại
     seam `get_judge` (lý do + probe bằng chứng ghi trong test docstring).
   - PRODUCT_FAIL (2 lớp): (a) `openai_compat.py` — bad JSON / malformed
     messages / judge exception đều thoát ra 500 không cấu trúc → fix fail-
     closed 400/503 OpenAI envelope + logger (fail-loud, không leak);
     (b) `v105_routes.py` thiếu import `Request` → `app.openapi()` crash
     PydanticUserError ở cả hai thứ tự import → fix 1 dòng import.
   - Stale pin: v104 count 23→24 (`/v104/learn/consolidate` thêm sau ngày pin)
     — cập nhật changelog guard, giữ exact-equality.
4. **D1** tại pin: flow_03 28/28 exit 0 (×2 lần); + import-order 29/29;
   regression flow_02 34/34.
5. **D2**: rebuild image với `SCP_GIT_SHA=<pin>` (EXIT=0), force-recreate,
   /health 200 + `commit == pin`, /readiness ready, RestartCount=0.
6. **D3**: 11 probe HTTP thật trên instance tạm full-profile (:8002, cùng image
   pin, JWT mint trong container, provider keys trung hòa, egress deny):
   401 auth-first / 400 envelope ×3 (fix mới được chứng minh runtime) / 200
   envelope + FAIL/KILL withheld / stream=true JSON đơn / models list /
   SWE-bench 200 + 422 + 404 top-level. Log container: 0 Traceback, 0 BYPASS.
   Teardown đầy đủ.
7. **D4–D7**: reference seal Mimosa `4a66b279…` HIGH=0 @`1f00d00` (patch M3
   chưa được scan lại — gap); D5 không có reviewer độc lập riêng cho M3
   (gap, same class M02); D6 AST: 0 silent-except trong code M3 authored,
   2 pre-existing có re-raise ngoài trong v105 (ghi ro); D7: 0 TODO,
   thiếu header WIRED/CLOSED + flow map stale + chưa có runbook (ghi ro).
8. **D8**: `M03-closure.json` + STATUS-LEDGER (dòng M3 → CLOSED_WITH_KNOWN_GAP)
   + progress log này. Commit docs sau pin (DEVIATION như M01/M02).

## Sự kiện concurrency (quan trọng — ghi để audit)

Trong phiên, một worker khác trên shared tree đã: stash toàn bộ WIP (kéo theo
thay đổi chưa commit của MC3) → checkout `feature/scp_v2_migration` → dọn các
artifact untracked. MC3 đã: `git stash apply` (giữ stash@{0} làm backup —
KHÔNG drop, WIP của worker khác vẫn trong đó) → commit scope files → commit
b809b0e lạc vào feature branch → cherry-pick về audit branch thành `3f29c18`
→ trả feature branch về `1fc58c7` (vị trí worker khác đặt). Evidence bị xóa
1 lần do cleanup — đã tái tạo và chạy lại D1 tại pin. Không dữ liệu của bên
khác bị drop/ghi đè.

## Giới hạn bằng chứng (đọc trước khi dùng)

- Endpoint là OpenAI-SHAPE compat + fail-closed; CHƯA chứng minh chat chất
  lượng thật với LLM thật (không answer source trên deployment pin).
- SSE chưa hỗ trợ; instance_id SWE-bench không persist; routes 404 trên
  deployment chính profile=core (chứng minh trên instance tạm full-profile).
- Không soak/chaos; không scan Mimosa lại sau pin; D5 không có review độc lập.
