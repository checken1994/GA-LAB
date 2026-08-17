# Cách áp dụng bộ tài liệu bảo vệ SCP

## Cảnh báo quan trọng

Đừng public repository ngay sau khi chép file. Bộ này là **bản nháp triển khai có cấu trúc**, chưa phải giấy phép thương mại đã ký và chưa thay thế việc luật sư rà soát.

## Bước 1 — Thay toàn bộ placeholder

Tìm và thay các chuỗi sau trong mọi file:

```text
[LEGAL COPYRIGHT HOLDER]
[LEGAL COPYRIGHT HOLDER / GA-LAB]
[OFFICIAL PROJECT EMAIL]
[OFFICIAL SECURITY EMAIL]
[OFFICIAL URL]
[PROJECT LOGO / WORDMARK]
[LEGAL ENTITY OR PERSON]
```

Nếu hiện tại bạn chưa có pháp nhân, ghi đúng tên cá nhân có quyền tác giả; không tự ghi “GA-LAB” như thể đó là công ty nếu chưa phải pháp nhân.

## Bước 2 — Chép đúng cấu trúc

```text
LICENSE
LICENSES.md
CONTRIBUTING.md
TRADEMARKS.md
COMMERCIAL_LICENSE_NOTICE.md
THIRD_PARTY_NOTICES.md
SECURITY.md
licenses/AGPL-3.0-only.txt
licenses/Apache-2.0.txt
```

Giữ nguyên toàn văn hai file trong `licenses/`. Không rút gọn, không dịch, không tự sửa nội dung AGPL hoặc Apache.

## Bước 3 — Kiểm tra boundary

Trước khi gắn Apache cho `dashboard/`, `desktop/`, `scp/api/` hoặc `scp/llm_gateway/`, kiểm tra import/dependency thật. Nếu component chứa logic core hoặc copy code AGPL, để `NOASSERTION` và rà soát thay vì gắn Apache theo mong muốn.

## Bước 4 — Kiểm tra quyền tác giả

Lập danh sách:

```text
- Code do chính bạn viết.
- Code do người khác đóng góp.
- Code copy từ GitHub/repository khác.
- Dependency, SDK, model, dataset, font, image.
- Code tạo bằng AI hoặc code generator.
```

Không hứa commercial license cho phần mà bạn không có quyền cấp lại. Nếu muốn bán bản thương mại bao phủ core, cần dùng CLA hoặc quyền chuyển nhượng phù hợp trước khi nhận thêm contribution vào core.

## Bước 5 — Quét secret trước khi public

Kiểm tra cả working tree và Git history. Tìm:

```text
.env
*.pem
*.key
id_rsa
password
secret
api_key
token
private
```

Nếu secret từng xuất hiện trong history, xóa file hiện tại là chưa đủ; phải xoay/revoke secret và làm sạch history trước khi public.

## Bước 6 — Tách thương hiệu

Tạo hoặc cập nhật README với câu:

```text
SCP DNA, SCP and GA-LAB names and logos are project marks.
Code rights are governed by the applicable component license.
See TRADEMARKS.md for permitted use.
```

Không cho fork dùng logo/tên “official” nếu chưa có phép bằng văn bản.

## Bước 7 — CI bắt buộc

Trước mỗi release, CI nên kiểm tra:

```text
1. Không có secret.
2. Mỗi source file có SPDX hoặc third-party notice.
3. Không có file AGPL bị gắn nhầm Apache.
4. THIRD_PARTY_NOTICES.md không còn TODO cho phần phát hành.
5. License files tồn tại đúng đường dẫn.
6. Release tag và commit hash được lưu.
```

## Bước 8 — Cách hiểu đúng “bảo vệ”

```text
AGPL       → quy tắc dùng/sửa/phân phối core
Apache     → mở rộng permissive cho component độc lập
Copyright  → quyền sở hữu code
Trademark  → bảo vệ tên/logo
CLA        → giữ khả năng dual/commercial licensing
Secret scan→ bảo vệ tài sản bí mật
Contract   → bảo vệ doanh thu/support/enterprise terms
```

Không có file license nào tự động ngăn mọi người fork public repository trên GitHub. GitHub cũng lưu ý public repository có thể được xem và fork; đổi private về sau không xóa fork/local copy đã tồn tại.

## Quyết định nên dùng cho SCP hiện tại

Nếu mục tiêu chính của bạn là **mở code nhưng không để người khác lấy core sửa rồi đóng kín toàn bộ dịch vụ**, dùng:

```text
scp/runtime, scp/autofix, scp/meta, scp/security, task_kernel
    → AGPL-3.0-only

connector, SDK, bridge độc lập
    → Apache-2.0

SCP/GA-LAB/logo
    → TRADEMARKS.md riêng

bản enterprise/commercial
    → hợp đồng riêng, sau khi kiểm tra quyền contributor
```
