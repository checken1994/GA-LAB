# SCP Canonical Development Root

## Quyết định

Từ snapshot ngày 2026-08-26, **GA-LAB là repository và thư mục phát triển canonical duy nhất** của SCP. Trên Windows, thư mục làm việc chuẩn là `C:\Users\check\Downloads\scp`. Mọi thay đổi mới phải bắt đầu từ `main` của `checken1994/GA-LAB`, đi qua branch/worktree cô lập, CI, merge fast-forward và đồng bộ lại thư mục chuẩn.

Hai thư mục phát triển phụ trước đây đã được archive và xóa khỏi máy theo yêu cầu. Archive recovery nằm ngoài repository tại `C:\Users\check\Downloads\scp-folder-archives-20260826\`; archive đó không phải workspace phát triển và không được đưa vào GitHub.

## Repository phụ `scp-agent`

`checken1994/scp-agent` là một nguồn tham khảo đã được clone read-only để so sánh. Nó **không** được coi là workspace thứ hai và **chưa** được merge nguyên trạng. So sánh hiện tại ghi nhận 475 path chung, 435 blob giống nhau, 40 blob khác nhau, 214 path chỉ có ở nguồn phụ và 697 path chỉ có ở GA-LAB.

Danh sách port có kiểm soát nằm tại `reports/PORT_BACKLOG_SCP_AGENT_TO_GA_LAB_20260826.json`. Mỗi mục phải có quyết định riêng về tương thích, license/provenance, test focused, CI và runtime evidence. Không dùng copy toàn bộ, không dùng `git reset`, và không thay thế kernel/Hands/ledger hiện tại bằng code chưa kiểm chứng.

## Quy tắc chống tái tạo workspace rác

Không tạo lại thư mục `scp-agent-structure-debt` hoặc `scp-structure-debt-worktree` dưới `Downloads`. Nếu cần thử nghiệm, dùng Git worktree tạm trong sandbox hoặc một branch được đặt tên rõ ràng; sau khi hoàn thành phải có cleanup evidence. Tệp chưa track `_agent_*` tại canonical root là artifacts được giữ để provenance, không phải nguồn phát triển và không được tự ý xóa.

## Cách xác nhận đang ở đúng root

```bash
git remote get-url origin
git branch --show-current
git rev-parse HEAD
git status --short
python3 tools/verify_canonical_root.py
```

Validator chỉ kiểm tra các invariant an toàn: remote canonical, branch không bị detached, không có path workspace phụ trong root, và không có nested `.git` ngoài thư mục Git metadata của root. Nó không khẳng định mọi tính năng đã hoàn thiện.

## Trạng thái claim

Canonical-root consolidation đã hoàn tất ở cấp **filesystem/process policy** và được kiểm tra bằng việc archive/hash/xóa hai workspace cũ, sync root với `origin/main`, và full smoke sau sync. Code từ `scp-agent` chỉ được coi là đã hợp nhất khi có commit riêng, test và evidence tương ứng; backlog còn mở không phải lỗi bị che giấu mà là danh sách port có chủ ý.
