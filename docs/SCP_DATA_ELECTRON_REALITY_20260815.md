# SCP — Kiểm tra thư mục data và lỗi Desktop thực tế

**Ngày:** 15/08/2026  
**Máy kiểm tra:** Windows thật tại `C:\Users\check\Downloads\scp`  
**Nguyên tắc:** Không xóa dữ liệu sống khi chưa có backup và test lại.

## 1. Kết luận ngắn

Thư mục `data` không chỉ có “dữ liệu học”. Nó đang trộn bốn loại: dữ liệu sống của SCP, nhật ký bảo mật, kết quả benchmark/test và log thử nghiệm của các round cũ. Vì vậy nhìn vào thư mục sẽ thấy rất nhiều file, nhưng không có nghĩa tất cả đều là lỗi.

Trong lần kiểm tra này, **database và ledger sống không bị xóa**. Chỉ có 219 log root cũ ngày 13–14/08 được chuyển vào `data\archive\root-logs-20260815-074036`. Đây là chuyển chỗ, không phải xóa; manifest nằm trong thư mục archive để rollback.

Một chuỗi giống OpenRouter key đã xuất hiện trong `data\desktop-logs\bridge-error.log`. File đã được backup riêng trước khi che chuỗi. Sau khi che, không còn chuỗi bắt đầu bằng `sk-or-v1` trong các file text của `data`. Tên trường `OPENROUTER_API_KEY` còn xuất hiện trong một số dòng chẩn đoán, nhưng không phải giá trị key.

## 2. Các nhóm file trong data

| Nhóm | Bằng chứng lúc kiểm tra | Có nên xóa? | Lý do |
|---|---:|---|---|
| `v13.db` và WAL/SHM | DB khoảng 55,58 MB; WAL/SHM tồn tại và kích thước có thể thay đổi khi SCP chạy | **Không** | Đây là DB sống; xóa WAL/SHM có thể làm mất dữ liệu chưa checkpoint |
| SQLite phụ | `subsystem_heartbeat.sqlite`, `autofix_worker.sqlite`, `scp_reputation.sqlite`, `kb_evolve.sqlite` | **Không** | Lưu heartbeat, worker, reputation và learning |
| Ledger bảo mật | `escalation_log.jsonl` khoảng 30,08 MB; `error_store.jsonl` khoảng 11,71 MB; `bypass_log.jsonl`, `why_gate_audit.jsonl` | **Không** | Đây là bằng chứng audit và threat defense; cần rotation chứ không xóa tùy ý |
| Intel | `intel_updates.jsonl` 702 dòng | **Không** | Pipeline đang ghi nhưng dữ liệu mới đều rỗng; phải sửa ingest trước khi bỏ |
| Benchmark | `benchmark_batches` 10 file; `benchmark_v2` 17 file | **Giữ/đưa archive sau khi chốt báo cáo** | Cần để tái chạy và kiểm tra kết quả |
| E2E/test evidence | `e2e-real` 69 file; `hands` 4; `pc_controller` 3 | **Giữ tạm** | Là bằng chứng các lần kiểm tra thực tế; không phải runtime chính |
| Shadow canary | 100 file trong `shadow` | **Không xóa lúc này** | Mã `shadow_canary.py` còn tham chiếu thư mục này |
| Desktop log | 10 file, khoảng 5,28 MB | **Giữ log mới** | Dùng để điều tra lỗi Desktop; có thể xoay vòng theo ngày |
| Root log cũ | 219 file, khoảng 15,68 MB | **Đã archive** | Là log thử nghiệm ngày 13–14/08, không phải database/ledger sống |

## 3. Nhận xét bên ngoài: phần nào đúng?

### WHY Gate

`why_gate_audit.jsonl` có 682 dòng và parse hợp lệ. Có 159 dòng chứa `BareExceptPass`. Hai chuỗi vị trí được nhắc trong nhận xét xuất hiện nhiều lần: `speculative_prefixer.py:559` có 44 lần và `type_flow_verifier.py:717` có 54 lần.

Vì vậy nhận xét rằng có hiện tượng scanner phát hiện lại cùng finding là **đúng theo log**. Tuy nhiên log hiện tại chưa đủ để kết luận mỗi lần đều là “patch chưa apply”; có thể là scan khác round, file được sinh lại hoặc patch chưa qua reality test. Cần thêm `finding_id`, `before_hash`, `after_hash` và trạng thái patch vào một khóa duy nhất để phân biệt.

### Rollback token

`rollback_tokens.json` không phải một token duy nhất mà có 6 entry. Trong đó **2 entry có trạng thái `pending` và 4 entry thiếu trường trạng thái**. Nhận xét “có token pending” là đúng nhưng chưa nói đủ. Trạng thái thiếu trường còn đáng lo hơn pending vì worker không thể biết phải làm gì tiếp theo.

### Intel feed

`intel_updates.jsonl` có 702 dòng hợp lệ. Cả 702 dòng đều có `new_signatures` rỗng và có 0 dòng `applied=true`. Nhận xét rằng intel pipeline đang chạy nhưng không đưa được chữ ký mới vào hệ thống là **đúng**. Đây là lỗi im lặng cần sửa.

### Threat defense và bypass log

`bypass_log.jsonl` có 1.681 record. Cả 1.681 record đều có `type=caught_with_signatures`, nghĩa là các payload đã được ghi nhận bởi signature trong ledger này. Phân bố verdict là 1.628 `UNKNOWN`, 29 `FAIL` và 23 `CONFLICT`.

Claim “100% bị catch” chỉ đúng cho **các record đã đi vào ledger này**, không thể mở rộng thành “SCP bắt được tất cả mọi cuộc tấn công AI và con người”. Bài benchmark trước đó vẫn có một ca bị đánh dấu `BYPASSED`, nên hai loại bằng chứng này không được trộn với nhau.

### Escalation và điểm 8,6–8,9/10

`escalation_log.jsonl` có khoảng 72.660 dòng, trong đó 1 dòng không parse được. Có 8 nhóm lý do đã được ghi nhận, gồm threat detection, countdown, block IP, rate limit, forensic logging và timeout. Điều này chứng minh log phình to và cần rotation.

Tuy nhiên schema hiện tại có `message`, `timestamp`, `why`; nó chưa đủ để chứng minh đầy đủ các claim như “mọi ca đều có countdown 30 phút” hay “human review đã xử lý”.

Điểm **8,6–8,9/10 không được chấp nhận là điểm đánh giá chính thức** vì nhận xét không đưa ra công thức, trọng số, mẫu số, tiêu chí pass/fail hoặc cách kiểm tra độc lập. Có thể coi đó là nhận xét định tính, không phải benchmark.

## 4. Lỗi Electron

Có ba dòng khác nhau trong log người dùng gửi:

| Dòng log | Ý nghĩa |
|---|---|
| `console-message arguments are deprecated` | Mã Desktop dùng callback kiểu cũ của Electron. Không phải lỗi làm hỏng SCP, nhưng cần sửa vì API cũ sẽ bị bỏ |
| `OnSizeReceived failed with Error: -2` | Chromium báo luồng dữ liệu upload bị đóng/hỏng trong lúc nhận kích thước. Thường liên quan request body/stream bị hủy hoặc kết nối nội bộ bị lỗi |
| `dashboard load failed: ERR_FAILED (-2)` | Một lần tải dashboard thất bại; cần theo dõi nhưng không đủ bằng chứng để kết luận mất dữ liệu |

Đã sửa handler `console-message` từ dạng cũ có nhiều tham số sang dạng mới chỉ nhận event object. Theo tài liệu Electron, listener có hơn một tham số bị coi là listener kiểu cũ và phát warning [1] [2].

Sau khi restart Electron, kết quả thật là:

```text
NODE_CHECK_EXIT=0
ELECTRON_PROCESSES=4
DEPRECATED_WARNING=False
CHROMIUM_PIPE_ERROR=False
PORT_3000_LISTEN=True
PORT_3030_LISTEN=True
PORT_8000_LISTEN=True
PORT_11434_LISTEN=True
HEALTH_HTTP=200
ASK_VERDICT=PASS
ASK_ANSWER=2 + 2 = 4
```

Vì vậy hai dòng warning người dùng gửi **không còn tái hiện trong lần smoke test mới**. Lỗi `Error: -2` là lỗi stream của Chromium, không phải bằng chứng có chương trình lạ gửi dữ liệu ra ngoài. Nếu nó quay lại, cần ghi thêm URL, request route và thao tác ngay trước lỗi để phân biệt upload webcam, Chat hoặc HMR.

## 5. Những file chưa được xóa và lý do

`v13.db`, các file `-wal`/`-shm`, bốn SQLite phụ, `escalation_log.jsonl`, `error_store.jsonl`, `bypass_log.jsonl`, `why_gate_audit.jsonl`, `intel_updates.jsonl` và thư mục `shadow` đều được giữ. Đây là dữ liệu sống hoặc bằng chứng có giá trị. Cách đúng là **rotation có giới hạn**, nén log cũ và giữ hash/manifest, không xóa thẳng.

Các thư mục benchmark và E2E có thể đưa vào archive sau khi chốt từng báo cáo. Chưa xóa vì chúng còn dùng để tái hiện các kết quả factual 0%, governance KILL và prompt injection BYPASSED.

## 6. Việc cần làm tiếp theo

Trước mắt cần thêm ba cơ chế: giới hạn kích thước ledger, rotation theo ngày hoặc theo số dòng; trạng thái rõ cho mọi rollback token (`pending`, `passed`, `failed`, `expired`, `reverted`); và intel ingest phải ghi rõ `source_http_status`, `parser_status`, `new_signatures_count`, `applied_count`.

Đối với Electron, cần build một bản production có CSP production thật rồi kiểm tra lại, thay vì chỉ chạy `electron .` trong chế độ dev. Cảnh báo CSP trong log cũ là dấu hiệu môi trường dev hoặc CSP chưa được bật; không nên dùng log dev để kết luận installer production đã an toàn.

## Tài liệu tham khảo

[1]: https://www.electronjs.org/docs/latest/api/web-contents "Electron webContents — console-message event"

[2]: https://www.electronjs.org/docs/latest/breaking-changes "Electron Breaking Changes"

[3]: https://chromium.googlesource.com/chromium/src/+/682206aafb5a1b9b3ae56099e2dc119311f3c3da/services/network/chunked_data_pipe_upload_data_stream.cc "Chromium ChunkedDataPipeUploadDataStream"
