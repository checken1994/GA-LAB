# SCP repository layout

Tài liệu này là **hợp đồng bố cục canonical** của repository `checken1994/GA-LAB`. Mục tiêu là để người dùng và CI luôn biết một file thuộc source, hướng dẫn vận hành, lịch sử, evidence hay công cụ tạm thời. Không dùng số lượng file hoặc số thư mục để tuyên bố hệ thống đã hoàn thiện.

## Nguyên tắc

1. **Root là cửa vào, không phải kho lịch sử.** Root chỉ giữ README, chính sách GitHub, cấu hình test và launcher tương thích cần chạy bằng double-click.
2. **Một chức năng chỉ có một bản canonical.** Bản copy cũ không được giữ ở root nếu đã có bản active trong `scripts/ops`, `scripts/maintenance` hoặc `docs`.
3. **Code active và patch lịch sử tách biệt.** Code đang chạy nằm trong `scp/`, `dashboard/`, `mini-services/`; helper đang dùng nằm trong `scripts/ops` hoặc `scripts/maintenance`; patch one-off nằm trong `scripts/maintenance/legacy`.
4. **Evidence không phải source.** Kết quả test, snapshot, log đã sanitize và report được đưa vào `reports/` hoặc `docs/evidence/`, không để ở root.
5. **Di chuyển không đồng nghĩa xóa mất lịch sử.** Git history là provenance của các file đã loại khỏi đường dẫn cũ; artifact có giá trị điều tra được giữ trong archive/private evidence theo chính sách secret.

## Bố cục canonical

| Khu vực | Nội dung được phép | Không đặt vào đây |
|---|---|---|
| `/` | `README.md`, `CONTRIBUTING.md`, `SECURITY.md`, `LICENSE`, `.env.example`, `.gitignore`, `pytest.ini`, launcher root tương thích | Audit round, report, patch one-off, raw evidence, log |
| `/scp/` | Python package và runtime source | Patch tạm, bản backup `.bak`, log |
| `/dashboard/`, `/mini-services/` | Dashboard và các service active | Evidence hoặc bản copy service cũ |
| `/docs/` | Tài liệu dự án đã được phân loại | File tạm không có owner/provenance |
| `/docs/guides/` | Hướng dẫn cài đặt, vận hành, kiểm thử | Audit lịch sử |
| `/docs/architecture/` | Architecture contract, repository map và thiết kế hiện tại | Log runtime |
| `/docs/archive/` | Audit round, baseline và tài liệu lịch sử không còn là current truth | Tài liệu hướng dẫn hiện hành |
| `/docs/legal/` | License notice, compatibility và trademark/legal notes | Source hoặc secret |
| `/docs/evidence/` | Evidence nhỏ, đã sanitize, có provenance | Token, cookie, `.env`, SQLite hoặc raw private log |
| `/scripts/ops/` | Supervisor, watchdog, monitor, launcher và harness đang được dùng | Patch lịch sử hoặc duplicate root |
| `/scripts/maintenance/` | Migration/maintenance helper có owner và cách chạy rõ | Runtime service chính |
| `/scripts/maintenance/legacy/` | Patch/fix one-off chỉ để tra cứu hoặc phục hồi có kiểm soát | Code được gọi tự động trong production |
| `/tests/` | Unit, contract, integration và reality tests | Kết quả test sinh ra |
| `/reports/` | Report và machine-readable evidence theo run/snapshot | Source code active |

## Các ngoại lệ có chủ đích ở root

`CONTRIBUTING.md` và `SECURITY.md` được giữ ở root vì GitHub tự nhận diện đây là policy entrypoint. `pytest.ini` ở root vì các runner và CI gọi từ repository root. Các file `.bat`/`.sh` ở root được giữ để không phá cách chạy double-click đã tồn tại. `run_reality_tests_portable.py` cũng tạm giữ ở root vì đây là entrypoint CI tương thích; output của nó phải đi vào `reports/reality/`, không ghi JSON kết quả vào root.

Các file này là **compatibility surface**, không phải dấu hiệu rằng root được phép chứa thêm patch/report mới.

## Quy tắc đặt tên và trạng thái

Tên current không dùng hậu tố `patch`, `fix`, `final`, `round`, `baseline` hoặc `probe` nếu file đó là code active. Những từ này chỉ dành cho lịch sử, migration, test hoặc evidence. Mọi evidence current phải ghi commit, profile, timestamp và phạm vi; mọi claim phải dùng `PASS_WITHIN_SCOPE`, `BLOCKED`, `CANDIDATE_NOT_PROVEN` hoặc verdict phù hợp thay vì “đã xong”.

## Quy trình thay đổi bố cục

Trước khi move hoặc remove file, phải kiểm tra tham chiếu, so sánh bản duplicate, lưu provenance nếu là artifact điều tra, cập nhật link, chạy compile/test/link check, tạo snapshot manifest và chỉ sau đó merge. Không dùng `git reset`, `git clean` hoặc xóa archive để làm thư mục trông sạch hơn.

## Source of truth

README root là entry guide. Tài liệu chi tiết bắt đầu từ [`docs/README.md`](../README.md). Architecture/runtime claim phải trỏ tới code và evidence cụ thể; không dùng một report cũ để đại diện cho snapshot hiện tại.
