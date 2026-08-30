# GA-LAB / scp-agent Structural-Debt Compatibility Matrix

- **GA-LAB worktree:** `structure-debt-pc`, HEAD `06e1cef2e6c7c44bf23c354b0a106f93b72cd273`
- **Verified source:** `scp-agent`, commit `cb132a5af9f0dbcc6293b939ab32136cef22593c`
- **Purpose:** map only real counterpart seams before porting; no whole-directory copy.

| Patch từ scp-agent | Counterpart trong GA-LAB | Quyết định | Lý do |
|---|---|---|---|
| K-1 latest fencing token | Không có `scp/task_kernel.py`, `scp/core/task_kernel.py`, `ask_kernel_adapter.py` hoặc lease kernel trong GA-LAB checkout | **Không port** | Thêm kernel mới sẽ là tính năng/kiến trúc mới, không phải port có chứng cứ |
| J-1 KB short-circuit state scope | Có trong `scp/runtime/judge_parts/judgecore_mixin.py`, monolith; `locals().get` quanh dòng 432 | **Port tương thích** | Giữ local flow hiện có, khởi tạo default rồi đọc biến trực tiếp |
| J-2 speculative evidence scope | Có trong monolith: tạo evidence quanh dòng 1436, merge bằng `dir()` quanh dòng 1681 | **Port tương thích** | Khởi tạo `verdict_evidence_spec = None`, merge bằng điều kiện explicit |
| Windows cascade import | Có `scp/tests/external_audit/test_cascade.py`, hardcode PATH POSIX | **Port tương thích** | Giữ PATH/biến hệ thống native; không đổi product runtime |
| Judge phase façade/state refactor | GA-LAB vẫn dùng `judgecore_mixin.py` monolith; không có phase modules tương ứng | **Không copy** | Cần một đợt refactor riêng với characterization tests; copy sẽ phá API/behavior |
| PC verification evidence | Có thể ghi record riêng trong worktree | **Port tài liệu** | Ghi provenance và giới hạn, không giả vờ GA-LAB đã đạt scp-agent parity |

## Quy tắc merge

Chỉ các dòng được đánh dấu **Port tương thích** mới được sửa trong worktree. K-1 và phase façade/state giữ ở `scp-agent`; không tạo file giả để làm matrix xanh. Sau port phải chạy compile, collection, characterization/full test và runtime ở port 8000 trước khi đưa thay đổi vào GA-LAB `main`.
