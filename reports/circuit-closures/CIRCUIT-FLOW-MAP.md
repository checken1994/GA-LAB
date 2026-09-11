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

Bảng dưới là trạng thái tại lần cập nhật gần nhất; luôn đối chiếu lại với closure record thật trong `reports/circuit-closures/` thay vì tin bảng này.

| Mạch | Tên | Suite chính | Runtime probe | Trạng thái |
|---|---|---|---|---|
| M1 | Boot & Background | `tests/T01_boot/` | watchdog `first execution completed` log; `GET /health` (service_identity.commit == SHA pin); `GET /readiness` (judge/background_scheduler = ok) | **CLOSED_WITH_KNOWN_GAP** (`reports/circuit-closures/M01-closure.json`, D4 = EVIDENCE_GAP) |
| M2 | Ask & Chat | `tests/T02_contract/test_flow_02_ask_chat_scp_standard.py` | WS probe thật; trace `ask_task_kernel` | **D1_FAIL** (exit 1: 3 failed, 30 passed — `INVENTORY/M2.txt`) |
| M3 | OpenAI-compat | `tests/T02_contract/test_flow_03_openai_compat_scp_standard.py` | chưa thực hiện | **D1_FAIL** (exit 1: 7 failed, 21 passed — `INVENTORY/M3.txt`) |
| M4 | Control & Hands | `tests/T03_capability/test_flow_04_control_hands_scp_standard.py` + `tests/T03_capability/` | chưa thực hiện | **D1_FAIL** (exit 1: 7 failed, 50 passed — `INVENTORY/M4.txt`) |
| M5 | Agent/Call | `tests/T03_capability/test_flow_05_agent_call_scp_standard.py` | chưa thực hiện | **D1_PASS__NOT_CLOSED** (exit 0: 35 passed — `INVENTORY/M5.txt`) |
| M6 | Prediction | `tests/T03_capability/test_flow_06_prediction_scp_standard.py` | chưa thực hiện | **D1_FAIL** (exit 1: 6 failed, 12 passed — `INVENTORY/M6.txt`) |
| M7 | AutoFix & Policy | `tests/T03_capability/test_flow_07_autofix_scp_standard.py` | chưa thực hiện | **D1_PASS__NOT_CLOSED** (exit 0: 43 passed — `INVENTORY/M7.txt`) |
| M8 | Audit/Benchmark | `tests/T03_capability/test_flow_08_audit_benchmark_scp_standard.py` | chưa thực hiện | **D1_PASS__NOT_CLOSED** (exit 0: 25 passed — `INVENTORY/M8.txt`) |
| M9 | Threat & Counter | `tests/T03_capability/test_flow_09_threat_analysis_scp_standard.py` | chưa thực hiện | **D1_PASS__NOT_CLOSED** (exit 0: 23 passed — `INVENTORY/M9.txt`) |
| M10 | Streaming | `tests/T03_capability/test_flow_10_streaming_scp_standard.py` | chưa thực hiện | **D1_FAIL** (exit 1: 5 failed, 7 passed — `INVENTORY/M10.txt`) |
| M11 | Admin/Import | `tests/T03_capability/test_flow_11_admin_import_scp_standard.py` | chưa thực hiện | **D1_PASS__NOT_CLOSED** (exit 0: 35 passed — `INVENTORY/M11.txt`) |
| M12 | Background WHY | `tests/T03_capability/test_flow_12_background_why_scp_standard.py` | chưa thực hiện | **D1_FAIL** (exit 1: 10 failed, 16 passed — `INVENTORY/M12.txt`) |
| M13 | Data sources & Learning | `tests/T03_capability/test_flow_13_free_api_learning_scp_standard.py` | chưa thực hiện | **D1_PASS__NOT_CLOSED** (exit 0: 27 passed — `INVENTORY/M13.txt`) |
| M14 | v106 Audit/Self-model | `tests/T03_capability/test_flow_17_self_model_capability_scp_standard.py` + `tests/T11_release/` | chưa thực hiện | **D1_PASS__NOT_CLOSED** (exit 0: 1 passed + 69 passed — `INVENTORY/M14a.txt`, `INVENTORY/M14b.txt`) |

Chi tiết đầy đủ (danh sách test FAILED, việc còn lại cho từng mạch, thứ tự đề xuất, giới hạn bằng chứng): `reports/circuit-closures/STATUS-LEDGER.md`.

> ⚠️ Cột Trạng thái ở bảng trên phản ánh **D1 inventory chạy trên working tree (dirty, chưa pin SHA)** do AutoCoder thực hiện — đây là baseline để lập kế hoạch, **không phải bằng chứng đóng mạch**. Riêng M1 giữ nguyên `CLOSED_WITH_KNOWN_GAP` theo `M01-closure.json`. **Suite xanh ≠ mạch đóng; phải có D0–D8.**

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
