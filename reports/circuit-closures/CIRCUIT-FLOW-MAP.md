# SCP Circuit Flow Map — 14 mạch đóng theo hợp đồng D0–D8

> Authority: hợp đồng đóng mạch D0–D8 (phụ lục 14 mạch). File này là **bản đồ wiring**:
> mỗi mạch ↔ suite test chính ↔ runtime probe ↔ trạng thái đóng.
>
> Quy tắc trạng thái (không được nới):
> - `CLOSED` chỉ khi có đủ D0–D7 trên **cùng một SHA pin** + closure record trong `reports/circuit-closures/`.
> - `CLOSED_WITH_KNOWN_GAP` = hợp lệ nhưng có ít nhất một mục mang `EVIDENCE_GAP` đã ghi rõ trong closure record. **Không** được đọc thành "đã xong hoàn hảo".
> - `NOT_VERIFIED` = chưa có bằng chứng runtime trên SHA pin. **Không** đồng nghĩa "hỏng", và **không** được đọc thành "đã xong".
> - `D1_PASS__NOT_CLOSED` = suite chính xanh nhưng **CHƯA** có pin/runtime/closure. **KHÔNG** được đọc là "xong".
> - `D1_FAIL` = suite chính đỏ (exit ≠ 0). Mạch chắc chắn chưa thể đóng.
> - `EVIDENCE_GAP` = đã chạy nhưng thiếu/không hợp lệ một mục bắt buộc.
>
> M1 hiện chỉ đạt `CLOSED_WITH_KNOWN_GAP` vì D4 (ratchet scan) là `EVIDENCE_GAP`: hook ledger báo
> `runStatus=inconclusive`, `scanned_files=0`, 6/6 file phạm vi `scanner_failed`. Bản deep scan có seal
> (phủ 1360/1360 file, 0 finding trong 6 file phạm vi M1) là bằng chứng bổ trợ, **không** nâng D4 thành PASS
> vì chính scan đó có `runStatus=inconclusive` / `completeness=partial`.

Bảng dưới là trạng thái tại lần cập nhật gần nhất (**2026-09-12, DNA-2** — đồng bộ theo `STATUS-LEDGER.md` + 14 closure record); luôn đối chiếu lại với closure record thật trong `reports/circuit-closures/` thay vì tin bảng này.

| Mạch | Tên | Suite chính | Runtime probe | Trạng thái |
|---|---|---|---|---|
| M1 | Boot & Background | `tests/T01_boot/` | **đã** — /health commit==pin `7650753…`, /readiness ready, watchdog `first execution completed` | **CLOSED_WITH_KNOWN_GAP** (`M01-closure.json`, pin `7650753…`; D4 = EVIDENCE_GAP) |
| M2 | Ask & Chat | `tests/T02_contract/test_flow_02_ask_chat_scp_standard.py` | **đã** — 34 passed tại pin `1f00d00…`; /health + /readiness + WS/idempotency probes trên instance standard tạm | **CLOSED_WITH_KNOWN_GAP** (`M02-closure.json`, pin `1f00d00…`; D3–D7 = PASS_WITH_LIMITS) |
| M3 | OpenAI-compat | `tests/T02_contract/test_flow_03_openai_compat_scp_standard.py` (+ import-order) | **đã** — 28 passed tại pin `3f29c18…`; 11 probe HTTP thật trên instance tạm full-profile (401/400/withheld) | **CLOSED_WITH_KNOWN_GAP** (`M03-closure.json`, pin `3f29c18…`; D4–D7 = PASS_WITH_LIMITS) |
| M4 | Control & Hands | `tests/T03_capability/test_flow_04_control_hands_scp_standard.py` | **đã** — 58 passed tại pin `e13fad4…`; 13/13 probe (6 token-only 403 + 2 PEP 403 + golden hands/execute COMPLETED) | **CLOSED_WITH_KNOWN_GAP** (`M04-closure.json`, pin `e13fad4…`; D3–D7 = PASS_WITH_LIMITS) |
| M5 | Agent/Call | `tests/T03_capability/test_flow_05_agent_call_scp_standard.py` | **đã** — 35 passed tại pin `6cdb424…`; 8/8 probe (401/403 + golden status/plan/sessions/dry-run) | **CLOSED_WITH_KNOWN_GAP** (`M05-closure.json`, pin `6cdb424…`; D4–D7 = PASS_WITH_LIMITS) |
| M6 | Prediction | `tests/T03_capability/test_flow_06_prediction_scp_standard.py` | **đã** — 23 passed tại pin `75e994f…`; 14/14 probe (401, 429 lockout, golden run-cycle + /verify) | **CLOSED_WITH_KNOWN_GAP** (`M06-closure.json`, pin `75e994f…`; D3/D4/D5/D7 = PASS_WITH_LIMITS) |
| M7 | AutoFix & Policy | `tests/T03_capability/test_flow_07_autofix_scp_standard.py` | **đã** — 43 passed tại pin `554f43e…`; 8/8 probe (401 + golden stats/permissions/attack-mode/run-audit observe) | **CLOSED_WITH_KNOWN_GAP** (`M07-closure.json`, pin `554f43e…`; D4–D7 = PASS_WITH_LIMITS) |
| M8 | Audit/Benchmark | `tests/T03_capability/test_flow_08_audit_benchmark_scp_standard.py` | **đã** — 25 passed tại pin `c0f5f6f…`; 9/9 probe (401/403 + batch benchmark thật + SSRF 400 fail-closed) | **CLOSED_WITH_KNOWN_GAP** (`M08-closure.json`, pin `c0f5f6f…`; D4/D5/D7 = PASS_WITH_LIMITS) |
| M9 | Threat & Counter | `tests/T03_capability/test_flow_09_threat_analysis_scp_standard.py` | **đã** — 23 passed tại pin `b4134ac…`; 8/8 probe (401 auth-first + golden admin stats/ledger) | **CLOSED_WITH_KNOWN_GAP** (`M09-closure.json`, pin `b4134ac…`; D4/D5/D7 = PASS_WITH_LIMITS) |
| M10 | Streaming | `tests/T03_capability/test_flow_10_streaming_scp_standard.py` | **đã** — 12 passed tại pin `1691f7f…`; 12/12 probe ×2 lần độc lập (401, 429, SSE thật 6 frame) | **CLOSED_WITH_KNOWN_GAP** (`M10-closure.json`, pin `1691f7f…`; D3/D4/D5/D7 = PASS_WITH_LIMITS) |
| M11 | Admin/Import | `tests/T03_capability/test_flow_11_admin_import_scp_standard.py` | **đã** — 35 passed ×2 tại pin `4f5e1bf…` rồi `8fc3560…`; 8/8 probe (401 + judge thật UNKNOWN/ESCALATE) | **CLOSED_WITH_KNOWN_GAP** (`M11-closure.json`, pin `8fc3560…`; D4/D5/D7 = PASS_WITH_LIMITS) |
| M12 | Background WHY | `tests/T03_capability/test_flow_12_background_why_scp_standard.py` | **đã** — 27 passed tại pin `fa9da62…`; probe deployment chính (doubt_ledger, why_gate_audit, WHY-VERIFY cycle 180s) | **CLOSED_WITH_KNOWN_GAP** (`M12-closure.json`, pin `fa9da62…`; D3/D4/D5 = PASS_WITH_LIMITS). **DNA-2 2026-09-12:** multi-source empty-evidence fix (DNA #22) — 29 passed @`4f451df` |
| M13 | Data sources & Learning | `tests/T03_capability/test_flow_13_free_api_learning_scp_standard.py` | **đã** — 28 passed tại pin `76b7624…`; P1–P6 probe (consolidate 200, top-systems fetch GitHub/Wikipedia thật) | **CLOSED_WITH_KNOWN_GAP** (`M13-closure.json`, pin `76b7624…`; D4/D5 = PASS_WITH_LIMITS) |
| M14 | v106 Audit/Self-model | `tests/T03_capability/test_flow_17_self_model_capability_scp_standard.py` + `tests/T11_release/` | **đã** — 3 passed (flow_17) + 69 passed (T11) tại pin `cf34778…`; 7/7 probe (401 sau fix BFLA) | **CLOSED_WITH_KNOWN_GAP** (`M14-closure.json`, pin `cf34778…`; D4/D5 = PASS_WITH_LIMITS) |

Chi tiết đầy đủ (danh sách test FAILED, việc còn lại cho từng mạch, thứ tự đề xuất, giới hạn bằng chứng): `reports/circuit-closures/STATUS-LEDGER.md`.

> ⚠️ Bảng trên đồng bộ trạng thái **từ 14 closure record** (mỗi mạch `CLOSED_WITH_KNOWN_GAP` tại SHA pin riêng). KHÔNG mạch nào được đọc thành `CLOSED` sạch; mọi mạch còn known_gaps đã ghi trong closure record tương ứng (đọc trước khi dùng lại kết quả). **Suite xanh ≠ mạch đóng; phải có D0–D8.**
>
> **Cập nhật 2026-09-12 (DNA-2):** (1) refresh bảng theo STATUS-LEDGER + closure records; (2) M12: multi-source empty-evidence fix (DNA #22, commit `4f451df`) — nhánh multi-source của `why_execute_plan.py` không còn auto-PASS với `ai_answer=''`, test pin đổi từ PASS → UNKNOWN + `empty_evidence` (strictness TĂNG) kèm control PASS cho match thật; flow_12 = 29 passed @`4f451df`; (3) D7: header `# SCP CIRCUIT: MXX — STATUS: CLOSED_WITH_KNOWN_GAP` đã thêm vào 69 file scope .py của M02–M14 (commit `514f1c9`) — commit này CHẠM file phạm vi của các mạch nên theo regression clause phải chạy lại tối thiểu D1+D2+D4 cho từng mạch: D1 của M12+M02 đã chạy lại (63 passed, exit 0); D2/D4 còn nợ owner. Header của 4 module M1 giữ nguyên (đã có từ M01, để tránh vô hiệu hoá pin 7650753 thêm lần nữa — reviewer_limits L5).

## Các track adoption ngoài 14 mạch (Track C1–C3, ADOPT-AND-FIX)

Ba track dưới đây **không thuộc** hợp đồng D0–D8 của 14 mạch M1–M14; chúng có
trạng thái riêng ghi tại `STATUS-LEDGER.md`. **Không** đọc các hàng này thành
`CLOSED` — đây là adoption track (infra/mở rộng năng lượng), không phải mạch
sản phẩm đóng theo D0–D8.

| Track | Tên | Suite chính | Runtime probe | Trạng thái |
|---|---|---|---|---|
| Track C1 | PostgreSQL KernelStorage (kernel storage thay SQLite) | `tests/T04_kernel/test_pg_storage_parity.py` + `test_pg_migration.py` + `test_pg_storage_chaos.py` + `test_pg_boot_runtime.py` (cần `SCP_PG_TEST_DSN` = docker PG thật; thiếu env = declared infra-skip) | **đã** — PG thật docker postgres:16-alpine: chaos injection (`pg_terminate_backend`), docker restart giữa claim, 2-process claim race, `pg_dump` → restore → verify, boot lifecycle qua TaskKernel API thật | **CLOSED_WITH_KNOWN_GAP** (`C1-postgres-closure.json`, sha_pin `72da6d3…`; performance/multi-node/HA chưa đo — đọc known_gaps) |
| Track C2 | PgEventBus: bảng `scp_events` durable + NOTIFY wake-up (NOTIFY chỉ là chuông, không phải queue) | `tests/T04_kernel/test_pg_event_bus.py` (cần `SCP_PG_TEST_DSN`; test factory opt-in chạy không cần PG) | **đã** — 9/9 ×2 lần chạy độc lập trên PG thật, trong đó replay sau listener chết đủ 5/5 đúng thứ tự (NOTIFY mất không mất event) | **CLOSED_WITH_KNOWN_GAP** (`C2-eventbus-closure.json`, sha_pin `5b4a6da…`; CHƯA wire vào kernel events thực — chỉ infra + API opt-in) |
| Track C3 | SandboxEvaluator: autofix không tự chấm bài — pytest thật trên bản sao workspace temp, fail-closed (wire opt-in `SCP_SANDBOX_EVALUATOR=1`) | `tests/T04_kernel/test_sandbox_evaluator_e2e.py` (NO-MOCK, subprocess pytest thật; 1 case PG-gated) | **đã (một phần)** — E2E 18 passed + 1 PG-gated PASSED trên PG thật; event-path smoke (publish `EVAL_REQUEST` → durable → replay → evaluate → `EVAL_RESULT`) + loop fail-closed exit 2; container compose `sandbox-evaluator` chưa có probe runtime riêng | **PASS_WITHIN_SCOPE** (pin tại commit `45a7dc8`; record = `reports/expert-panel/C3-sandbox-evaluator.md` — **evidence report, không phải closure JSON chuẩn**, vì C3 là adoption track ngoài hợp đồng D0–D8; KHÔNG đọc thành CLOSED) |

Chi tiết đầy đủ từng track: `STATUS-LEDGER.md` (bảng trạng thái, các hàng
Track C1/C2/C3) + record tương ứng.

## Ghi chú về cột "Suite chính"

- Đường dẫn ở cột Suite chính là **tên file đang tồn tại trên đĩa** tại thời điểm lập bản đồ (kiểm bằng `ls`), không phải bằng chứng các test đó đã PASS.
- Tồn tại test ≠ Reality proof (GA.md § A5). Với M2–M14, `D1_PASS__NOT_CLOSED` chỉ nghĩa là suite đã chạy và **không đỏ** trong lần inventory trên working tree; nó **không** có nghĩa đã pin SHA, đã có runtime proof, hay đã đóng mạch.
- Riêng M1: suite `tests/T01_boot/` đã chạy thật, kết quả và SHA nằm trong `M01-evidence/` + `M01-closure.json`.

## Runtime probe M1 — hợp đồng tối thiểu

| Probe | Kỳ vọng | Bằng chứng |
|---|---|---|
| `GET /health` | HTTP 200, `service_identity.commit == SCP_GIT_SHA` đã pin lúc build | `M01-evidence/D2-docker.txt` |
| `GET /readiness` | HTTP 200, `{"status":"ready","checks":{"judge":"ok","background_scheduler":"ok"}}` | `M01-evidence/D2-docker.txt` |
| container log | `[MACH1-FIX-1] ... (5 jobs: ...)`, `[MACH1-FIX-2]`, `[RESTORED-SYSTEMS] RetryPolicy background thread started`, `first execution completed` | `M01-evidence/D2-docker.txt` |

Cách chạy lại: `reports/circuit-closures/M01-runbook.md`.
