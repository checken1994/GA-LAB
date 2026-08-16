# Script dọn dòng trống ledger SCP

Script:

```text
scripts/clean_jsonl_blank_lines.py
```

Script đã kiểm tra cú pháp và chạy thử với fixture tạm. Nó không tự động sửa ledger thật.

## Vì sao phải dừng writer trước khi dọn

Ledger được ghi bởi Supervisor/service. Script dọn dùng atomic replace. Nếu Supervisor vẫn append đúng lúc thay file, các dòng mới có thể nằm ở file cũ hoặc bị mất trong lúc thay thế. Vì vậy phải dừng/disable writer trước khi dùng `--apply`, rồi kiểm tra postcondition, sau đó mới bật lại.

## Dry-run an toàn

```powershell
cd C:\Users\check\Downloads\scp
python scripts\clean_jsonl_blank_lines.py `
  --ledger .private-secrets\release-audit\scp-247\supervisor-ledger.jsonl `
  --check-json
```

Dry-run chỉ đếm dòng và hash, không đổi file.

## Apply có backup

Chỉ chạy khi Supervisor và Watchdog đã dừng/disable:

```powershell
python scripts\clean_jsonl_blank_lines.py `
  --ledger .private-secrets\release-audit\scp-247\supervisor-ledger.jsonl `
  --backup-dir .private-secrets\release-audit\scp-247\ledger-cleanup-backups `
  --check-json `
  --apply
```

Script sẽ:

1. Từ chối file không tên `supervisor-ledger.jsonl`, trừ khi có `--force`.
2. Đếm dòng trống và kiểm tra từng dòng không trống có phải JSON hợp lệ không.
3. Tạo backup timestamp trước khi sửa.
4. Ghi file tạm cùng thư mục, flush và `fsync`.
5. Thay file bằng `os.replace`.
6. Đọc lại để xác nhận không còn dòng trống và số dòng JSON không đổi.
7. Nếu postcondition lỗi, tự chép backup trở lại.

## Rollback thủ công

Lấy file `.before-clean.bak` mới nhất trong thư mục backup, dừng writer, rồi chép ngược về tên ledger gốc. Không dùng `git clean` để xóa evidence.

## Kết quả kiểm thử fixture

Fixture có 4 dòng, trong đó 2 dòng trống và 2 JSON hợp lệ. Dry-run báo `BLANK_LINES=2`, `INVALID_JSON_LINES=0`; apply tạo 1 backup, kết quả còn 2 dòng và `AFTER_BLANK_LINES=0`.
