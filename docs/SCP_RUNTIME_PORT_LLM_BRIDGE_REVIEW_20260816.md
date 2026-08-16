# Runtime port và llm-bridge review — 16/08/2026

## 1. HTTP probe thật

Probe được chạy trực tiếp trên PC Windows bằng `Invoke-WebRequest`, không chỉ kiểm tra TCP listener.

| Port | Endpoint chuẩn dùng để probe | Kết quả | Diễn giải |
|---:|---|---:|---|
| 3000 | `/api/scp/health` | HTTP 200 | Dashboard proxy và chuỗi health SCP phản hồi đúng; body báo `overall=true` |
| 3000 | `/` | HTTP 200 | Dashboard production đang phục vụ HTML |
| 3030 | `/healthz` | HTTP 200 | Loop scheduler có endpoint readiness đúng |
| 3030 | `/health` | HTTP 404 | Không phải endpoint chuẩn của loop scheduler |
| 3030 | `/` | HTTP 200 | Service info phản hồi; body cho biết `running=false` tại thời điểm probe |
| 8000 | `/health` | HTTP 200 | Python backend phản hồi |
| 8000 | `/health/detailed` | HTTP 200 | Backend detailed health phản hồi |
| 11434 | `/api/tags` | HTTP 200 | Listener Ollama-compatible phản hồi |
| 11434 | `/` | HTTP 200 | Body là `Ollama is running` |
| 11434 | `/health` và `/healthz` | HTTP 404 | Ollama không dùng hai path này |

File evidence trên PC:

```text
C:\Users\check\Downloads\scp\scp-audit\http-probe-20260816-102017.json
```

## 2. Script dọn ledger

Script mới:

```text
scripts/clean_jsonl_blank_lines.py
```

Mặc định script chỉ dry-run. Nó chỉ được apply khi có `--apply`, từ chối file không tên `supervisor-ledger.jsonl` nếu không có `--force`, kiểm tra JSON, tạo backup timestamp, ghi file tạm cùng thư mục, `fsync`, atomic replace và đọc lại để kiểm tra postcondition.

Fixture tạm đã kiểm chứng:

```text
TOTAL_LINES=4
BLANK_LINES=2
NONBLANK_LINES=2
INVALID_JSON_LINES=0
ACTION=DRY_RUN_NO_FILE_CHANGED
ACTION=APPLIED
AFTER_LINES=2
AFTER_BLANK_LINES=0
BACKUPS=1
```

**Chưa apply vào ledger thật.** Trước khi apply ledger thật phải stop/disable Supervisor và Watchdog để không có writer append đồng thời. Sau đó chạy dry-run, apply, kiểm tra hash/backup, rồi bật lại.

## 3. Nguyên nhân thật của llm-bridge `CIRCUIT_OPEN`

### Bằng chứng ledger

Toàn bộ record `service=llm-bridge` có:

| Event/reason | Số lần |
|---|---:|
| `PORT_OCCUPIED` / `listener_exists_before_supervisor_start` | 27 |
| `RESTART` / `health_failure` | 25 |
| `CIRCUIT_OPEN` / `restart_budget_exhausted` | 187 |

Các `CIRCUIT_OPEN` ghi `restart_count=5`. Supervisor có cấu hình `MaxRestartsPerWindow=5` và `RestartWindowSeconds=900`, tức tối đa 5 lần restart trong cửa sổ 15 phút. Sau khi đủ 5 lần, nó mở circuit và không restart thêm.

### Owner thật của port 11434

Probe TCP/process trên PC cho thấy:

```text
port 11434 owner PID=8016 name=ollama.exe
```

HTTP probe trên cùng port trả:

```text
GET /           -> 200 Ollama is running
GET /api/tags   -> 200
```

Vì vậy port 11434 đang do **Ollama thật** giữ, không phải Bun `llm-bridge`. PID `23588` trong ledger là PowerShell Supervisor đã chạy từ khoảng 09:32:46; nó không phải một llm-bridge process đang lắng nghe port.

### Chuỗi lỗi

Supervisor hiện khai báo service:

```text
llm-bridge -> port 11434 -> GET http://127.0.0.1:11434/api/tags
```

Khi Supervisor khởi động, Ollama đã nghe port 11434. `Start-ScpService` thấy port đã bị chiếm và ghi:

```text
PORT_OCCUPIED / listener_exists_before_supervisor_start
```

Sau đó runtime entry của llm-bridge là `null`, nên vòng monitor coi process llm-bridge không sống. Nó ghi `health_failure`, tăng restart history và thử start lại. Mỗi lần thử vẫn gặp port occupied. Khi đủ 5 lần trong 900 giây, Supervisor ghi `CIRCUIT_OPEN`. Vòng monitor tiếp tục ghi `CIRCUIT_OPEN` mỗi khoảng 15 giây; đó là lý do con số tăng lên 187.

Đây **không phải bằng chứng OpenRouter 429, Groq fail hoặc model trả lời sai**. Nó là lỗi hợp đồng port/process: hai thành phần cùng muốn dùng 11434, và Supervisor không phân biệt được “listener tương thích bên ngoài đang khỏe” với “process con của Supervisor chưa khởi động”.

### Vì sao không có log llm-bridge riêng

Thư mục log Supervisor có log cho dashboard, loop-scheduler, scp-python và autofix-worker, nhưng không có `llm-bridge.out.log`/`llm-bridge.err.log` mới. Điều này phù hợp với chuỗi trên: bridge bị chặn ở bước `PORT_OCCUPIED` trước khi `Start-Process` tạo child process và file log.

## 4. Cách sửa đúng, chưa tự áp dụng

Có ba lựa chọn, chỉ nên chọn một:

| Lựa chọn | Cách làm | Rủi ro |
|---|---|---|
| Dùng Ollama thật | Bỏ `llm-bridge` khỏi danh sách service Supervisor khi `LLM_PROVIDER=ollama` hoặc khi owner 11434 là Ollama được allowlist | Cần sửa health contract để kiểm tra owner + HTTP |
| Dùng llm-bridge | Chuyển bridge sang port khác, ví dụ 11435, và đổi `LLM_BRIDGE_URL`/client contract đồng bộ | Cần sửa nhiều config và kiểm tra firewall |
| Adopt có kiểm soát | Khi port 11434 đã có Ollama, Supervisor xác minh PID/path/HTTP `/api/tags`, ghi `EXTERNAL_ADOPTED`, không restart child | Phải có allowlist process owner; không được adopt listener bất kỳ |

Lựa chọn an toàn nhất với PC hiện tại là **dùng Ollama thật trên 11434 và không khởi động llm-bridge trùng port**. Không nên kill Ollama vì Ollama đang là provider hợp lệ mà SCP dùng được.

## 5. Kết luận

Tại thời điểm kiểm tra, cả bốn nhóm dịch vụ đều có HTTP response đúng endpoint của mình. Tuy nhiên `11434` đang là Ollama thật, còn Supervisor vẫn xem đó là `llm-bridge` phải tự sinh process. Health tổng thể có thể xanh trong khi process ownership sai; đây chính là lý do ledger ghi rất nhiều `CIRCUIT_OPEN`.

**Không nên sửa bằng cách tăng restart budget.** Tăng từ 5 lên 20 chỉ làm log dài hơn và retry port conflict lâu hơn. Cần sửa service discovery/port ownership trước.

**Ngày:** 16/08/2026  
**Tác giả:** Manus AI
