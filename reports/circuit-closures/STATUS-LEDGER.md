# SỔ TRẠNG THÁI MẠCH (STATUS-LEDGER) — M1→M14

> Authority: `CLOSURE-CONTRACT.md` (D0–D8) + `CIRCUIT-FLOW-MAP.md` (bản đồ wiring).
> File này là **sổ trạng thái vận hành**: mỗi mạch ↔ suite chính ↔ kết quả D1 thật ↔ runtime probe ↔ closure record ↔ trạng thái.
> Ngày lập: 2026-09-10. Branch: `audit/runtime-guard-AUDIT-20260909`. HEAD lúc lập: `067e636216977c420e79811ebe4e75bd1c7bc05d` (HEAD **không** phải SHA pin của bất kỳ mạch nào ngoài M1).

## Quy tắc trạng thái (không được nới)

- `CLOSED` — chỉ khi có đủ **D0–D8** trên **cùng một SHA pin** + closure record trong `reports/circuit-closures/`.
- `CLOSED_WITH_KNOWN_GAP` — hợp lệ nhưng có ít nhất một mục mang `EVIDENCE_GAP` đã ghi rõ trong closure record. **Không** được đọc thành "đã xong hoàn hảo".
- `D1_PASS__NOT_CLOSED` — suite chính xanh nhưng **CHƯA** có pin/runtime/closure. **KHÔNG** được đọc là "xong"; đây mới là điều kiện cần, chưa đủ.
- `D1_FAIL` — suite chính đỏ (exit ≠ 0). Mạch chắc chắn chưa thể đóng.
- `NOT_VERIFIED` — chưa chạy. Không hàm ý hỏng, và cũng **không** được đọc thành "đã xong".
- `EVIDENCE_GAP` — đã chạy nhưng thiếu/không hợp lệ một mục bắt buộc.

## ⚠️ CẢNH BÁO VỀ BẰNG CHỨNG D1 (đọc trước khi dùng bảng)

1. **D1 inventory chạy trên working tree (dirty, chưa pin SHA).** Các suite dưới đây do AutoCoder chạy bằng `py -3.12 -m pytest <suite> -q --no-header` trên **working tree hiện tại**, nơi `git status` đang có nhiều file `.py` modified/untracked. Kết quả **không** gắn với một SHA bất biến.
2. **Đây là baseline để LẬP KẾ HOẠCH, không phải bằng chứng đóng mạch.** Mọi con số ở cột D1 chỉ trả lời câu hỏi "suite có đỏ không", **không** trả lời "mạch đã đóng chưa". Không được dùng bảng này để tuyên bố bất kỳ mạch M2–M14 nào là đã hoàn thành.
3. **M1 là ngoại lệ.** M1 có closure record + SHA pin riêng (`M01-closure.json`, sha_pin `765075312bdc55373a86d9c5577ac62140c7ad64`); kết quả D1 của M1 lấy từ `M01-evidence/D1-T01-pytest.txt`, **không** lấy từ `INVENTORY/`.
4. **`INVENTORY/*.txt` là output nguyên văn** của lần chạy đó (đã copy vào repo). Không có lần chạy lại nào trong lần lập sổ này.
5. **Exit code ≠ chất lượng test.** Cảnh báo `RequestsDependencyWarning` và traceback `Exception while exporting Span` (opentelemetry) xuất hiện trong nhiều file INVENTORY; chúng **không** làm đổi exit code của pytest, nhưng có mặt trong log và chưa được phân loại là vô hại.

## Bảng trạng thái 14 mạch

| Mạch | Tên | Suite chính | D1 (exit + tóm tắt) | Runtime probe (đã/chưa) | Closure record | Trạng thái | Bằng chứng |
|---|---|---|---|---|---|---|---|
| M1 | Boot & Background | `tests/T01_boot/` | exit 0 — 35 passed (7.78s, lần chạy re-pin) | **đã** (`GET /health` + `/readiness` + container log) | `M01-closure.json` (sha_pin `7650753…`) | **CLOSED_WITH_KNOWN_GAP** (D4 = EVIDENCE_GAP) | `M01-evidence/D1-T01-pytest.txt`, `M01-evidence/D2-docker.txt` |
| M2 | Ask & Chat | `tests/T02_contract/test_flow_02_ask_chat_scp_standard.py` | exit 0 — **34 passed** (21.33s, chạy lại tại pin `1f00d00…`, `M02-evidence/D1-T02-pytest.txt`; inventory cũ `INVENTORY/M2.txt` là 3F/30P **trước** khi fix MACH2 + contract 1a — đã lỗi thời) | **đã** (rebuild + force-recreate với `SCP_GIT_SHA=1f00d00…`: /health 200, /readiness ready, `service_identity.commit` == pin; /ask missing-context → FAIL/withheld/KILL fail-closed; /ask context-backed → PASS/UPHOLD + task COMPLETED và WS /chat → frame `verified` trên instance standard **tạm** :8001 cùng image, đã tắt) | `M02-closure.json` (sha_pin `1f00d00…`) | **CLOSED_WITH_KNOWN_GAP** (D3/D4/D5/D6/D7 = PASS_WITH_LIMITS — đọc known_gaps: chat route không đăng ký trên profile=core; PASS/verified chỉ chứng minh với answer source fixture local; D5 chưa có artifact review trong repo) | `M02-evidence/D1-T02-pytest.txt`, `D2-docker.txt`, `D3-*.json/.txt`, `D6-*.txt`, `D7-todo-scan.txt` |
| M3 | OpenAI-compat | `tests/T02_contract/test_flow_03_openai_compat_scp_standard.py` | exit 1 — 7 failed, 21 passed (4.16s) | chưa | — | **D1_FAIL** | `INVENTORY/M3.txt` |
| M4 | Control & Hands | `tests/T03_capability/test_flow_04_control_hands_scp_standard.py` (+ `tests/T03_capability/`) | exit 1 — 7 failed, 50 passed (17.00s) | chưa | — | **D1_FAIL** | `INVENTORY/M4.txt` |
| M5 | Agent/Call | `tests/T03_capability/test_flow_05_agent_call_scp_standard.py` | exit 0 — 35 passed (3.29s) | chưa | — | **D1_PASS__NOT_CLOSED** | `INVENTORY/M5.txt` |
| M6 | Prediction | `tests/T03_capability/test_flow_06_prediction_scp_standard.py` | exit 1 — 6 failed, 12 passed (3.61s) | chưa | — | **D1_FAIL** | `INVENTORY/M6.txt` |
| M7 | AutoFix & Policy | `tests/T03_capability/test_flow_07_autofix_scp_standard.py` | exit 0 — 43 passed (80.76s) | chưa | — | **D1_PASS__NOT_CLOSED** | `INVENTORY/M7.txt` |
| M8 | Audit/Benchmark | `tests/T03_capability/test_flow_08_audit_benchmark_scp_standard.py` | exit 0 — 25 passed (2.95s) | chưa | — | **D1_PASS__NOT_CLOSED** | `INVENTORY/M8.txt` |
| M9 | Threat & Counter | `tests/T03_capability/test_flow_09_threat_analysis_scp_standard.py` | exit 0 — 23 passed (2.62s) | chưa | — | **D1_PASS__NOT_CLOSED** | `INVENTORY/M9.txt` |
| M10 | Streaming | `tests/T03_capability/test_flow_10_streaming_scp_standard.py` | exit 1 — 5 failed, 7 passed (3.69s) | chưa | — | **D1_FAIL** | `INVENTORY/M10.txt` |
| M11 | Admin/Import | `tests/T03_capability/test_flow_11_admin_import_scp_standard.py` | exit 0 — 35 passed (4.42s) | chưa | — | **D1_PASS__NOT_CLOSED** | `INVENTORY/M11.txt` |
| M12 | Background WHY | `tests/T03_capability/test_flow_12_background_why_scp_standard.py` | exit 1 — 10 failed, 16 passed (5.24s) | chưa | — | **D1_FAIL** | `INVENTORY/M12.txt` |
| M13 | Data sources & Learning | `tests/T03_capability/test_flow_13_free_api_learning_scp_standard.py` | exit 0 — 27 passed (3.37s) | chưa | — | **D1_PASS__NOT_CLOSED** | `INVENTORY/M13.txt` |
| M14 | v106 Audit/Self-model | `tests/T03_capability/test_flow_17_self_model_capability_scp_standard.py` + `tests/T11_release/` | exit 0 — 1 passed (2.69s) **và** exit 0 — 69 passed (2.49s) | chưa | — | **D1_PASS__NOT_CLOSED** | `INVENTORY/M14a.txt`, `INVENTORY/M14b.txt` |

Tổng hợp theo exit code (inventory lập sổ 2026-09-10): **8 mạch xanh D1** (M1, M5, M7, M8, M9, M11, M13, M14) / **6 mạch đỏ D1** (M2, M3, M4, M6, M10, M12). **Cập nhật 2026-09-11:** M2 đã chạy lại tại pin `1f00d00…` sau chuỗi fix MACH2 + contract 1a → **34/34 exit 0** và có closure record → **CLOSED_WITH_KNOWN_GAP** (`M02-closure.json`). Hiện **2/14 mạch có closure record** (M1, M2) — cả hai đều mang gap đã ghi rõ.

**Suite xanh ≠ mạch đóng; phải có D0–D8.**

## Danh sách mạch CÒN LẠI phải hoàn thiện

### (a) `D1_FAIL` — phải sửa trước khi có thể nói tới đóng mạch (M2, M3, M4, M6, M10, M12)

Danh sách test FAILED trích nguyên từ `INVENTORY/*.txt`:

**M2 — Ask & Chat (3 failed)** — `INVENTORY/M2.txt`
> **UPDATE 2026-09-11 (đã xử lý):** 3 test đỏ này thuộc contract cũ; owner phê duyệt contract 1a (verified-frame), Agent T sửa file test theo hướng TĂNG strictness (thêm assert `governance==KILL`, precondition provider isolation, pin exact `provider_label`, bỏ legacy frame type `answer`); root cause thật là lỗ hổng isolation làm lộ OPENROUTER key slot 4-10 vào pytest (cloud round-trip). Suite chạy lại tại pin `1f00d00…`: **34/34 exit 0** (`M02-evidence/D1-T02-pytest.txt`). M2 đã có closure record `M02-closure.json` → **CLOSED_WITH_KNOWN_GAP**. Số 3 failed dưới đây là trích nguyên văn inventory CŨ (trước fix), giữ lại để audit lịch sử.
- `test_flow_02_ask_chat_scp_standard.py::TestFlow02AskEndpoint::test_ask_endpoint_llm_gateway_fallback_chain`
- `test_flow_02_ask_chat_scp_standard.py::TestFlow02WebSocketChat::test_ws_chat_message_exchange_fail_closed_without_llm`
- `test_flow_02_ask_chat_scp_standard.py::TestFlow02WebSocketChat::test_ws_chat_rate_limit_exceeded_closes_1008`

**M3 — OpenAI-compat (7 failed)** — `INVENTORY/M3.txt`
- `test_flow_03_openai_compat_scp_standard.py::TestFlow03OpenAICompat::test_openai_chat_completions_validates_schema`
- `test_flow_03_openai_compat_scp_standard.py::TestFlow03OpenAICompat::test_openai_compat_handles_streaming_false`
- `test_flow_03_openai_compat_scp_standard.py::TestFlow03OpenAICompat::test_swe_bench_chat_completions_endpoint_exists`
- `test_flow_03_openai_compat_scp_standard.py::TestFlow03OpenAICompat::test_swe_bench_validates_instance_id`
- `test_flow_03_openai_compat_scp_standard.py::TestFlow03OpenAICompat::test_streaming_response_translation`
- `test_flow_03_openai_compat_scp_standard.py::TestFlow03OpenAICompat::test_openai_compat_gateway_failure_returns_503`
- `test_flow_03_openai_compat_scp_standard.py::TestFlow03OpenAICompat::test_swe_bench_compat_agent_failure_returns_error`

**M4 — Control & Hands (7 failed)** — `INVENTORY/M4.txt`
- `test_flow_04_control_hands_scp_standard.py::TestFlow04ControlHands::test_pc_controller_execute_requires_token_and_capability`
- `test_flow_04_control_hands_scp_standard.py::TestFlow04ControlHands::test_pc_controller_kill_clear_requires_capability_token`
- `test_flow_04_control_hands_scp_standard.py::TestFlow04ControlHands::test_control_capability_status_requires_admin`
- `test_flow_04_control_hands_scp_standard.py::TestFlow04ControlHands::test_control_capability_escalate_requires_admin`
- `test_flow_04_control_hands_scp_standard.py::TestFlow04ControlHands::test_pc_controller_write_file_succeeds_with_valid_token`
- `test_flow_04_control_hands_scp_standard.py::TestFlow04ControlHands::test_hands_executor_forwards_token_to_controller`
- `test_flow_04_control_hands_scp_standard.py::TestFlow04ControlHands::test_hands_executor_rejects_missing_token_fail_closed`

**M6 — Prediction (6 failed)** — `INVENTORY/M6.txt`
- `test_flow_06_prediction_scp_standard.py::TestFlow06Prediction::test_prediction_run_cycle_requires_admin`
- `test_flow_06_prediction_scp_standard.py::TestFlow06Prediction::test_prediction_pending_requires_admin`
- `test_flow_06_prediction_scp_standard.py::TestFlow06Prediction::test_prediction_all_requires_admin`
- `test_flow_06_prediction_scp_standard.py::TestFlow06Prediction::test_prediction_verify_requires_admin`
- `test_flow_06_prediction_scp_standard.py::TestFlow06Prediction::test_prediction_stats_requires_admin`
- `test_flow_06_prediction_scp_standard.py::TestFlow06Prediction::test_prediction_run_cycle_executes_v5_pipeline`

**M10 — Streaming (5 failed)** — `INVENTORY/M10.txt`
- `test_flow_10_streaming_scp_standard.py::TestFlow10Streaming::test_stream_endpoint_accepts_streaming_request`
- `test_flow_10_streaming_scp_standard.py::TestFlow10Streaming::test_stream_sse_format_correct`
- `test_flow_10_streaming_scp_standard.py::TestFlow10Streaming::test_stream_handles_llm_gateway_failover`
- `test_flow_10_streaming_scp_standard.py::TestFlow10Streaming::test_stream_validates_request_schema`
- `test_flow_10_streaming_scp_standard.py::TestFlow10Streaming::test_stream_timeout_handling`

**M12 — Background WHY (10 failed)** — `INVENTORY/M12.txt`
- `test_flow_12_background_why_scp_standard.py::TestFlow12BackgroundWhy::test_doubt_cron_initializes_without_db_lock`
- `…::test_doubt_cron_runs_checks`
- `…::test_doubt_cron_persists_report_to_jsonl`
- `…::test_doubt_cron_respects_interval`
- `…::test_doubt_cron_handles_check_errors_silently`
- `…::test_doubt_cron_stops_background_thread`
- `…::test_why_engine_verifies_past_decisions`
- `…::test_why_engine_looks_up_external_sources`
- `…::test_why_engine_detects_contradictions`
- `…::test_query_open_meteo_returns_results`

**Ràng buộc sửa (theo `AGENTS.md` + DNA):** sửa **PRODUCT/HARNESS tại điểm lỗi**, không làm xanh bằng delete/skip/xfail/hạ assertion. Mỗi nhóm sửa phải kèm repro + xác nhận root cause trước khi sửa (DNA #1, #26). `INVENTORY/M12.txt` có ít nhất một `TypeError` tại `tests/T03_capability/test_flow_12_background_why_scp_standard.py:42` — cần đọc kỹ để phân biệt lỗi harness với lỗi product trước khi kết luận.

### (b) `D1_PASS__NOT_CLOSED` — suite xanh nhưng **chưa đóng mạch** (M5, M7, M8, M9, M11, M13, M14)

Các mạch này **chưa có gì ngoài D1**. Việc còn lại, theo `CLOSURE-CONTRACT.md`:

| Mạch | D0 khóa phạm vi + SHA pin | D2 runtime proof | D3 adversarial | D4 ratchet | D5 review độc lập | D6 fail-loudly | D7 wiring/docs | D8 closure record |
|---|---|---|---|---|---|---|---|---|
| M5 Agent/Call | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ |
| M7 AutoFix & Policy | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ |
| M8 Audit/Benchmark | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ |
| M9 Threat & Counter | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ |
| M11 Admin/Import | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ |
| M13 Data sources & Learning | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ |
| M14 v106 Audit/Self-model | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ |

(D1 của nhóm này cũng **chưa** đủ điều kiện làm D1 hợp lệ: D1 yêu cầu "suite chính exit 0 + lưu toàn bộ output làm artifact **trên SHA pin**"; output hiện có là chạy trên working tree dirty.)

### (c) M1 — đã có closure, còn nợ đã ghi rõ

M1 **không** nằm trong danh sách "còn lại" ở dạng mở, nhưng **không được đọc là sạch**: `M01-closure.json` ghi `falsification_status = PARTIALLY_FALSIFIED_AT_PIN`, `D4_ratchet = EVIDENCE_GAP` (hook ledger `runStatus=inconclusive`, `scanned_files=0`, 6/6 file phạm vi `scanner_failed`; mốc "HIGH toàn dự án" chưa từng được đo đầy đủ). D5 của PIN2 **đã có 2 bản review độc lập** (`M01-evidence/D5-reviewer-3-pin2.md` = APPROVE_WITH_LIMITS, `D5-reviewer-4-overclaim.md` = PARTIAL/không thấy bịa đặt) nên nhãn D5 nay là `PASS_WITH_LIMITS`, **không** phải PASS trơn; còn nợ: `reviewer_limits` L1 (HEAD ≠ sha_pin → vi phạm điều khoản D8 "cùng commit"), L3 (evidence D1/D3 chạy ở parent, chỉ content-equivalent), L5 (header 4 module ghi `STATUS: CLOSED`). Chi tiết: `M01-closure.json` → `reviewer_limits` + `known_gaps`.

## Thứ tự đề xuất

Nguyên tắc xếp thứ tự: (1) sửa theo **cụm cùng root cause** để một lần điều tra trả nợ nhiều mạch; (2) nhóm đỏ trước nhóm xanh, vì mạch đỏ chặn cả D1; (3) việc đóng closure (D0/D2/D3/D4/D5/D8) làm sau, khi D1 đã ổn định và có pin.

1. **Cụm authz/admin — M4 + M6.** Cả hai đỏ gần như đồng dạng quanh kiểm quyền: M6 là 5/6 test `*_requires_admin` + 1 test pipeline; M4 là token/capability PEP + `*_requires_admin`. Cùng một lớp nguyên nhân (ranh giới token/admin) → sửa một lần, hồi quy cả hai.
2. **Cụm gateway/chat — M2 + M3 + M10.** M2 (`llm_gateway_fallback_chain`, WS fail-closed, WS rate-limit 1008), M3 (`gateway_failure_returns_503`, streaming translation), M10 (SSE format, gateway failover, timeout) đều là một trục: hành vi fail-closed/fail-over và hợp đồng streaming của gateway. Sửa trục này trước khi đóng bất kỳ mạch nào ở nhóm xanh liên quan tới LLM.
3. **Cụm WHY — M12.** 10 test đỏ tập trung vào `doubt_cron` + `why_engine` + `open_meteo`; có `TypeError` tại dòng 42 nên cần phân loại harness-vs-product trước.
4. **Đóng closure cho nhóm D1_PASS.** Sau khi D1 ổn định: chốt SHA pin → D0 → D2 runtime probe thật → D3 adversarial → D4 ratchet → D5 review độc lập → D6 → D7 → D8. Đề xuất thứ tự trong nhóm: M5, M8, M9, M11, M13 (suite nhỏ, 1 file) trước; M7 và M14 sau (M14 cần gộp 2 suite: `flow_17` + `tests/T11_release/`).
5. **Đóng nợ M1.** Chạy lại D4 đúng phạm vi M1 để đóng `EVIDENCE_GAP`; D5 của PIN2 nay đã có 2 bản review độc lập (`D5-reviewer-3-pin2.md`, `D5-reviewer-4-overclaim.md`) — việc còn lại là `reviewer_limits` L1/L3/L5 (khep D8 "cùng commit" đòi re-pin theo đúng trình tự, evidence D1/D2/D3/D4 phải chạy lại trên checkout sạch của SHA pin, và header 4 module về `CLOSED_WITH_KNOWN_GAP`). Không đóng được thì giữ nguyên `CLOSED_WITH_KNOWN_GAP` — tuyệt đối không hạ chuẩn D4 để lấy `CLOSED`.

**Suite xanh ≠ mạch đóng; phải có D0–D8.**

## Giới hạn bằng chứng của sổ này (missing pieces)

- Không có SHA pin cho D1 của M2–M14 → **không thể** dùng số liệu này để chứng minh bất kỳ điều gì về một commit cụ thể. Working tree đang dirty; kết quả có thể lệch nếu chạy lại sau khi có người sửa `.py`.
- Không có runtime probe nào cho M2–M14 trong lần lập sổ → cột "Runtime probe" = "chưa" là **thiếu bằng chứng**, không phải "đã kiểm và không có vấn đề".
- Sổ này **không** phân loại nguyên nhân gốc của 38 test đỏ (3+7+7+6+5+10). Danh sách FAILED là trích nguyên văn, chưa phải chẩn đoán.
- Số lượng test xanh/đỏ **không** nói gì về coverage, mutation score, hay chất lượng assertion.
- M14 gộp 2 suite trong một mạch; `INVENTORY/M14a.txt` (1 passed) + `M14b.txt` (69 passed) đều xanh, nhưng chưa xác minh được `tests/T11_release/` có thực sự phủ đủ phạm vi D1 của M14 theo `CLOSURE-CONTRACT.md` hay không.
- Cảnh báo dependency (`urllib3`/`chardet`) và lỗi export span OpenTelemetry xuất hiện trong log INVENTORY nhưng chưa được đánh giá là vô hại hay có hại cho kết quả.
- Sổ này **không** tuyên bố bất kỳ mạch nào "an toàn", "production-ready", hay "không còn vấn đề". `PASS` chỉ nghĩa là chưa quan sát thấy lỗi trong phạm vi đã chạy.
