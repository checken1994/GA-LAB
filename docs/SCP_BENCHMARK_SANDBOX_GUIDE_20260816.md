# Hướng dẫn dựng sandbox benchmark cho SCP

## Mục đích

Script `scripts/setup_scp_benchmark_sandbox.ps1` tạo một phòng thử nghiệm riêng cho hai nhóm bài test:

1. **AI Agent Security:** injection, vượt quyền, confused deputy, excessive agency, secret leakage, kill switch, audit và recovery.
2. **Secure Coding Agent:** sửa code, chạy test, không thêm lỗ hổng, không làm lộ secret và không nghe chỉ dẫn độc nằm trong repository.

Script không chạy benchmark trên PC thật. Nó tạo workspace bản sao đã lọc, map input vào guest ở chế độ chỉ đọc, map output riêng để lấy kết quả, ép các cờ nguy hiểm về `0`, tắt clipboard/audio/video/network và không map `.env`, `.private-secrets`, `data`, `node_modules`, `venv`, `.next` hoặc runtime desktop.

> **Điểm quan trọng:** không có sandbox nào an toàn tuyệt đối nếu chưa kiểm tra enforcement bằng fault injection. File manifest và output của mỗi run phải được giữ lại; không chỉ nhìn thấy cửa sổ VM rồi gọi là đã cách ly.

## Cách chạy an toàn nhất

### Bước 1: Chỉ tạo profile, chưa khởi động

Mở PowerShell bằng quyền Administrator, đi tới repo và chạy:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
cd C:\Users\check\Downloads\scp
.\scripts\setup_scp_benchmark_sandbox.ps1 `
  -Mode WindowsSandbox `
  -RepoPath C:\Users\check\Downloads\scp `
  -OutputRoot D:\UserData\scp-benchmark
```

Lệnh này chỉ tạo thư mục run, bản sao repo sạch, file `.wsb`, manifest và bootstrap. Không tự khởi động VM.

### Bước 2: Kiểm tra trước khi bấm Start

Kiểm tra các file sau:

```text
D:\UserData\scp-benchmark\scp-benchmark-*\host-manifest.json
D:\UserData\scp-benchmark\scp-benchmark-*\*.wsb
D:\UserData\scp-benchmark\scp-benchmark-*\input\sandbox_bootstrap.ps1
```

Phải thấy:

```text
network = disabled
input_read_only = true
host_secrets_mapped = false
```

Nếu thấy `.env`, `.private-secrets`, `data`, token, key, cookie hoặc database trong input, **không chạy**. Script được thiết kế để dừng khi phát hiện nhóm file này.

### Bước 3: Khởi động Windows Sandbox

Chỉ sau khi kiểm tra profile, chạy lại với `-Start`:

```powershell
.\scripts\setup_scp_benchmark_sandbox.ps1 `
  -Mode WindowsSandbox `
  -RepoPath C:\Users\check\Downloads\scp `
  -OutputRoot D:\UserData\scp-benchmark `
  -Start
```

Windows Sandbox sẽ chạy `sandbox_bootstrap.ps1`. Bootstrap copy input read-only sang workspace ghi được trong guest, ép các cờ nguy hiểm về 0, đặt token/provider key rỗng, rồi chỉ chạy compile check offline. Bộ benchmark thật chỉ được thêm sau khi task set đã đóng băng và được review.

## Vì sao mặc định tắt mạng

AI Agent Security benchmark không nên cho agent gọi internet tự do. Nếu agent được phép tải dependency, gửi dữ liệu ra ngoài hoặc gọi provider thật, kết quả không còn chứng minh được policy của SCP. Nếu sau này cần test provider, phải dùng một proxy egress riêng có allowlist domain/path, log request/response đã che secret, quota và kill switch. Không bật network trực tiếp trong Windows Sandbox chỉ để cho test chạy nhanh hơn.

## Hyper-V khi cần VM dùng lâu dài

Windows Sandbox phù hợp cho một run ngắn và luôn sạch lại sau khi đóng. Nếu cần VM giữ snapshot hoặc chạy nhiều giờ, dùng Hyper-V với một VHDX sạch:

```powershell
.\scripts\setup_scp_benchmark_sandbox.ps1 `
  -Mode HyperV `
  -RepoPath C:\Users\check\Downloads\scp `
  -OutputRoot D:\UserData\scp-benchmark `
  -HyperVBaseVhdxPath D:\VM\clean-windows-base.vhdx
```

Script tạo private virtual switch, differencing disk và VM generation 2, không tạo external switch, không tải ISO và không tự mở internet. VHDX gốc phải là bản sạch do người dùng kiểm tra trước; không dùng ổ Windows thật làm base.

## Ma trận quyền benchmark

| Hành động | Mặc định |
|---|---|
| Đọc input benchmark | Cho phép trong guest |
| Ghi workspace guest | Cho phép trong guest |
| Ghi output đã map | Cho phép, chỉ ở thư mục output |
| Đọc `.env`, token, cookie, SSH key | Từ chối |
| Gọi internet | Từ chối |
| Gọi provider thật | Từ chối |
| Upload, publish, delete, đổi quyền | Từ chối |
| Chạy AutoFix | Chỉ deterministic, cần task set đã review |
| Policy promotion | Không tự động trong vòng đầu |
| High-risk action | DENY hoặc HUMAN_REVIEW |

## PowerShell khởi động mỗi phút

Kiểm tra trên PC thật ngày 16/08/2026 đã xác nhận:

| Đối tượng | Kết quả |
|---|---|
| `SCP-247-Recovery-Watchdog` | Có trigger lặp `PT1M`, tức 1 phút/lần |
| Command | PowerShell 7.6.5, `-NoProfile -NonInteractive -WindowStyle Hidden -ExecutionPolicy Bypass -File ...scp_247_recovery_watchdog.ps1` |
| Thời gian chạy | Task Scheduler event log cho thấy trigger ở 09:53:15, 09:54:15, 09:55:15, 09:56:15, 09:57:15, 09:58:15; task kết thúc bình thường sau khoảng 3 giây |
| Cửa sổ SCP task | Action đã có `-WindowStyle Hidden`; cờ task `Hidden` đã được đặt thành `True` |
| Các `pwsh -NoExit` khác | Parent là `sidecar.exe` của Manus, không phải SCP; tại lúc kiểm tra không có `MainWindowHandle` |

Vì vậy, **SCP có đúng một phần chạy mỗi phút: Recovery Watchdog**. Ẩn được, và đã ẩn task + action. Nhưng ẩn không có nghĩa là tắt; watchdog vẫn chạy mỗi phút để kiểm tra phục hồi.

Các process `pwsh -NoExit` do Manus `sidecar.exe` tạo không được tự ý kill hoặc sửa trong phạm vi SCP. Muốn bỏ hoàn toàn hiện tượng nhấp nháy do nhóm process này, cần sửa cấu hình/launcher của Manus sidecar hoặc dùng bản desktop client phù hợp; không nên che giấu một process ngoài SCP khi chưa xác định đầy đủ lý do.

## Evidence đã lưu trên PC

```text
C:\Users\check\Downloads\scp\scp-audit\powershell-watch-20260816-095619\
C:\Users\check\Downloads\scp\scp-audit\hide-task-20260816-100504\
```

Evidence gồm process sampling, danh sách PowerShell scheduled tasks, trigger 1 phút và settings trước khi đổi cờ Hidden.

## Không được làm

Không map toàn bộ `C:\Users\check`, không map `C:\Users\check\Downloads\.env`, không đưa OpenRouter/Ollama key vào guest, không dùng external virtual switch, không chạy exploit trên PC thật, không dùng `-WindowStyle Hidden` để che một lệnh chưa được audit và không xóa log sau khi benchmark fail.

**Ngày:** 16/08/2026  
**Tác giả:** Manus AI

## Điều khiển Recovery Watchdog

Script `scripts/control_scp_247_watchdog.ps1` chỉ tác động vào task `SCP-247-Recovery-Watchdog`. Mỗi thao tác `Disable`, `Enable` hoặc `SetInterval` đều export XML và lưu `status-before.json` dưới `scp-audit\watchdog-control-*` trước khi thay đổi.

### Chỉ xem trạng thái

```powershell
Set-ExecutionPolicy -Scope Process Bypass
cd C:\Users\check\Downloads\scp
.\scripts\control_scp_247_watchdog.ps1 -Action Status
```

### Vô hiệu hóa hoàn toàn, có rollback

Lệnh này dừng lần chạy hiện tại nếu có, sau đó disable task. Nó không xóa script, log hay XML backup:

```powershell
.\scripts\control_scp_247_watchdog.ps1 -Action Disable
```

Sau lệnh này Supervisor vẫn có thể tiếp tục chạy; chỉ mất khả năng watchdog tự khởi động lại Supervisor khi Supervisor bị dừng. Nếu Supervisor đang Running, các service hiện tại không bị tắt chỉ vì watchdog bị disable.

### Bật lại nhưng chưa chạy ngay

```powershell
.\scripts\control_scp_247_watchdog.ps1 -Action Enable
```

### Bật lại và chạy một lần ngay

```powershell
.\scripts\control_scp_247_watchdog.ps1 -Action Enable -StartAfterEnable
```

### Giữ watchdog nhưng giảm tần suất từ 1 phút xuống 5 phút

```powershell
.\scripts\control_scp_247_watchdog.ps1 -Action SetInterval -IntervalMinutes 5
```

Có thể dùng số phút khác từ 1 đến 1440. Không nên đặt dưới 1 phút; khoảng 5 phút phù hợp hơn nếu ưu tiên giảm process spawn. Đổi lịch không làm watchdog chạy resident; mỗi lần vẫn là một process ngắn rồi thoát.

### Khôi phục task từ XML backup

```powershell
.\scripts\control_scp_247_watchdog.ps1 `
  -Action Restore `
  -BackupXmlPath 'C:\Users\check\Downloads\scp\scp-audit\watchdog-control-YYYYMMDD-HHmmss\SCP-247-Recovery-Watchdog.xml'
```

## Khuyến nghị cho PC hiện tại

Có ba mức:

| Mức | Cách làm | Khi nào dùng |
|---|---|---|
| Tắt hoàn toàn | `-Action Disable` | Khi đang debug Desktop hoặc không cần tự phục hồi |
| Kiểm soát cân bằng | `-Action SetInterval -IntervalMinutes 5` | Khi muốn có recovery nhưng không muốn mở PowerShell mỗi phút |
| Bảo vệ mạnh nhất | Giữ 1 phút, Hidden=True, timeout 30 giây, MultipleInstances=IgnoreNew, kill switch | Khi ưu tiên tự phục hồi 24/7 |

Ở trạng thái hiện tại, watchdog đang `Running`, `Hidden=True`, `MultipleInstances=IgnoreNew`, timeout `PT30S`, trigger `PT1M`. Nó chỉ kiểm tra trạng thái Supervisor và ghi ledger; script không có resident loop. Nếu không cần tự phục hồi trong lúc benchmark, mức an toàn và ít gây khó chịu nhất là disable bằng script có backup, không phải kill `pwsh` bằng PID.
