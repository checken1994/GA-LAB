# SCP runtime source — Reproducible release R41

**Repository:** [`checken1994/GA-LAB`](https://github.com/checken1994/GA-LAB)  
**Commit:** `2137cf3abf26611f737b4d3a8e5fb51fc93346f3`  
**Ngày:** 14/08/2026 (GMT+7)

## Vì sao runtime từng không xuất hiện?

Trong `.gitignore` cũ có rule tổng quát:

```text
**/runtime/
```

Rule này đúng khi áp dụng cho generated runtime, packaged runtime và build output, nhưng **quá rộng** khi áp dụng vào `scp/runtime/`. Kết quả là toàn bộ Python runtime source của SCP bị ignore, dù backend vẫn import và dùng các module đó trên PC thật.

Đây là lỗi phân loại artifact, không phải bằng chứng runtime không cần thiết.

## Runtime nào đã được publish?

Commit R41 publish **55 source/document files** trong `scp/runtime/`, gồm:

- Python orchestration và verification source.
- `engine_parts/`, `judge_parts/`, `slms_parts/`.
- SLM implementations và storage/timing modules.
- `SLM_NAMING_NOTE.md`.

Source được lấy từ PC thật và compile bằng Python venv của SCP trước khi push. Không publish:

- `__pycache__/` và `.pyc`.
- `*.bak`, snapshot backup hoặc patch scratch.
- SQLite, JSONL runtime ledger, logs.
- `.env`, provider keys, auth/token secrets.
- `desktop/runtime/` packaged binaries hoặc installer output.

## Ignore policy mới

`scp/runtime/` là **versioned source**; build/runtime-generated folders khác vẫn bị ignore. Các exception mới là:

```text
!scp/runtime/
!scp/runtime/**
scp/runtime/**/__pycache__/
scp/runtime/**/*.pyc
```

Điều này tách ba khái niệm vốn bị trộn trước đây:

| Loại | GitHub | Lý do |
|---|---|---|
| Runtime source `scp/runtime/*.py` | Có | Cần để người khác checkout và chạy/reproduce SCP |
| Packaged runtime `desktop/runtime/*` | Không mặc định | Generated distribution artifact, cần release bundle/hash riêng |
| Runtime state `data/*`, SQLite, JSONL, logs | Không | Dữ liệu máy chạy, có thể chứa secret/PII/state không reproducible |
| Environment `.env` | Không | Chứa secret; chỉ `.env.example` được publish |

## Cách người khác dùng sau khi checkout

1. Clone repo GA-LAB.
2. Cài Python 3.12+, Node.js và Bun theo README.
3. Chạy `install-scp.bat` trên Windows hoặc cài dependencies tương đương.
4. Tạo `.env` local từ `.env.example`, điền secrets ở local/secret files.
5. Đảm bảo năm dangerous flags bằng `0` trước production run.
6. Chạy `start-scp.bat` hoặc Electron launcher.
7. Chạy `python -m pytest -q` và portable reality runner theo README.

Runtime state được tạo mới trong `data/`; người dùng không cần tải database/ledger của PC tác giả để chạy source.

## Reality verification

- R41 remote HEAD: `2137cf3abf26611f737b4d3a8e5fb51fc93346f3`.
- Remote tree có 55 file trong `scp/runtime/`.
- Remote tree không có `__pycache__`, `.pyc` hoặc `.bak` trong runtime.
- Runtime source trên PC đã compile thành công bằng Python venv.
- Worktree publish tạm đã được cleanup; working tree chính không bị reset hay overwrite.

## Kết luận

SCP trước đây có thể bị checkout thiếu runtime source vì ignore rule quá rộng. R41 đã sửa đúng lớp packaging: **source được publish, state và secret không publish**. Đây là cách để PC khác có thể dùng SCP mà vẫn giữ security boundary.
