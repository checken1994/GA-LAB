# MC6 — M6 (Prediction) closure progress log

Date: 2026-09-11. Branch: `audit/runtime-guard-AUDIT-20260909`. Worker: MC6.
Session start HEAD: `9c7f186` (M4 pin commit). Guard `git branch --show-current`
checked at session start and before every commit: OK throughout.

## Baseline

- `INVENTORY/M6.txt`: 6 failed / 12 passed (exit 1). Cả 6 đỏ cùng triệu chứng
  **404**: `test_prediction_{run_cycle,pending,all,verify,stats}_requires_admin`
  + `test_prediction_run_cycle_executes_v5_pipeline`.
- Quan sát quan trọng: cả 12 "passed" đều là test `pass` TRẮNG (5 PRED-7..11 +
  7 causal pointer) → baseline xanh của M6 là xanh ảo hoàn toàn.

## Root-cause (đầy đủ trong `M06-closure.json` → `root_causes`)

| # | Phân loại | Nội dung |
|---|---|---|
| RC-1 | HARNESS | 5 test đánh top-level `/run-cycle`... nhưng router đăng ký prefix `/v105/predictions` (đã xác minh bằng route list thật của app) |
| RC-2 | HARNESS | PRED-6 mock chính route handler (FastAPI bỏ qua) + assert response shape `{success,cycle_id}` mà product không bao giờ trả |
| RC-3 | PRODUCT | `_get_engine()` đọc `api_server._predictive_engine` — global không bao giờ được gán (singleton thật nằm ở `helpers.get_judge()`) → 503 vĩnh viễn trên mọi endpoint |
| RC-4 | PRODUCT | `/verify` luôn 500: route truyền `limit` nhưng `Verifier.verify_pending()` không nhận |
| RC-5 | PRODUCT | KhamPha `spec["ai_answer"]` KeyError (generator V90 chỉ trả `{question,domain}`) nuốt cả block → offline không sinh prediction |
| RC-6 | PRODUCT + audit cũ "Lock DB" | `entity` bị nhận nhưng không INSERT (mất dữ liệu im lặng) + table cũ thiếu cột. SQLite handling kiểm tra: WAL + busy_timeout 30s + RLock; PRED-7 8-thread×4 ghi thật không mất row; probe runtime 0 "database is locked" → nghi vấn **không được xác nhận** trong phạm vi |
| RC-7 | PRODUCT | `SelfLearner` fallback `SCPV13()` (shim SCPV14) không có `.classifier` → Learn phase là no-op im lặng |
| RC-8 | HARNESS truth fixes | PRED-9 đổi tên (generate không dùng LLM gateway), pin dedup similarity thật, sửa nhãn over/under_predicted, de-vacuous 12 test trắng |

## Fixes (commit pin `75e994ff576faee5080aec3f541aa422b7d4ad0a`)

- `scp/api/routes/prediction_routes.py`: `_get_engine()` đọc singleton canonical
  từ `api_server_parts.helpers` (getattr tại call time) + docstring sửa claim sai.
- `scp/prediction/predictive.py`: `Verifier.verify_pending(limit)`; INSERT entity
  + migration cộng sung; KhamPha skip per-spec có WARNING; `SelfLearner._get_engine()`
  back bằng `RealityClassifier` thật.
- `tests/T03_capability/test_flow_06_prediction_scp_standard.py`: viết lại toàn
  bộ — path thật, admin auth thật (SCP_AUTH_TOKEN_SECRET + Bearer, pattern T02),
  autouse rate-limit accounting clear (chỉ accounting), crawl-thread suppression
  (pattern T02, có lý do), golden path không mock, seed/cleanup row có marker,
  22 test thật (0 skip/xfail, 0 mock golden path).

## Kết quả D1–D8

- D1: 23/23 passed exit 0 tại pin (22 flow_06 + 1 test_subsystem_prediction);
  chạy 3 lần deterministic. Evidence: `M06-evidence/D1-T06-pytest.txt`.
- D2: build `SCP_GIT_SHA=<pin>` EXIT=0 lần 1; image
  `sha256:70dce4ef…`; force-recreate main; /health 200 + commit == pin;
  /readiness ready. Evidence: `D2-docker.txt`, `D2-docker-build.txt`.
- D3: 14/14 probe trên `scp-m6-probe` :8004 (full-profile, egress deny, token
  probe per-session không in): 5×401 negative; 429 lockout adversarial (designed,
  tự hồi phục ~65s); run-cycle 200 golden path; /verify 200 (trước fix 500);
  422 schema; 2 run-cycle liên tiếp + 5 parallel probe 200 hết; log scan:
  0 locked / 0 Traceback / 0 bypass. Teardown xong. Evidence: `D3-m6-runtime.json`,
  `D3-runtime-setup.txt`.
- D4: PASS_WITH_LIMITS — reference seal `4a66b279…` (HIGH=0 @1f00d00), diff M6
  chưa deep scan riêng (gap ghi rõ, cùng posture M2/M3/M4).
- D5: PASS_WITH_LIMITS — Agent V (1f00d00) không phủ diff M6; không reviewer
  artifact độc lập cho M6 (gap ghi rõ).
- D6: PASS — 0 `except:pass` trong scope (AST scan, 18 handler có xử lý quan
  sát được). Evidence: `D6-ast-scan.txt`.
- D7: PASS_WITH_LIMITS — 0 TODO dangling; thiếu header STATUS + runbook riêng
  (gap ghi rõ). Evidence: `D7-todo-scan.txt`.
- D8: `M06-closure.json` (CLOSED_WITH_KNOWN_GAP, falsification_status =
  PARTIALLY_FALSIFIED_AT_PIN) + STATUS-LEDGER M6 cập nhật + file này.

## Guard compliance

- Nhánh đúng tại mọi điểm kiểm; commit chỉ `git add` 3 đường dẫn cụ thể.
- 3 file WIP của stream khác (test_test_infrastructure_fail_closed,
  test_flow_11, test_security_sweep_s6) không bị chạm, không stash.
- Không in secret: token probe random per-session không in/persist (xóa sau
  teardown); không đọc/in giá trị `.env`.
- Container probe đã teardown; main deployment chạy tại pin (health 200 sau
  teardown).

## Còn lại (known gaps — tường minh trong closure record)

G1 crawl internet thật chưa chứng minh (egress deny by design); G2 seal là
snapshot @1f00d00; G3 chưa có review độc lập riêng cho diff M6; G4 KhamPha vẫn
chưa sinh ai_answer (feature work); G5 write-concurrency qua HTTP không gọi được
(không có endpoint tạo prediction); G6 Learn production-judge path dead; G7
thiếu header/runbook; G8 reality_4-a-003 fail ở threat_routes (M9, pre-existing);
G9 503 fail-closed cho tới judge ready (contract có ý).
