# Original User Request

## 2026-09-08T12:26:38Z

# Teamwork Project Prompt — R2, R3, R6 Remediation

Dự án SCP (Agent OS) đang cần vá 3 lỗ hổng kiến trúc nghiêm trọng cuối cùng (R2, R3, R6) để đạt trạng thái Autonomous 24/7.

Working directory: c:\Users\check\Downloads\scp
Branch hiện tại: omega/gap-01-remediation (hoặc main tuỳ bạn checkout, hãy tạo nhánh mới nếu cần, ví dụ: remediation/R2-R3-R6).

MANDATORY BINDING: You are strictly bound by Zero-Trust and Fail-Closed principles. You MUST adhere to FA-01 through FA-13. You are FORBIDDEN from self-granting authority or simulating PASS results. Any code modifications must explicitly enforce boundaries at the Database/Hardware level, not via RAM/Variables.

## Lỗ hổng cần vá

### R2: Execution Bypass (PCController)
- Vấn đề: `PCController` có các phương thức thực thi trực tiếp (VD: chạy command) mà thiếu boundary kiểm tra token hợp lệ từ Unified Broker.
- Yêu cầu: Thêm token boundary vào `PCController`. Bất kỳ request thực thi nào cũng phải có token (HMAC-SHA256 signature hợp lệ) được cấp phát đúng thẩm quyền. Chặn fail-closed nếu thiếu/sai token.

### R3: Provenance Forgery (Verifier receipts)
- Vấn đề: Các biên lai `verification.passed` (verifier receipts) đang thiếu độc lập (cryptographic provenance). Worker có thể tự giả mạo biên lai thành công để lừa Kernel.
- Yêu cầu: Thêm chữ ký số (cryptographic signature/HMAC) vào Receipt. Kernel phải verify chữ ký này trước khi commit trạng thái `COMPLETED`.

### R6: AutoFix Rollback (Cognitive loop perfect isolation)
- Vấn đề: Vòng lặp Cognitive/AutoFix thiếu cơ chế perfect isolation và rollback. Nếu AI áp dụng code lỗi, hệ thống bị hỏng (catastrophic corruption).
- Yêu cầu: Xây dựng cơ chế snapshot/rollback (có thể dùng `data/shadow/` hoặc git stash/restore) cho file trước khi AutoFix áp dụng patch. Tự động rollback nếu Reality Test (pytest) thất bại sau khi patch.

## Yêu cầu Bắt buộc (FA-12, FA-13)
- Vẽ Causal Graph và tạo file báo cáo `EMERGENCY_GAP_REPORT.md` (nếu phát hiện lỗ hổng lân cận).
- Phủ test cho toàn bộ nhân quả (Causal-Driven Test Generation) trong thư mục `tests/`. Chạy `pytest` phải xanh.
- Cuối cùng, tổng hợp kết quả (Fix steps, Test outcomes) vào artifact báo cáo.
