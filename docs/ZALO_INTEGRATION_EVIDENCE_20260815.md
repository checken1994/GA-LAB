# Bằng chứng tích hợp Zalo OA

Ngày kiểm tra: 2026-08-15.

## Nguồn chính thức

1. Zalo OA OpenAPI: https://developers.zalo.me/docs/api/official-account-api-230

Tài liệu nói OA OpenAPI cần Zalo Official Account, Zalo App đã được xác thực/cấp quyền, và hệ thống server của doanh nghiệp. Khi có tương tác, Zalo gửi HTTP POST đến webhook URL của ứng dụng. Các nhóm quyền gồm nhắn tin, gọi thoại, bài viết và quản lý.

2. Gửi tin tư vấn văn bản: https://developers.zalo.me/docs/official-account/tin-nhan/tin-tu-van/gui-tin-tu-van-dang-van-ban

Endpoint chính thức được tài liệu nêu là POST https://openapi.zalo.me/v3.0/oa/message/cs. Request cần header access_token, recipient.user_id và message.text; nội dung tối đa 2.000 ký tự. user_id phải lấy qua API/user interaction, không thể chỉ dùng số điện thoại tùy ý.

3. Webhook event: https://developers.zalo.me/docs/api/official-account-api/webhook/su-kien-official-account-gui-tin-nhan-cho-nguoi-dung-post-3650

Webhook nhận HTTP POST JSON và tài liệu nêu chữ ký X-ZEvent-Signature dựa trên appId, data, timestamp và OA secret key. SCP phải kiểm tra chữ ký, chống replay, giới hạn lệnh và chỉ cho phép user_id đã ghép cặp.

## Kết luận kỹ thuật

Repo SCP hiện không có connector Zalo và cấu hình Manus cũng không có mục Zalo. Muốn kết nối thật cần user cung cấp/thiết lập Zalo OA + Zalo App, quyền, access token hoặc OAuth flow, webhook HTTPS công khai và user_id được phép. Không được tự lấy token từ file khác, không gửi tin thử và không bật lệnh từ xa trước khi có allowlist, chữ ký webhook, nonce/replay protection, xác nhận hai bước cho lệnh nguy hiểm và audit log.

## Trạng thái đã kiểm chứng

- Dashboard live đã có sessionStorage, conversation_history, nút Mic bấm để nói một câu và nút Camera bấm để mở/chụp.
- Backend /ask đã nhận image_data base64 giới hạn kích thước và conversation_history giới hạn số turn.
- Reality test image_data với ai_answer có sẵn trả HTTP 200, PASS, domain math, answer 2 + 2 = 4.
- Reality test có image_data nhưng để Ollama tự sinh câu trả lời vượt thời gian 180 giây; điều này chưa chứng minh image path hỏng, vì test không tách riêng thời gian model. Backend vẫn healthy.
- Không tự động ghi âm, không tự động quay webcam, không gửi Zalo và không sửa production .env.

## Nguyên nhân trả lời lệch đã xác định

Dashboard `/dashboard` trước đây gửi `/ask` mà không có `session_id` và không có lịch sử. WebSocket `/chat` có lưu lịch sử trong RAM nhưng không truyền lịch sử đó vào lời gọi judge. Vì vậy giao diện có vẻ như đang trò chuyện nhưng backend xử lý các lượt gần như độc lập. Bản sửa e92b9da tạo session ID trong sessionStorage, gửi tối đa 8 turn gần nhất, truyền context có giới hạn vào Ollama và ưu tiên câu hỏi hiện tại. WebSocket cũng truyền conversation context vào judge.

Reality test trên PC trước bản sửa cho thấy: `2 + 2` → PASS/math/2 + 2 = 4; `Thủ đô Việt Nam` → CONFLICT/geography nhưng câu trả lời vẫn là Hà Nội; `Ollama dùng để làm gì?` → UNKNOWN vì chưa đủ dữ liệu. Đây là bằng chứng cho thấy pipeline không luôn trả lời sai chủ đề, nhưng phần chat không có context đúng và một số câu hỏi còn bị guard hạ xuống UNKNOWN.

Sau bản sửa, dashboard live có `getUserMedia`, `captureImage`, `conversation_history`, `sessionStorage`. Reality test `image_data` với câu hỏi 2 + 2 và answer có sẵn trả HTTP 200, PASS, math, `2 + 2 = 4`, không bị lịch sử cũ về thời tiết làm lệch. Test để Ollama tự sinh answer với ảnh đã vượt 180 giây; chưa dùng kết quả đó để kết luận ảnh hỏng, vì thời gian model là biến riêng.
