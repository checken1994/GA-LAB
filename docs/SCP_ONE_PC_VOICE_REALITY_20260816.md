# SCP DNA — Reality Report: Hội thoại bạn–SCP trên một PC

**Ngày:** 2026-08-16  
**Phạm vi:** Windows Desktop, camera/mic trên chính PC của người dùng, không phải cuộc gọi giữa hai PC.

## 1. Kết luận ngắn

Mục tiêu đúng là: người dùng bấm nút trên Desktop, Windows hỏi quyền camera/mic, người dùng nói với SCP, SCP chuyển giọng nói thành chữ bằng Whisper local, đưa câu chữ vào luồng `/api/scp/ask`, hiển thị câu trả lời và đọc lại bằng loa của PC. Đây là mô hình **một người dùng nói chuyện với trợ lý SCP**, không cần WebRTC signaling, STUN hoặc TURN.

Source code trước đó đang trộn hai ý khác nhau. `video-call-panel.tsx` là phòng WebRTC hai peer, còn Dashboard chính có một phần mic/camera riêng. Vì vậy giao diện có camera/mic nhưng không phải một “cuộc nói chuyện với SCP” hoàn chỉnh. Ngoài ra, runtime dashboard cũ có manifest thiếu `/api/scp/ask`, `/api/scp/voice` và `/api/scp/call/session`, dù source Dashboard đã có các route này. Đây là lỗi **runtime stale**: source mới hơn gói chạy thật.

## 2. Thay đổi đã thực hiện

Commit `9ca6131` thay `video-call-panel.tsx` bằng luồng một PC. Luồng mới có các nút bắt đầu và tắt cuộc nói chuyện, camera preview của người dùng, avatar SCP, bật/tắt camera, bật/tắt mic, ghi từng câu, gửi audio qua `/api/scp/voice`, gửi transcript qua `/api/scp/ask`, hiển thị verdict/câu trả lời và đọc câu trả lời bằng `speechSynthesis` của Chromium. Quyền thiết bị chỉ xin sau khi người dùng bấm nút; khi tắt thì toàn bộ media track bị dừng.

Commit `bc06d96` thêm `signAndEditExecutable=false` và `forceCodeSigning=false` trong electron-builder. Mục đích là không để build bị treo ở bước tìm signtool khi PC chưa có certificate Authenticode. Điều này **không ký mã**; installer vẫn sẽ NotSigned cho đến khi người dùng có certificate.

## 3. Bằng chứng thực tế trên PC

| Kiểm tra | Kết quả | Ý nghĩa |
|---|---:|---|
| Dashboard source build trên PC | PASS | Next build hoàn thành; chỉ còn cảnh báo dynamic filesystem đã có từ trước |
| Backend health sau mở Desktop unpacked | HTTP 200 | Backend thật khởi động được |
| Dashboard HTTP sau mở Desktop | HTTP 200 | Dashboard thật khởi động được |
| Runtime ports | 3000, 3030, 8000 mở; 11434 là Ollama | Chuỗi Desktop backend/sidecar đã lên trong smoke |
| Tắt smoke | PASS | Các process SCP do smoke đã dừng; Ollama được giữ nguyên |
| Runtime manifest sau copy fix | PASS | Có `/api/scp/ask`, `/api/scp/voice`, `/api/scp/call/session` |
| Camera/mic thật | CHƯA CHỨNG MINH | Cần người dùng bấm nút và chấp nhận quyền trên cửa sổ Desktop thật |
| Whisper package trên venv | Có `openai-whisper 20250625` | PC có thư viện STT local; chưa chứng minh một câu nói thật đã được nhận đúng |
| Edge TTS package | Chưa có | Bản mới dùng loa Chromium `speechSynthesis`, không phụ thuộc edge-tts |

Probe voice dùng payload giả đã từng trả lỗi JSON vì payload bị escape sai trong PowerShell; đó không phải bằng chứng camera/mic hỏng. Sau copy fix, manifest đã có route voice. Một phiên probe audio thật vẫn chưa được coi là PASS vì chưa có thao tác micro thật của người dùng và chưa có transcript độc lập để đối chiếu.

## 4. Installer

Electron-builder trên PC vẫn treo ở bước packaging sau thời gian dài, kể cả sau khi tắt tự động ký mã. Vì vậy hai installer trong `desktop/release` đã được khôi phục về bản đã biết là hợp lệ, không dùng bản build dở. Hash known-good hiện giữ nguyên:

| File | SHA-256 |
|---|---|
| `SCP-DNA-Control-Center-1.6.0-x64.exe` | `F0FC3E717C2ACD2F013B7867E2D8FA1ECC2B487ED0346D85A61B8C3012F8E9D6` |
| `SCP-DNA-Control-Center-1.6.0-portable.exe` | `BB99D273ED965F5A7DED297FFD9FB6271E8F6F61C1EB0BB0F0808FCB402BCD24` |

Không tuyên bố installer mới đã chứa patch voice. Source và runtime/dashboard đã cập nhật; installer cuối cần một lần build sạch thành công rồi mới được phát hành.

## 5. Những phần còn chưa thể gọi là hoàn tất

Email Gmail người dùng gửi chưa đọc được vì phiên trình duyệt đang ở trang Sign in; chưa có bằng chứng về “mô hình trong email”. Không được tự đoán nội dung email.

Camera/mic một PC đã được nối về mặt code và route runtime, nhưng chưa có bằng chứng người dùng nói một câu thật, Whisper trả transcript đúng, câu đó đi qua governance, và SCP đọc lại đúng bằng loa. Đây là bước cần thao tác thiết bị thật, không thể thay bằng health check.

Defensive action thật như block IP, chỉnh firewall hoặc honeypot vẫn chưa được bật tự động. Hiện SCP cố ý trả `SKIPPED_NOT_IMPLEMENTED` cho action chưa có enforcement để không nói sai. Không nên biến phần này thành lệnh block tự động trước khi có allowlist, giới hạn phạm vi, rollback, timeout và human approval.

ACL `.env` production chưa sửa vì yêu cầu dự án cấm tự ý đổi quyền file secret. OTel collector thật, PC thứ hai, Zalo/Telegram, installer PC thứ hai và soak test 24 giờ vẫn chưa có bằng chứng.

## 6. Reality over Model

> `PASS` ở đây chỉ có nghĩa là không phát hiện lỗi trong phạm vi kiểm tra hiện tại. Nó không có nghĩa mọi camera, mọi mic, mọi driver Windows hoặc mọi installer PC khác đều đã được chứng minh.

Trạng thái trung thực hiện tại là: **source one-PC voice đã được sửa và đồng bộ GitHub; runtime dashboard đã được cập nhật đúng route; Desktop backend smoke đạt HTTP 200; camera/mic thật và installer mới vẫn chưa được chứng minh hoàn chỉnh.**

## 7. Rollback

Source rollback: checkout commit trước `7ea634f` nếu cần.  
Dashboard runtime rollback: dùng `.private-secrets\runtime-dashboard-before-copyfix-20260816\dashboard`.  
Stable unpacked dashboard rollback: dùng `.private-secrets\stable-dashboard-before-voice-20260816\dashboard`.  
Installer rollback: dùng `.private-secrets\installer-before-one-pc-voice-20260816`.
