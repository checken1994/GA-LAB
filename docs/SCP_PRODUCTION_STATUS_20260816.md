# Báo cáo trạng thái SCP DNA — 16/08/2026

**Phạm vi:** repo `checken1994/GA-LAB`, PC Windows `C:\Users\check\Downloads\scp`, và Release Gate trên GitHub.

> **Kết luận ngắn:** Phần mã nguồn đã sửa, bộ kiểm tra CI và bộ reality test hiện đã đạt trạng thái **production candidate**. Tuy nhiên, chưa được gọi là **Production-ready hoàn toàn** vì còn các phần vận hành thật chưa có bằng chứng: chạy nền 24/7 trong 24 giờ, camera/mic bằng người dùng thật, installer mới, ký code Windows, OTel, defensive action ở firewall/OS và tích hợp Zalo/Telegram.

## 1. Bằng chứng cuối cùng

| Hạng mục | Kết quả thật | Bằng chứng |
|---|---:|---|
| Commit cuối trước báo cáo | `aaa6177` | `git log`, PC đã pull fast-forward |
| GitHub Release Gate | **PASS** | [Run 31921128687](https://github.com/checken1994/GA-LAB/actions/runs/31921128687) |
| Reality tests trên GitHub Windows | **74/74 PASS, 0 fail, 0 timeout, 0 error** | Log run `aaa6177`, dòng summary |
| Reality tests trực tiếp trên PC Windows | **74/74 PASS, 0 fail, 0 timeout, 0 error** | `C:\Users\check\Downloads\scp\scp-audit\reality-suite-pc-aaa6177-20260816-090901.json` |
| Pytest trong clone | **101 passed** | Local check trước commit dashboard |
| Ruff trên phần kernel/route | **PASS** | Local check trước commit |
| Dashboard build | **PASS** | Next.js 16.3.0 build hoàn tất |
| NPM audit production | **0 vulnerabilities** | Log Release Gate cuối |
| Port SCP sau test | `3000=False`, `3030=False`, `8000=False` | Postcondition trên PC |
| Scheduled Tasks | Supervisor và Recovery Watchdog đều `Disabled` | Postcondition trên PC |
| Git tracked diff trên PC | Không có thay đổi tracked chưa commit | `TRACKED_DIFF=False`, `STAGED_DIFF=False` |

Bộ test trên PC đã chạy đúng trên máy thật, không phải chỉ chạy trong sandbox. Các test sidecar tự khởi động Bun tạm thời, dùng env rỗng riêng, rồi tự dừng. Sau khi kết thúc, không còn port SCP mở và không còn process Bun/Node/Electron của test bị bỏ lại.

## 2. Những lỗi thật đã tìm ra và đã sửa

### 2.1. Release Gate ban đầu không chạy được

CI ban đầu fail ngay ở bước cài thư viện vì hai phiên bản bị ghi sai hoặc xung đột: `types-requests==2.32.0` không tồn tại và `coverage==7.6.0` không tương thích với `pytest-cov==7.0.0`. Ngoài ra, requirements production kéo theo gói ML nặng dù Release Gate không dùng đến. Các phiên bản đã được sửa, phần ML được tách ra thành `scp/requirements-optional-ml.txt`, còn CI mặc định chỉ cài thứ cần cho kiểm tra.

### 2.2. CI thiếu Bun

Năm reality test của loop-scheduler và llm-bridge fail vì workflow GitHub chỉ cài Python nhưng không cài Bun. Workflow đã thêm `oven-sh/setup-bun@v2`, pin Bun `1.3.14`, đúng với phiên bản Bun trên PC.

### 2.3. Hai sidecar có import trùng làm runtime Bun không khởi động

`loop-scheduler/index.ts` khai báo `dirname` hai lần. `llm-bridge/index.ts` khai báo `readFileSync` hai lần. Bun build trên PC đã xác nhận sau khi sửa: cả hai sidecar đều bundle thành công.

### 2.4. Reality harness phụ thuộc sai vào Windows

Một số test dùng `grep`/`rg` và quét cả `venv`, `node_modules`, cache và dữ liệu lớn. Trên PC thật, ba test bị timeout 60 giây. Harness đã được sửa để bỏ qua các thư mục không phải mã nguồn, và buộc UTF-8 khi chạy child process. Sau đó ba test đều PASS; full suite trên PC đạt 74/74.

Runner cũng tự tạo một `.env.test` rỗng, chỉ dùng cho child test. Nó không tự lấy `.env` production. Đây là điểm quan trọng để tránh test vô tình dùng secret thật.

### 2.5. Dashboard có Prisma giả định nhưng không có client được generate

Build Next.js fail vì `@prisma/client` có trong package nhưng checkout sạch không có Prisma client được generate và repo cũng không có schema database đang dùng. `dashboard/src/lib/db.ts` đã được đổi thành facade **fail-closed**: nói rõ database chưa được cấu hình, thay vì giả vờ có database. Nếu sau này cần database, phải thêm `schema.prisma`, chạy `prisma generate`, rồi thay facade trong một change riêng.

### 2.6. Task Kernel đã được harden

Planner/Executor đã được bổ sung lease có thời hạn, heartbeat, fencing token, journal có sequence/hash, fsync, stale-run guard và recovery rõ ràng cho tình trạng UNKNOWN. Worker cũ không được tiếp tục ghi kết quả sau khi lease đã mất. Side effect không được retry mù khi chưa biết hành động đã chạy hay chưa.

Reality probe tạm thời đã kiểm tra hai worker cùng tranh một plan, stale worker bị chặn, failure cần recovery và journal có integrity. Đây là bằng chứng tốt cho kernel ở mức code/runtime probe, nhưng chưa phải soak test nhiều process trong 24 giờ.

## 3. Trạng thái PC sau khi kiểm chứng

SCP hiện vẫn **tắt 24/7 theo yêu cầu trước đó**. Hai scheduled task `SCP-247-Supervisor` và `SCP-247-Recovery-Watchdog` đều Disabled. Các port `3000`, `3030`, `8000`, `11434` đều không mở tại thời điểm postcondition cuối. Process Python `D:\scp-local-agent\runtime\main.py` vẫn là một chương trình khác, không phải SCP; không tự ý dừng chương trình đó.

Ollama và phần mềm ngoài phạm vi SCP không bị xóa. Full reality suite dùng sidecar tạm thời rồi dọn sau test. Không có secret value nào được đưa vào báo cáo hoặc commit.

## 4. Những phần chưa được phép tuyên bố hoàn tất

| Phần | Trạng thái thật | Vì sao chưa thể gọi là xong |
|---|---|---|
| Chạy 24/7 | Chưa bật | Chưa có soak test 24 giờ về memory, log, SQLite lock và recovery |
| Camera/mic | Có code route và UI | Chưa có bằng chứng người dùng bấm Allow, nói thật, Whisper nhận âm thanh và loa đọc lại trên PC |
| Desktop installer mới | Chưa chứng minh | Bản installer known-good cũ còn NotSigned; electron-builder build mới từng treo |
| Ký code Windows | Chưa có | Chưa có certificate Authenticode |
| Defensive action thật | Chưa hoàn tất | Playbook hiện phải trả `SKIPPED_NOT_IMPLEMENTED` cho block IP/firewall chưa có implementation đầy đủ |
| OTel collector | Chưa hoàn tất | Chưa cài SDK/collector và chưa có trace thật từ các subsystem |
| Zalo/Telegram | Chưa có | Chưa có connector, webhook verification, chống replay và command allowlist |
| PC thứ hai | Chưa làm | Chưa có kiểm chứng cài installer trên máy khác |
| Học từ external truth | Chưa đủ | Có staging/policy handoff, nhưng chưa chứng minh luồng học external truth dài hạn và promotion tự động an toàn |
| Code production `.env` ACL | Chưa tuyên bố | Chưa sửa trực tiếp theo yêu cầu không tự ý đụng file `.env` production |

Vì vậy, câu trả lời chính xác là: **SCP đã qua cổng kiểm tra code và reality suite, nhưng toàn sản phẩm chưa đủ bằng chứng để gọi Production-ready hoàn toàn.** Không nên bật 24/7 chỉ vì CI xanh.

## 5. Backup và rollback

Trước mỗi lần pull lên PC, các file tracked liên quan đã được copy vào các thư mục backup sau:

```text
C:\Users\check\Downloads\scp\scp-audit\20260816-before-sync-b7cc8fa\
C:\Users\check\Downloads\scp\scp-audit\20260816-before-sync-aaa6177\
```

Nếu cần quay code tracked về mốc trước patch cuối, có thể dùng Git sau khi kiểm tra lại thay đổi local:

```powershell
git -C C:\Users\check\Downloads\scp status --short
git -C C:\Users\check\Downloads\scp reset --hard b7cc8fa
```

Lệnh rollback trên chỉ tác động file tracked. Không dùng `git clean -fd`, vì PC đang có nhiều thư mục backup, báo cáo và dữ liệu người dùng chưa được phân loại để xóa.

## 6. Bước hợp lý tiếp theo

Bước tiếp theo nên là tạo một **production candidate có kiểm soát**, không bật 24/7 ngay. Candidate này cần kiểm tra installer trên PC sạch, camera/mic bằng thao tác thật, rồi mới bật supervisor trong cửa sổ quan sát ngắn. Sau đó chạy soak test tăng dần từ 1 giờ lên 24 giờ, theo dõi process, port, memory, log size, SQLite lock, kill switch và recovery. Chỉ khi các postcondition này đều có bằng chứng mới được gọi SCP là Production-ready vận hành thật.

**Tác giả:** Manus AI  
**Ngày:** 16/08/2026
