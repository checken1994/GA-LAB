# SCP Telemetry: Evidence Sau Bản Vá Terminal State

**Ngày kiểm tra:** 17/08/2026.
**Mục tiêu kiểm tra:** Khi Evolution bị tắt bằng chính sách, lần khởi tạo mới không được ghi là `STARTING` chưa có kết thúc trong run ledger. Nó phải ghi ngay trạng thái kết thúc `DISABLED`.

## Thay đổi nhỏ đã thực hiện

Hàm `SubsystemTelemetry.start()` được đổi theo đúng một quy tắc:

| Trạng thái chính sách | Trước bản vá | Sau bản vá |
|---|---|---|
| Subsystem đang chạy | `STARTING` | `STARTING` |
| Subsystem bị tắt có chủ đích | `STARTING` | `DISABLED` |

Lý do là `DISABLED` không phải lỗi hoặc process chết. Đây là một quyết định an toàn: Evolution không được phép chạy. Ghi `STARTING` cho trường hợp này làm người đọc ledger hiểu nhầm là một run đã kẹt hoặc mất terminal event.

## Chuỗi bằng chứng trên PC thật

| Bước | Bằng chứng quan sát được | Kết quả |
|---|---|---|
| Sao lưu | Có bản trước vá tại `C:\Users\check\Downloads\scp\scp-audit\telemetry-terminal-20260817-191901\subsystem_telemetry.py.before` | Có đường rollback |
| Kiểm tra mã | `python -m py_compile scp/core/subsystem_telemetry.py` bằng venv của SCP | PASS |
| Probe runtime thật | Khởi tạo `EvolutionEngine("data")` trong child process với `SCP_EVOLUTION_ENABLED=0` | PASS |
| Postcondition ledger | Event mới nhất trong `data/evolution_runs.jsonl` có `event_type=started` và `status=DISABLED` | PASS |
| Reality regression | `tests/run_reality_tests_portable.py` | **74/74 PASS**, 0 fail, 0 timeout |
| Python regression | `python -m pytest -q` trong venv SCP | **101 passed**, 2 warnings |
| Runtime services | Dashboard `/`, scheduler `/`, backend `/health`, Ollama `/api/tags` | Cả 4 HTTP 200 |

Probe không gọi `evolve_cycle()`, không chạy AutoFix, không tạo candidate mới, không đổi `active_policies.json` và không promote policy. Vì vậy nó chứng minh đúng một việc: **lifecycle ledger của Evolution khi bị tắt ghi đúng terminal state**.

## GitHub và trạng thái source

Patch tương thích đã được push lên GitHub ở commit **`3028fb2`** với message `fix(telemetry): make disabled startup terminal`.

PC thật đang có cùng thay đổi logic đã được reality-test, nhưng repository local của PC có lịch sử cũ và nhiều file dirty từ các phiên trước. Sau khi fetch, nhánh PC có một local commit telemetry riêng và còn lệch lịch sử với `origin/main`. Không thực hiện `pull`, `rebase` hoặc reset tự động vì các thao tác đó có thể đè file local chưa phân loại. Đây là một giới hạn đồng bộ cần xử lý bằng backup và merge có kiểm soát sau này.

## Điều đã được chứng minh và điều chưa được chứng minh

| Claim | Verdict | Lý do |
|---|---|---|
| Startup có chính sách tắt ghi terminal `DISABLED` trên PC thật | **VERIFIED** | Có compile, probe ledger và regression sau thay đổi |
| Bản vá không làm hỏng bộ reality test hiện có | **PASS_WITHIN_SCOPE** | 74/74 reality test pass |
| Bản vá không làm hỏng regression Python hiện có | **PASS_WITHIN_SCOPE** | 101 pytest pass |
| Bốn service core đang phản hồi ở thời điểm kiểm tra | **VERIFIED** | HTTP 200 trên route đúng của từng service |
| Evolution đã chạy production và tự sinh policy hợp lệ | **BLOCKED** | Evolution đang bị tắt có chủ đích; probe không và không được phép bật/promotion policy |
| AutoFix candidate → patch → regression-free đã được chứng minh end-to-end | **BLOCKED** | Chưa có evidence chain thật cho toàn bộ đường đi |
| SCP đã production-ready hoàn toàn | **BLOCKED** | Thiếu full chaos, security, reproducibility và policy-handoff evidence |

> `PASS` ở đây chỉ có nghĩa là không thấy lỗi trong đúng phạm vi kiểm tra. Nó không có nghĩa SCP đã tự hoàn thiện, đã an toàn trước mọi tấn công, hoặc đã sẵn sàng phát hành production.

## Rollback

Nếu patch gây lỗi, khôi phục file backup trên PC nêu ở bảng bằng chứng, sau đó chạy lại `py_compile`, reality suite và HTTP probe bốn service. Không cần thay đổi `.env`, không cần rotate token, không cần sửa database hay active policy để rollback patch này.

## Việc còn mở

1. Hợp nhất repository PC cũ với GitHub `main` theo cách có backup, vì hiện lịch sử branch chưa đồng nhất.
2. Chạy evidence chain riêng cho AutoFix thật nhưng bị giới hạn phạm vi, có snapshot, rollback và verifier độc lập.
3. Chạy policy handoff có dữ liệu candidate hợp lệ trong staging trước; chỉ promotion production sau khi có bằng chứng và người sở hữu hiểu thay đổi.
4. Hoàn thành security/chaos/recovery gate trước khi dùng nhãn production-ready.
