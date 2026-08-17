# BFLA Evidence — `/v105/ask/stream` — 17/08/2026

## Finding thật

Khi cập nhật external security audit để quét các router đã tách khỏi `api_server.py` và `verify_admin` canonical trong `scp/security/auth.py`, audit phát hiện:

| Mục | Trước patch |
|---|---|
| Route | `POST /v105/ask/stream` |
| Runtime wiring | `api_server.py` có `app.include_router(stream_router)` |
| Auth | Không có `Depends(verify_admin)` |
| Rủi ro | Bất kỳ client truy cập được backend có thể bắt đầu SSE judge stream mà không qua admin token |

Router từng tự mô tả là “dead route”, nhưng source runtime hiện đã include nó. Vì vậy đây là **BFLA thực**, không phải cảnh báo giả.

## Bản vá tối thiểu

`scp/api/routes/stream_routes.py` nay import `Depends` và `verify_admin`, rồi dùng:

```python
@router.post("/v105/ask/stream", dependencies=[Depends(verify_admin)])
```

Dependency chạy trước generator SSE. Không token hợp lệ thì route phải trả `401`, không được khởi tạo judge stream.

External audit cũng được sửa để kiểm tra route từ `scp/api/routes/*.py` và implementation canonical `scp/security/auth.py`, thay vì chỉ đòi hàm còn nằm ở layout `api_server.py` cũ.

## Evidence sau patch trên PC

| Kiểm tra | Kết quả |
|---|---|
| Compile `stream_routes.py` và audit | PASS |
| External audit security | `2 passed, 2 skipped` |
| Runtime POST `/v105/ask/stream` không token | **HTTP 401** |
| Supervisor reload | Controlled restart; ledger `START` rồi `HEALTHY` cho 4 child service |
| HTTP recovery | Dashboard, scheduler, backend, Ollama đều `200` sau recovery |
| Full pytest | `101 passed` |
| Portable reality suite | `74/74 pass`, `0 fail`, `0 timeout` |

## Ranh giới kết luận

Patch này chứng minh route stream không token bị chặn trong runtime Windows vừa kiểm tra. Nó **không** chứng minh mọi route, mọi proxy hay mọi network path đã qua full chaos/security gate. Các blocker policy production, external truth, source reproducibility và chaos profile vẫn giữ nguyên.
