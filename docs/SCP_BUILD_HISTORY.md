# SCP DNA — Lịch sử xây dựng hệ thống

**Repository:** [`checken1994/GA-LAB`](https://github.com/checken1994/GA-LAB)  
**HEAD được đối chiếu:** `17f340283b7e8f314777f30b6a1fddfd1145e5ec` (`R39`)  
**Ngày đối chiếu:** 14/08/2026 (GMT+7)

## 1. Cách đọc lịch sử

Lịch sử SCP không chỉ là chuỗi commit tính năng. Đây là lịch sử của một hệ thống tự kiểm tra chính nó: mỗi round bắt đầu bằng việc đặt câu hỏi “Tại sao?”, kiểm chứng claim cũ bằng Reality, tìm nguyên nhân gốc, sửa nhỏ có rollback, rồi chạy lại test. Tư tưởng trung tâm là **DNA #22: PASS không đồng nghĩa TRUE**.

GitHub hiện có **23 commit chính** trong nhánh `main`, từ gói hardening/release ban đầu đến R39. Các báo cáo trong `docs/` bổ sung bối cảnh cho các round trước khi commit ledger trở nên chi tiết.

## 2. Các giai đoạn hình thành

| Giai đoạn | Dấu mốc | Kết quả kiến trúc/chức năng |
|---|---|---|
| Round 7–11 | Các worklog và self-audit đầu tiên | Hình thành SCP Python, AutoFix, dashboard Next.js, test Reality và phương pháp tự audit. Round 9 phát hiện các lỗi blocking trong async và race condition mà round trước đã bỏ sót. |
| R16–R20 | Remediation, startup gate, env loading, continuity | Chuyển các bài học audit thành guard production, startup gate, cấu hình env sớm, tài liệu continuity và learning/evolution audit. |
| R21–R27 | Provider contract và sidecar wiring | Chuẩn hóa provider credentials, timeout/checkpoint cho evolution, sửa env-loader wiring, cache empty override, model ID và help flag. |
| R28–R30 | Provider bounded mode và verification semantics | Thêm Ollama-only bounded provider mode, thay thế bare-except-pass trong AutoFix path và phân loại đúng các trường hợp evolution bị verifier reject. |
| R31–R34 | WHY và deterministic fixes | WHY gate đi qua bounded provider; deterministic `BareExceptPass` không còn bị model yếu phủ định; patch trailing `# noqa` được nhận diện và bảo toàn. |
| R35–R37 | Bounded AutoFix verification | Chặn nested pytest/enterprise/mypy scan trong post-fix verification và completeness check, xử lý downstream timeout thực tế. |
| R38 | Ledger isolation | Child process của bounded evolution ghi ledger theo `data_dir`, không làm nhiễm `data/learning_runs.jsonl` production khi chạy test. |
| R39 | Verified/stored observability | Ledger và audit payload ghi rõ `verified` và `stored`, phân biệt fix đã verify với reflect đã lưu durable. |

## 3. Commit ledger đã xác nhận trên GitHub

| Commit | Ngày | Ý nghĩa |
|---|---|---|
| `d80c246` | 13/08 | SCP DNA production hardening và packaged release ban đầu |
| `57c53cf` | 13/08 | Reconciled SCP DNA learning/evolution audit |
| `205c867` | 13/08 | Sửa production sidecar wiring và scheduler reality harness |
| `153c6f6` | 13/08 | Thêm learning/evolution run ledger |
| `55c4f5f` | 13/08 | Bảo đảm learning ledger trả metric đã được hỏi |
| `e529b4d` | 13/08 | Bounded evolution và canonical HTTP auth contract |
| `aee02cc` | 13/08 | Evolution stage checkpoints và provider timeout |
| `c3c8aec` | 13/08 | Thống nhất credential loading giữa các evolution path |
| `925d390` | 13/08 | Ghi provider contract reality evidence cuối |
| `e07f5fc` | 14/08 | Env-loader wiring, cache override, model ID và help flag |
| `01a299d` | 14/08 | Thay bare-except-pass trong AutoFix path |
| `5357d75` | 14/08 | Bounded Ollama-only provider mode |
| `7db2fcf` | 14/08 | Phân loại chính xác evolution verification rejects |
| `b479da5` | 14/08 | WHY qua bounded provider và review evolution fixes |
| `35d1673` | 14/08 | Tách deterministic BareExceptPass khỏi weak LLM falsification |
| `3d36e81` | 14/08 | Nhận diện `# noqa` trong deterministic fix |
| `95b3b3d` | 14/08 | Bảo toàn `# noqa` khi apply fix |
| `8ccc05b` | 14/08 | Bound AutoFix verification scans |
| `5ba56a3` | 14/08 | Isolate bounded evolution ledgers theo data directory |
| `17f3402` | 14/08 | Ghi verified/stored evolution outcomes |

## 4. Những gì SCP đã thực sự trở thành

SCP đã tiến hóa từ một bộ audit/autofix thành một pipeline có nhiều boundary: **scan → WHY → policy/review → deterministic hoặc bounded fix → verification → reflect → durable storage → ledger**. Desktop Control Center đóng gói pipeline cùng dashboard và các sidecar; backend Python giữ logic trust boundary; data layer giữ bằng chứng, ledger và knowledge state.

Evolution R39 trên PC thật đã ghi nhận `status=SUCCESS`, `bugs_found=1`, `bugs_fixed=1`, `verified=1`, `stored=1`; durable KB có 6 lessons và 4 evolved patterns. Đây là evidence của một bounded run cụ thể, không phải tuyên bố hệ thống phát hiện mọi cuộc tấn công.

## 5. Nguyên tắc thiết kế xuyên suốt

SCP giữ các nguyên tắc sau qua từng round:

1. **Reality over model:** source, process, port, response và ledger thật có quyền quyết định cuối.
2. **PASS ≠ TRUE:** pass chỉ có nghĩa không tìm thấy lỗi trong scope và evidence hiện tại.
3. **Fail closed ở trust boundary:** tier cao, startup gate, auth và policy không được tự nới lỏng trong production.
4. **Deterministic trước model khi pattern đã biết:** model không được phủ định một fix deterministic đã nằm trong trust boundary.
5. **Mọi thay đổi phải có rollback:** snapshot, manifest, verification và audit đi cùng patch.
6. **Learning phải durable và truy nguyên:** reflect, SQLite KB, JSONL audit và run ledger phải phân biệt các trạng thái thành công, reject, provider/verifier fail và write fail.

## 6. Các khoảng trống còn mở

Lịch sử này không biến SCP thành hệ thống đã chứng minh mọi khả năng. Các vùng còn cần evidence độc lập gồm code signing, cài đặt trên một PC Windows thứ hai, adversarial corpus mở rộng, provider poisoning, prompt injection ngoài corpus, supply-chain tampering và long-running concurrency stress. Cấu hình `.env` thật và data runtime vẫn là tài sản local/ignored, không được đưa lên GitHub.

## References

[1]: [GitHub commit history](https://github.com/checken1994/GA-LAB/commits/main)  
[2]: [SCP continuity archive](https://github.com/checken1994/GA-LAB/blob/main/docs/SCP_CAU_CHUYEN_GA_TAI_SAO_CONTINUITY_ARCHIVE.md)  
[3]: [SCP worklog](https://github.com/checken1994/GA-LAB/blob/main/docs/WORKLOG.md)
