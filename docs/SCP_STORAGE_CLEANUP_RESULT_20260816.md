# Kết quả dọn dung lượng SCP — 16/08/2026

## Phạm vi đã xóa

Đã xóa theo phương án A sau khi tạo manifest trước thao tác:

- Sáu thư mục build snapshot `.private-release-*` trong `desktop`.
- `.mypy_cache` và `.pytest_cache`.
- `dashboard\node_modules`.
- Junction `desktop\node_modules` và target tương ứng trên ổ D.

Không xóa các vùng được bảo vệ:

- `desktop\release`.
- `desktop\runtime`.
- `.git`.
- `data`.
- `scp` và mã nguồn.
- Database, ledger và file `.env` production.

## Dung lượng trước và sau

| Vùng | Trước | Sau | Đã giảm |
|---|---:|---:|---:|
| Toàn bộ `C:\Users\check\Downloads\scp` | 12.645 GB | 4.636 GB | 8.008 GB |
| `desktop` | 10.965 GB | 3.247 GB | 7.718 GB |

Git pack vẫn còn khoảng 1.07 GiB. Phần này chưa dọn vì là lịch sử Git; muốn giảm tiếp phải tạo backup/bundle rồi mới prune object không còn dùng.

## Kiểm tra sau dọn

Các đường dẫn được xóa đều đã xác nhận không còn. Các đường dẫn được giữ đều còn tồn tại.

Supervisor đã được khởi động lại:

```text
SCP-247-Supervisor=Running
```

HTTP probe:

```text
http://127.0.0.1:3000/api/scp/health = 200
http://127.0.0.1:3030/healthz = 200
http://127.0.0.1:8000/health = 200
http://127.0.0.1:11434/api/tags = 200
```

Smoke test hội thoại sau khi dọn:

```text
HTTP_STATUS=200
RUN_ID=run-fbd7883736fe4dfbba3c32358c9712e0
VERDICT=PASS
```

Lần thử đầu sau khi restart bị đóng kết nối giữa chừng; Supervisor đã tự restart dashboard. Lần thử lại sau khi hệ thống ổn định đã PASS. Đây là lý do không coi lần lỗi đầu là bằng chứng hệ thống hỏng hoàn toàn.

## Rollback

Manifest trước khi xóa nằm trong:

```text
C:\Users\check\Downloads\scp\scp-audit\storage-cleanup-before-YYYYMMDD-HHmmss.json
```

Các build snapshot và node_modules đã xóa không được backup thành bản sao vì chúng là build/cache có thể tạo lại từ mã nguồn và lockfile. Nếu cần cài lại dependency:

```powershell
cd C:\Users\check\Downloads\scp\dashboard
bun install

cd ..\desktop
bun install
```

Không chạy lại lệnh cài dependency khi chưa cần, vì nó sẽ tạo lại khoảng 1 GB node_modules.
