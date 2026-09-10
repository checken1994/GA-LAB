# SCP Circuit Flow Map — 14 mạch đóng theo hợp đồng D0–D8

> Authority: hợp đồng đóng mạch D0–D8 (phụ lục 14 mạch). File này là **bản đồ wiring**:
> mỗi mạch ↔ suite test chính ↔ runtime probe ↔ trạng thái đóng.
>
> Quy tắc trạng thái (không được nới):
> - `CLOSED` chỉ khi có đủ D0–D7 trên **cùng một SHA pin** + closure record trong `reports/circuit-closures/`.
> - `NOT_VERIFIED` = chưa có bằng chứng runtime trên SHA pin. **Không** đồng nghĩa "hỏng", và **không** được đọc thành "đã xong".
> - `EVIDENCE_GAP` = đã chạy nhưng thiếu/không hợp lệ một mục bắt buộc.

Bảng dưới là trạng thái tại lần cập nhật gần nhất; luôn đối chiếu lại với closure record thật trong `reports/circuit-closures/` thay vì tin bảng này.

| Mạch | Tên | Suite chính | Runtime probe | Trạng thái |
|---|---|---|---|---|
| M1 | Boot & Background | `tests/T01_boot/` | watchdog `first execution completed` log; `GET /health` (service_identity.commit == SHA pin); `GET /readiness` (judge/background_scheduler = ok) | **CLOSED** (`reports/circuit-closures/M01-closure.json`) |
| M2 | Ask & Chat | `tests/T02_contract/test_flow_02_ask_chat_scp_standard.py` | WS probe thật; trace `ask_task_kernel` | NOT_VERIFIED |
| M3 | OpenAI-compat | `tests/T02_contract/test_flow_03_openai_compat_scp_standard.py` | chưa thực hiện | NOT_VERIFIED |
| M4 | Control & Hands | `tests/T03_capability/test_flow_04_control_hands_scp_standard.py` + `tests/T03_capability/` | chưa thực hiện | NOT_VERIFIED |
| M5 | Agent/Call | `tests/T03_capability/test_flow_05_agent_call_scp_standard.py` | chưa thực hiện | NOT_VERIFIED |
| M6 | Prediction | `tests/T03_capability/test_flow_06_prediction_scp_standard.py` | chưa thực hiện | NOT_VERIFIED |
| M7 | AutoFix & Policy | `tests/T03_capability/test_flow_07_autofix_scp_standard.py` | chưa thực hiện | NOT_VERIFIED |
| M8 | Audit/Benchmark | `tests/T03_capability/test_flow_08_audit_benchmark_scp_standard.py` | chưa thực hiện | NOT_VERIFIED |
| M9 | Threat & Counter | `tests/T03_capability/test_flow_09_threat_analysis_scp_standard.py` | chưa thực hiện | NOT_VERIFIED |
| M10 | Streaming | `tests/T03_capability/test_flow_10_streaming_scp_standard.py` | chưa thực hiện | NOT_VERIFIED |
| M11 | Admin/Import | `tests/T03_capability/test_flow_11_admin_import_scp_standard.py` | chưa thực hiện | NOT_VERIFIED |
| M12 | Background WHY | `tests/T03_capability/test_flow_12_background_why_scp_standard.py` | chưa thực hiện | NOT_VERIFIED |
| M13 | Data sources & Learning | `tests/T03_capability/test_flow_13_free_api_learning_scp_standard.py` | chưa thực hiện | NOT_VERIFIED |
| M14 | v106 Audit/Self-model | `tests/T03_capability/test_flow_17_self_model_capability_scp_standard.py` + `tests/T11_release/` | chưa thực hiện | NOT_VERIFIED |

## Ghi chú về cột "Suite chính"

- Đường dẫn ở cột Suite chính là **tên file đang tồn tại trên đĩa** tại thời điểm lập bản đồ (kiểm bằng `ls`), không phải bằng chứng các test đó đã PASS.
- Tồn tại test ≠ Reality proof (GA.md § A5). Với M2–M14, "NOT_VERIFIED" nghĩa là **chưa chạy và chưa pin SHA**; không hàm ý suite đúng hay sai.
- Riêng M1: suite `tests/T01_boot/` đã chạy thật, kết quả và SHA nằm trong `M01-evidence/` + `M01-closure.json`.

## Runtime probe M1 — hợp đồng tối thiểu

| Probe | Kỳ vọng | Bằng chứng |
|---|---|---|
| `GET /health` | HTTP 200, `service_identity.commit == SCP_GIT_SHA` đã pin lúc build | `M01-evidence/D2-docker.txt` |
| `GET /readiness` | HTTP 200, `{"status":"ready","checks":{"judge":"ok","background_scheduler":"ok"}}` | `M01-evidence/D2-docker.txt` |
| container log | `[MACH1-FIX-1] ... (5 jobs: ...)`, `[MACH1-FIX-2]`, `[RESTORED-SYSTEMS] RetryPolicy background thread started`, `first execution completed` | `M01-evidence/D2-docker.txt` |

Cách chạy lại: `reports/circuit-closures/M01-runbook.md`.
