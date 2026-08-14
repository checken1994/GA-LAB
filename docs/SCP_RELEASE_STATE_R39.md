# SCP DNA — Release state R39

**Repository:** [`checken1994/GA-LAB`](https://github.com/checken1994/GA-LAB)  
**Commit source:** `17f340283b7e8f314777f30b6a1fddfd1145e5ec`  
**Ngày cập nhật:** 14/08/2026 (GMT+7)  
**Thiết bị evidence:** Windows 11 PC thật của người dùng

## Current decision

SCP đang ở trạng thái **HARDENED PRODUCTION-CANDIDATE**. Core pipeline và packaged auth contract đã có evidence tốt trên PC thật, nhưng chưa gọi là production-ready hoàn toàn vì runtime `.env` chính chưa được promote về safe flags, installer chưa có Authenticode signing và chưa có deployment evidence trên PC Windows thứ hai.

## Verified current evidence

| Gate | Result |
|---|---:|
| Repository HEAD | R39, local/remote đã đối chiếu |
| Pytest | 55 passed, 0 failed |
| Portable reality suite | 73 passed, 0 failed, 0 timeout, 0 error |
| Packaged R39 artifact | `desktop/runtime/scp-backend.exe` |
| Packaged R39 SHA-256 | `F599AE9087B507C7FE155BB27DF817A1EF3B72C5085EC8019A619D83252DB243` |
| Safe runtime flags | `0,0,0,0,0` |
| Safe runtime health | HTTP 200 |
| Safe runtime missing/wrong/correct auth | HTTP 401 / 401 / 200 |
| Safe run cleanup | test port/process closed |
| Firewall after change window | loopback TCP/UDP và outbound đều Enabled + Block |
| Evolution R39 | SUCCESS, bugs found/fixed `1/1`, verified/stored `1/1` |
| Durable learning | 6 lessons, 4 evolved patterns |

## Configuration boundary

File `.env` thật trên PC **không được đưa lên GitHub** và không được ghi nội dung secret vào tài liệu. Runtime candidate an toàn có năm dangerous flags bằng `0`:

```text
SCP_DEV_MODE=0
SCP_SKIP_STARTUP_GATE=0
SCP_AUTO_APPROVE_TIER3=0
SCP_TIER3_ALLOW_RELAXATION=0
SCP_TIER3_ALLOW_BAREEXCEPTPASS=0
```

Candidate đã được dùng để chạy packaged R39 với auth contract `200/401/401/200`. Việc promote candidate thành `.env` runtime chính là change operation riêng, có backup/rollback và không tự động thực hiện bằng commit tài liệu.

## Distribution state

Installer được rebuild sau khi phát hiện bản installer cũ chứa backend hash khác R39. Bản rebuild đã được cài thử trong thư mục isolated trên Windows PC thật, exit `0`, tạo 1.453 files, backend bên trong khớp hash R39 và app smoke-launch được. Installer hiện chưa được chứng minh trên PC Windows thứ hai và chưa có publisher Authenticode signature.

## Data and secret policy

`.env`, provider keys, auth/password/token files, SQLite runtime state, JSONL ledgers, logs, private backups, `desktop/runtime` và generated installer output phải nằm ngoài Git history. Repository chỉ lưu `.env.example`, source, tests, sanitized documentation và metadata evidence.

## Known remaining work

1. Promote safe runtime configuration có backup/rollback.
2. Ký installer/backend bằng chứng thư publisher và verify chain.
3. Cài/test trên PC Windows thứ hai.
4. Mở rộng adversarial corpus: prompt injection, malicious patch, provider poisoning, replay và tamper ledger.
5. Phân loại/commit các local patches ngoài R39 theo từng evidence boundary; không bulk-commit working tree.
