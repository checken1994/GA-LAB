# Desktop SCP — Root Cause và Reality Test

**Phạm vi:** PC Windows thật `C:\Users\check\Downloads\scp`, sau khi desktop portable báo lỗi trong bối cảnh SCP-247 Supervisor đang chạy.

## Kết luận ngắn

Nguyên nhân chính đã được xác định là **hai thành phần cùng cố làm chủ một stack SCP dùng chung bốn port**. Supervisor đã chạy sẵn backend, scheduler, bridge và dashboard trên `3000/3030/8000/11434`; Electron desktop cũ lại luôn gọi `startService()` cho toàn bộ child process mà không kiểm tra stack bên ngoài. Khi portable app mở trong trạng thái đó, Bun/Python cố bind lại các port đang được dùng. Log thực tế có `EADDRINUSE` trên scheduler và các lần trước có `dashboard load failed: ERR_FAILED`.

Đây không phải lỗi của riêng một patch AST hay một binary worker. Đây là lỗi **lifecycle ownership contract**: chưa có invariant “mỗi port chỉ có một owner” và desktop chưa có chế độ attach vào stack do supervisor quản lý. Việc thêm deterministic worker làm lộ rõ khoảng trống này vì runtime desktop đã có thêm child nhưng boot path vẫn giả định Electron là owner duy nhất.

## Evidence độc lập

| Dòng evidence | Kết quả thực tế |
|---|---|
| Port owner trên PC | `3000=node`, `3030=bun`, `8000=python`, `11434=bun` |
| Log runtime | `Failed to start server. Is port 3030 in use?`, mã `EADDRINUSE` |
| Desktop log lịch sử | Có `dashboard load failed: ERR_FAILED` sau startup race |
| Supervisor | Task `SCP-247-Supervisor = Running` |
| Watchdog | `SCP-247-Recovery-Watchdog = Ready` |
| Health trước/sau fix | `3000/3030/8000/11434` listen; HTTP `200,200,200,200` |
| Portable test sau fix | Process desktop sống sau 15 giây; chỉ có **1 process liên quan mới** — chính portable app, không có Bun/Python child duplicate |
| Sau khi đóng desktop | Bốn port vẫn listen, chứng minh desktop attach không sở hữu/kill stack supervisor |
| Worker queue | `applied=1`, `rejected=1`, `llm_allowed=false` |

## Chuỗi “tại sao”

**Tại sao desktop báo lỗi?** Vì desktop cố khởi động các service mà supervisor đã khởi động.

**Tại sao desktop lại khởi động duplicate?** Vì `boot()` gọi `startService()` cho `bridge`, `scheduler`, `scp`, `worker`, `dashboard` vô điều kiện; không có preflight kiểm tra external healthy stack.

**Tại sao các test trước không bắt được?** Vì test tập trung vào isolated fixtures, source contract, service health và worker queue; chưa có test black-box “launch portable khi supervisor đang giữ toàn bộ port”. `HTTP 200` của service không chứng minh ownership lifecycle của desktop.

**Tại sao mỗi lần fix lại lộ lỗi mới?** Vì các thay đổi được thực hiện theo từng lớp: supervisor/worker trước, packaging sau, nhưng contract giữa các lớp chưa được kiểm tra như một hệ thống duy nhất. Mỗi patch làm thay đổi topology process, trong khi test cũ vẫn giả định topology trước đó. Đây là regression do **missing integration invariant**, không phải bằng chứng rằng mọi patch đều vô nghĩa.

## Thay đổi đã áp dụng

Electron boot hiện thực hiện ba trạng thái:

| Trạng thái | Hành vi |
|---|---|
| `external-healthy` | Attach vào stack hiện hữu; không gọi `startService()`, không tạo child duplicate |
| `partial` | Từ chối khởi động duplicate và báo rõ stack đang partial; operator xem log/supervisor recovery |
| `none` | Electron mới khởi động các child packaged/source của chính nó |

Ngoài ra, packaged mode giờ kiểm tra **mọi runtime executable** trước khi spawn, trong đó có `scp-autofix-worker.exe`, thay vì chỉ kiểm tra backend.

## Reality test sau fix

Portable artifact đã được rebuild và promote sau backup:

```text
Path: C:\Users\check\Downloads\scp\desktop\.private-release-current\SCP-DNA-Control-Center-1.6.0-portable.exe
Size: 625,548,707 bytes
SHA-256: 13FF34A60F8C749532AD9FBEBDD597939BE114EBDA7401E2E4F4AC000CCEC8A2
```

Khi launch artifact này trong lúc supervisor đang healthy, desktop process sống qua 15 giây, không sinh Bun/Python child mới, và sau khi đóng desktop bốn port supervisor vẫn còn listen. Full-stack checkpoint sau đó vẫn trả `Supervisor=Running`, `Watchdog=Ready`, `HTTP=200,200,200,200`, `LOOP_PAUSED=false`, `total_runs=49`.

## Vì sao vẫn có thể xuất hiện lỗi khác

Bản sửa này đóng **một root cause cụ thể**, không chứng minh desktop hoàn hảo. Các khoảng trống còn lại là clean-machine install, userData permission, Windows Defender/SmartScreen, sleep/hibernate, cold boot/logon, disk-full/log rotation, Authenticode và trường hợp partial stack kéo dài hơn 45 giây. Những trường hợp đó phải có reality test riêng.

## Rollback

Backup checkpoint đã được tạo trước chẩn đoán. Artifact cũ được backup trước khi promote artifact mới. Nếu cần dừng ngay, tạo file `C:\Users\check\Downloads\scp\.private-secrets\release-audit\scp-247\KILL`; supervisor sẽ dừng children theo Job Object. Muốn rollback desktop artifact, dừng portable app, restore file backup gần nhất, kiểm tra SHA-256 rồi mới mở lại.

## GitHub

Patch Electron attach/partial-stack guard đã push lên [GA-LAB commit `ea78012`](https://github.com/checken1994/GA-LAB/commit/ea7801246960d535cb5de8ac4bb6e5c8e82ee397). Đây là evidence của patch source; artifact Windows vẫn được phân phối bằng file release có hash, không commit binary vào source repository.

## Kết luận theo SCP DNA

> `PASS` trước đây chỉ có nghĩa các test cũ không phát hiện lỗi trong phạm vi topology cũ. Nó không chứng minh desktop có thể attach vào supervisor stack thật.

Hiện tại evidence hỗ trợ kết luận: **desktop startup collision đã được xác định và đã có fix được reality-test trên PC này**. Chưa được phép suy rộng thành “desktop không còn lỗi trên mọi máy”.
