# AutoFix Fixture Evidence: Rollback Giữ Đúng Byte Trên Windows

## Vấn đề phát hiện thật

Runner có sẵn `scripts/ops/autofix_e2e_fixture_test.py` được chạy trong vùng private fixture, ngoài source `scp/` và ngoài data production. Lần chạy đầu **fail exit 14**: deterministic patch được áp dụng, nhưng hash sau rollback không bằng hash trước patch.

Đây là một lỗi thật của rollback contract, không phải lỗi test. Fixture gốc dùng CRLF. `filepath.read_text()` đã đổi CRLF thành LF trước khi nội dung được lưu vào rollback registry; registry lại restore với `newline=""`. Kết quả là text có vẻ giống, nhưng byte hash sau rollback khác byte hash trước. Điều này làm evidence `regression-free/rollback` không đáng tin trên Windows.

## Recovery an toàn

Fixture lỗi chỉ nằm trong `.private-secrets/release-audit/scp-247/autofix-fixture`. Trước khi khôi phục, bản fixture đã patch được sao lưu vào `scp-audit/telemetry-terminal-20260817-191901/fixture_xss.after-failed-rollback.py`.

Khôi phục fixture dùng đúng string literal `original` của runner qua AST và `Path.write_text`, sau đó SHA-256 trở lại chính xác hash trước run:

| Điều kiện recovery | Kết quả |
|---|---|
| Fixture trước run có hash đã lưu | Có |
| Fixture sau failed rollback được backup | Có |
| Fixture được dựng lại theo code runner | Có |
| Hash sau recovery = hash trước run | PASS |
| Source/data production thay đổi bởi recovery | Không |

## Bản vá

Commit GitHub **`8ae97a5`** thay đổi `scp/autofix/engine.py` theo hai điểm hẹp:

1. Đọc `_pre_fix_content` bằng `filepath.open(..., newline="")` để giữ nguyên CRLF/LF.
2. Khi rollback syntax-failure trong deterministic XSS path, ghi lại với `newline=""`.

Registry rollback vốn đã dùng `newline=""`. Patch làm đầu vào và đầu ra cùng contract byte/line-ending, không thay đổi policy tier, allowlist, quyền AutoFix hoặc logic LLM.

## Retest trên PC thật

| Postcondition | Kết quả |
|---|---|
| Preview không sửa fixture | `True` |
| Policy malicious fixture bị chặn | `False` cho `policy_malicious_allowed` |
| Deterministic apply | `fixed` / `patched=True` |
| Rollback được gọi | `True` |
| `before_hash == after_rollback_hash` | **True** |
| Regression Python sau patch | **101 passed**, 2 warnings |
| Portable reality suite sau patch | **74/74 pass**, 0 fail, 0 timeout |

## Verdict đúng phạm vi

**VERIFIED cho fixture deterministic XSS trong staging/private audit.** Điều này đóng lỗi byte-preservation của rollback trên đường đã chạy. Nó **không** chứng minh AutoFix đã an toàn với mọi file, mọi bug, LLM-generated patch, policy production, hoặc workload production. Những phạm vi đó vẫn cần candidate/artifact/verifier riêng.
