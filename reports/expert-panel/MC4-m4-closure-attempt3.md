# MC4 — Mạch 4 (Control & Hands) closure — attempt 3 — 2026-09-11

Branch: `audit/runtime-guard-AUDIT-20260909`. Base: `872067a`. Pin: `e13fad455afbfaa7b5e53ec677c1e9772eecc19d`.

## Tiền kết (kế thừa attempt 2)

Attempt 2 chết do provider error sau khi để lại 1 fix dở trong
`scp/hands/task_kernel_bridge.py` (~dòng 298): raise PermissionError khi
`capability_token` không parse được, TRƯỚC `registry.require` và trước mọi
kernel state mutation (FA-05, comment `[M4 FIX 2026-09-11]`).

**Verdict review: GIỮ.** Đúng nguyên nhân thật: trước fix, request mutating
KHÔNG token vẫn tạo task/lease/idempotency/checkpoint trước khi executor PEP
từ chối (kernel side effect trước authorization), và unknown action leak
KeyError thay vì contract authz. Fix làm xanh
`test_hands_executor_rejects_missing_token_fail_closed` (57/57 khi mới vào
phiên). Strictness tăng thêm assert FA-05.

## Root-cause 7 đỏ (INVENTORY/M4.txt) — 0 PRODUCT_FAIL trong số đỏ

| Test | Verdict | Root cause |
|---|---|---|
| pc_controller_execute_requires_token_and_capability | HARNESS_BROKEN | Authority dựng trên file state RỖNG (NamedTemporaryFile) → product fail-closed `state_corrupt` (đúng thiết kế, chống truncate-attack). Fix: fresh state path + isolated controller; pin whoami thật + tokenId/epoch. |
| pc_controller_kill_clear_requires_capability_token | HARNESS_BROKEN | Cùng root cause empty-state-file. Fix tương tự; pin kill_switch_engaged() trước/sau + body killSwitch=False. |
| control_capability_status_requires_admin | HARNESS_BROKEN | NameError `app` chưa từng được định nghĩa. Fix: FastAPI app + control_routes.router thật. |
| control_capability_escalate_requires_admin | HARNESS_BROKEN | Cùng NameError. Fix tương tự. |
| pc_controller_write_file_succeeds_with_valid_token | HARNESS_BROKEN | Giả định backup cho file MỚI; product chỉ backup khi overwrite (backupId=None là đúng). Fix: pin 2 pha create→update, backup byte-identical v1. |
| hands_executor_forwards_token_to_controller | HARNESS_BROKEN (2 lớp) | `pc.execute` CHU ĐỘCH không trong registry + patch nhầm controller (executor tự tạo controller riêng, authority repo data/hands revoked epoch 57). Fix: no-mock, token `hands:pc.write_file`, kernel path thật, pin tokenId echo + kernel COMPLETED. |
| hands_executor_rejects_missing_token_fail_closed | PRODUCT_FAIL (fix kế thừa) | Bridge mutation trước authorization. Fix attempt 2 GIỮ. |

Cộng thêm: **PLANNER-1** (test xanh MƠ HỒ — FA-01) de-vacuous: assertion `or`
luôn thoả + token inject vào bản copy public thay vì step input (journal là
source of truth). Fix: token nhúng tại create_plan, pin plan COMPLETED, 2 step
VERIFIED, file thật.

## PRODUCT_FAIL phát hiện thêm qua D3 runtime probe

`/v3/hands/execute` leak **HTTP 500** cho thiếu capability token sau khi bridge
raise PermissionError đúng FA-05 → fix `e13fad4`: map
PermissionError/InvalidTokenSignatureError → **403** (mirror
pc_controller_routes). Test HTTP-boundary mới `[HANDS-6]`.

## D0–D8 tóm tắt

- **D0** PASS — 3 file chạm: task_kernel_bridge.py, hands_routes.py, flow_04 test. Scope diff == pin (rỗng). 3 file WIP của stream khác KHÔNG bị chạm.
- **D1** PASS — flow_04 **58 passed exit 0** tại pin (verbose: `M04-evidence/D1-T04-pytest.txt`); repeat+regression 76 passed; regression `test_pc_controller_token_pep` + `test_api_token_boundary` **18 passed exit 0**. Suite mock-free (xoá unittest.mock imports). Không skip/xfail.
- **D2** PASS — build `SCP_GIT_SHA=e13fad4…` EXIT=0 (lần 1 fail TRANSIENT TLS timeout tới auth.docker.io — retry 1 lần OK, không phải product defect); recreate; /health 200 commit==pin; /readiness ready; RestartCount=0; image sha256:0f8246a4…
- **D3** PASS_WITH_LIMITS — instance tạm full-profile :8003 cùng image pin, token mint trong container (T04 pattern): **13/13 PASS** — 6 negative (no/wrong token → 403 token-only fail-closed), P4/P5 (PEP 403 CapabilityRequiredError), P6 (PEP pass-through tokenId echo; lệnh thật platform-limit trong Linux container — execution thật chứng minh D1 Windows), P7 golden path 200 + kernel COMPLETED, P8 health commit==pin. Log scan 0 Traceback / 0 BYPASS; teardown xong.
- **D4** PASS_WITH_LIMITS — reference seal S6b `4a66b279…` HIGH=0 @1f00d00; patch M4 không tạo sink mới; chưa deep-scan lại (gap).
- **D5** PASS_WITH_LIMITS — Agent V SWEEP_APPROVED là moc chuoi khác; không có reviewer độc lập riêng cho M4 (gap cùng loại M02/M03).
- **D6** PASS_WITH_LIMITS — 6 except:pass-without-log PRE-EXISTING có chủ đích (cleanup guards + heartbeat control-flow), 0 do patch M4 tạo ra; runtime 0 Traceback.
- **D7** PASS_WITH_LIMITS — 0 TODO/FIXME/XXX/HACK trên 15 file scope; thiếu header WIRED/CLOSED, flow-map M4 stale, chưa có runbook (gap ghi rõ).
- **D8** PASS — `M04-closure.json` (JSON validated) + STATUS-LEDGER M4 + progress log này.

## Probe-harness notes (trung thực)

1. Git Bash MSYS path conversion làm hỏng env container (2 lần fail) → MSYS_NO_PATHCONV=1.
2. Container default USER 10001 không ghi được anonymous volume (root-owned) → probe container chạy `--user 0` (production giữ USER 10001 + host-bind; không đổi artifact nào).
3. Thiếu SCP_HOST=0.0.0.0 → uvicorn bind loopback trong container → không probe được từ host.
4. P7 lần đầu gửi token qua header; hands_routes đọc `payload.capabilityToken` từ BODY (product đúng — hai route hai contract) → probe sửa, chạy lại toàn bộ 13/13.

## Guard & discipline

- Branch guard: `git branch --show-current` kiểm tra đầu phiên + trước mỗi commit — đúng `audit/runtime-guard-AUDIT-20260909` cả 3 lần.
- `git add` đường dẫn cụ thể; không đụng 3 file WIP (test_test_infrastructure_fail_closed, test_flow_11, test_security_sweep_s6); không stash; không in secret (token chỉ qua env; evidence chỉ ghi prefix 8 ký tự + "<redacted>").
- Pre-commit hook (t00_meta_audit) qua sạch cả 2 commit, không cần de-shape.

## Commits

1. `0d13c85` fix(M4): close Control & Hands circuit — capability PEP + hands bridge fail-closed ordering (product bridge + 6 test rewrite + PLANNER-1)
2. `e13fad4` fix(M4): map hands bridge PEP rejection to HTTP 403 (fail-closed boundary) — **sha_pin**
3. (commit docs này) docs(M4): pin circuit closure record M4

## Kết luận

M4 **CLOSED_WITH_KNOWN_GAP** tại pin `e13fad4…`. Verdict bị giới hạn bởi scope:
không tuyên bố production-ready, không tuyên bố command execution chạy trong
container Linux, không tuyên bố hệ thống secure. Hồi quy: commit sau chạm scope
M4 phải chạy lại D1 + D2 + D4.
