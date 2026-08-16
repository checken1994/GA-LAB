# Kiểm tra dung lượng SCP — 16/08/2026

## Kết luận

Thư mục `C:\Users\check\Downloads\scp\desktop` chiếm khoảng **10.965 GB**. Nguyên nhân chính không phải một file đơn lẻ mà là **nhiều bản build desktop Electron bị giữ lại cùng lúc**. Có 9 thư mục build/snapshot; phần lớn chứa một thư mục `win-unpacked` khoảng 0.828–1.119 GB.

`.git` chiếm khoảng **1.158 GB**, trong đó pack đang dùng khoảng **1.07 GiB**. Kiểm tra Git cho thấy có ba blob lớn không còn được branch hiện tại tham chiếu, lần lượt khoảng **625.5 MB, 383.0 MB và 225.5 MB**. Ba object này là ứng viên lớn nhất để thu hồi, nhưng cần giữ backup Git trước khi prune vì việc này làm mất khả năng khôi phục bằng reflog đối với object đã bỏ.

## Desktop chiếm dung lượng ở đâu

| Thư mục | Dung lượng | Nhận xét |
|---|---:|---|
| `release` | 2.492 GB | Bản phát hành chính: x64 installer, portable installer và `win-unpacked` |
| `.private-release-worker-final` | 1.698 GB | Bản build thử/đóng gói cũ, có `win-unpacked` và portable EXE |
| `.private-release-current` | 1.454 GB | Snapshot build cũ |
| `.private-release-filtered` | 1.210 GB | Snapshot build cũ |
| `.private-release` | 1.211 GB | Snapshot build cũ |
| `.private-release-desktop-fix` | 1.072 GB | Snapshot build sửa desktop cũ |
| `.private-release-worker-current` | 1.072 GB | Snapshot build worker cũ |
| `runtime` | 0.755 GB | Các executable runtime SCP và dashboard |
| `node_modules` | Không tính trong desktop | Là reparse point/junction; dữ liệu nằm ngoài vùng đo |

Các file đơn lẻ lớn nhất gồm:

| File | Dung lượng |
|---|---:|
| `release\SCP-DNA-Control-Center-1.6.0-x64.exe` | 686 MB |
| `release\SCP-DNA-Control-Center-1.6.0-portable.exe` | 686 MB |
| `.private-release-worker-final\SCP-DNA-Control-Center-1.6.0-portable.exe` | 626 MB |
| `.private-release-current\SCP-DNA-Control-Center-1.6.0-portable.exe` | 626 MB |
| `.private-release\SCP-DNA-Control-Center-1.6.0-portable.exe` | 383 MB |

## `.git` và cache

| Vùng dữ liệu | Dung lượng | Đánh giá |
|---|---:|---|
| `.git` tổng | 1.158 GB | Lớn; cần dọn có backup |
| `.git` pack đang dùng | 1.07 GiB | Chủ yếu do các object binary cũ |
| `.mypy_cache` | 0.303 GB | Cache có thể xóa, sẽ tự tạo lại |
| `dashboard\node_modules` | 0.666 GB | Có thể tạo lại bằng package manager |
| `desktop\node_modules` | 0.450 GB | Có thể tạo lại; hiện là dữ liệu build dependency |
| `data` | 0.190 GB | Không nên xóa toàn bộ; có ledger/runtime/evidence |
| `.pytest_cache` | Rất nhỏ | Có thể xóa |

Git hiện báo `prune-packable=0` và `garbage=0`, nghĩa là Git không tự xem các object này là rác bình thường trong chu kỳ hiện tại. Tuy nhiên `git fsck --unreachable` xác nhận ba blob lớn không còn reachable từ branch/tag hiện tại. Không nên chạy `git gc --prune=now` trước khi tạo backup hoặc bundle.

## Cách tối ưu an toàn

### Có thể làm trước, rủi ro thấp

Có thể xóa các cache có thể tái tạo như `.mypy_cache`, `.pytest_cache`, và sau khi dừng các tiến trình Node/Bun thì xóa `dashboard\node_modules` hoặc `desktop\node_modules` rồi cài lại khi cần. Những việc này không xóa mã nguồn, database hay lịch sử Git.

### Cần chọn bản build trước khi dọn

Nên giữ `desktop\release` vì đây là bản phát hành mới nhất, giữ `desktop\runtime` vì SCP đang dùng runtime đóng gói, và giữ tối đa một snapshot rollback. Các thư mục `.private-release-*` còn lại là ứng viên dọn lớn nhất. Tuy nhiên không nên tự động xóa tất cả vì chúng có thể là bằng chứng build hoặc bản rollback.

Cách an toàn là **di chuyển** các snapshot cũ vào thư mục quarantine có timestamp trên ổ D, kiểm tra SCP vẫn khởi động, rồi mới xóa sau thời gian quan sát. Di chuyển an toàn hơn xóa trực tiếp vì còn rollback.

### Tối ưu `.git`

Có hai mức:

1. `git gc --auto` hoặc `git repack` thông thường thường chỉ tối ưu nhẹ, không chắc thu hồi ba blob lớn.
2. Muốn thu hồi mạnh, cần tạo bundle/backup trước, lưu lại hash hiện tại, kiểm tra stash/tag, sau đó mới expire reflog và prune unreachable object. Cách này có thể giảm khoảng **1.2 GB** nếu ba blob lớn thật sự không cần giữ, nhưng không được làm nếu chưa có backup Git.

Không nên dùng `git reset --hard`, xóa `.git`, hoặc xóa toàn bộ `data` để giảm dung lượng.

## Trạng thái đã thực hiện

Đã chỉ đọc và đo dung lượng. **Chưa xóa hoặc di chuyển file nào.** Các file báo cáo đo được lưu trong `scp-audit` trên PC; những file này có thể xóa riêng sau khi kiểm tra nếu muốn.

## Evidence chính

Các phép đo được chạy trên PC thật bằng PowerShell. Dữ liệu gồm tổng byte, số file, dung lượng từng thư mục cấp một, file lớn nhất, trạng thái reparse point, `git count-objects`, `git fsck --unreachable` và `git verify-pack`.
