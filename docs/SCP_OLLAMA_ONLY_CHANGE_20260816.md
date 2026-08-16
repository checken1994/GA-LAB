# SCP chuyển sang Ollama thật — 16/08/2026

## Kết luận ngắn

SCP đã được chuyển sang dùng **Ollama thật** tại `http://127.0.0.1:11434`. `llm-bridge` đã bị bỏ khỏi danh sách child service của `SCP-247-Supervisor`; Supervisor không còn cố khởi động Bun bridge trên port mà Ollama đang dùng.

Không xóa Ollama và không sửa file `.env` production.

## Thay đổi đã áp dụng

| Hạng mục | Trạng thái |
|---|---|
| Xóa service entry `llm-bridge` khỏi Supervisor | Đã làm |
| Giữ Ollama ở `127.0.0.1:11434` | Đã làm |
| Gán `OLLAMA_HOST=http://127.0.0.1:11434` cho child service | Đã làm |
| Ép `SCP_LLM_PROVIDER_MODE=ollama_only` cho child service | Đã làm |
| Giữ `LLM_BRIDGE_URL` chỉ như alias tương thích cũ | Đã làm; không khởi động bridge |
| Kiểm tra `/api/tags` trước khi Supervisor chạy | Đã làm; Ollama không khỏe thì Supervisor abort fail-closed |
| Backup trước khi sửa | Đã làm |
| Rollback | Có thể phục hồi file Supervisor và XML Scheduled Task từ backup |

## Bằng chứng trên PC thật

File Supervisor sau khi sửa có SHA-256:

```text
290114FC5386216B8DA7DF54E5E4956B10A8AABC91E38C0E0BE38D6052740894
```

Số entry runtime có dạng `Name = 'llm-bridge'` trong service map:

```text
0
```

Trạng thái Scheduled Task:

```text
SCP-247-Supervisor=Running
SCP-247-Recovery-Watchdog=Disabled
```

HTTP probe sau restart:

| Endpoint | Kết quả |
|---|---:|
| `http://127.0.0.1:3000/api/scp/health` | 200 |
| `http://127.0.0.1:3030/healthz` | 200 |
| `http://127.0.0.1:8000/health` | 200 |
| `http://127.0.0.1:11434/api/tags` | 200 |

Port `11434` vẫn do `ollama.exe` PID `8016` giữ. Đây là kết quả mong muốn.

Ledger của lần Supervisor mới nhất có:

```text
CURRENT_RUN_LLM_BRIDGE=0
CURRENT_RUN_PORT_OCCUPIED=0
CURRENT_RUN_CIRCUIT_OPEN=0
```

Smoke test hội thoại thật qua dashboard:

```text
HTTP_STATUS=200
RUN_ID=run-d44eea3a503b4b95b53b06d43637259c
VERDICT=PASS
```

## GitHub

Đã push commit:

```text
863264e — fix(runtime): use external Ollama instead of llm bridge
```

## Rollback

Backup nằm trong thư mục dạng:

```text
C:\Users\check\Downloads\scp\scp-audit\ollama-only-change-before-YYYYMMDD-HHmmss\
```

Nếu cần rollback, dừng `SCP-247-Supervisor`, phục hồi `scp_247_supervisor.ps1` từ backup, sau đó khởi động lại task. Không cần và không được xóa Ollama.

## Giới hạn còn lại

Thay đổi này giải quyết đúng xung đột port và việc Supervisor retry sai. Nó **không có nghĩa** Ollama luôn trả lời đúng mọi câu hỏi, cũng không có nghĩa toàn bộ SCP đã được chứng minh production-ready tuyệt đối. Những phần đó vẫn phải kiểm tra bằng smoke test, reality test và verifier riêng.
