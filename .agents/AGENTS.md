# SCP Agent Instructions & System Skills Directives

> **QUY TẮC BẮT BUỘC TRƯỚC MỌI PHIÊN LÀM VIỆC (PRE-SESSION MANDATE)**
> Trước khi bắt đầu bất kỳ tác vụ nào trong workspace này, Agent **BẮT BUỘC** phải tải, tham chiếu và tuân thủ bộ kỹ năng **SCP Skills** cùng 26 nguyên lý **SCP DNA**.

---

## 1. Bộ Kỹ Năng SCP Cốt Lõi (SCP Skills Pack)

Toàn bộ 13 kỹ năng SCP đã được tích hợp vào bộ nhớ và cấu hình hệ thống tại `.agents/skills/` và plugin toàn cục:


| Kỹ năng (Skill) | Mục đích & Trọng tâm |
|---|---|
| **`scp-dna`** | Áp dụng 26 nguyên lý DNA: *Thực tế > Mô hình*, *PASS ≠ TRUE*, *Ảo giác đồng thuận*, *Tìm mảnh ghép còn thiếu (missing piece)*, *Fail-Closed*. |
| **`scp-reality-verifier`** | Tiêu chuẩn hóa 4 cấp độ bằng chứng (*Static → Integration → End-to-end → Recovery*). Bắt buộc chạy kiểm thử thực tế trước khi xác nhận sửa lỗi. |
| **`scp-runtime-audit`** | Kiểm toán trạng thái tiến trình thực tế, cổng dịch vụ, health probe và nhật ký hệ thống. |
| **`scp-task-kernel-review`** | Kiểm tra tính bất biến của State Machine trong Task Kernel (15 trạng thái hợp lệ, khóa chuyển đổi nguyên tử). |
| **`scp-capability-security-review`** | Phân quyền bảo mật theo tác vụ, bảo vệ chống bypass, injection và leo thang đặc quyền. |
| **`scp-release-evidence-gate`** | Tiêu chuẩn bằng chứng phát hành: không tuyên bố "hoàn hảo" khi chưa có kết quả kiểm thử tái lập độc lập. |
| **`scp-startup-troubleshooter`** | Xử lý lỗi khởi động, phát hiện xung đột cổng và bất đồng bộ biến môi trường. |
| **`scp-safe-latency-optimizer`** | Tối ưu hóa độ trễ mà không làm suy yếu các cổng an toàn hoặc cơ chế khôi phục. |
| **`scp-computer-use-recovery`** | Cơ chế phục hồi khi tác vụ ngoại vi, browser hoặc worker bị ngắt quãng giữa chừng. |
| **`scp-gateway-resilience`** | Kiểm soát LLM Gateway, Circuit Breakers, Model Fallback Cascade, và API rate limits — độ trễ và độ bền của tầng LLM outbound. |
| **`scp-learning-loop-guard`** | Kiểm soát vòng lặp học liên tục, Knowledge Warehouse, Deep Scraper, và Autofix engine — chống Knowledge Poisoning và Catastrophic Forgetting. |
| **`scp-web-orchestration-safety`** | Kiểm soát browser sessions, DOM manipulation, CDP protocol, và anti-honeypot tactics — chống bẫy thực thi trên web.. |
| **`scp-skill-review`** | Chuẩn audit bộ skill: index nhất quán, bằng chứng, calibration, và định xem skill nào đáng tin làm chuẩn sửa chính SCP. |

---

## 2. Nguyên Tắc Vận Hành Bất Biến (Non-Negotiable Rules)

1. **Reality > Model (Thực tế > Mô hình):** Không tin vào suy đoán hay ảo giác của AI. Luôn xác minh bằng mã thực thi, AST và log thực tế trước khi kết luận hoặc xóa code.
2. **Fail-Closed by Default:** Khi thiếu context hoặc không chắc chắn về độ an toàn, hệ thống phải từ chối hoặc chuyển sang trạng thái `UNKNOWN`/`HUMAN_REVIEW`, tuyệt đối không tự bịa đặt câu trả lời.
3. **Zero Hardcoded Paths:** Tất cả các đường dẫn trong codebase phải giải quyết động (`Path(__file__).resolve().parent...`), nghiêm cấm hardcode đường dẫn người dùng cá nhân.
4. **Clean Workspace:** Tuyệt đối không để lại file rác, file debug tạm bợ tại thư mục gốc. Mọi kiểm thử phải có đường dẫn dọn dẹp hoặc nằm trong vùng `.gitignore`.
5. **Continuous Verification:** Sau mỗi chỉnh sửa code, bắt buộc chạy `run_reality_tests_portable.py` (76/76) và pytest để đảm bảo không có bất kỳ regression nào.
6. **API-First Orchestration:** SCP là một Agent OS sinh ra để điều phối API ngoại vi thông qua Gateway. TUYỆT ĐỐI KHÔNG đề xuất cài đặt hoặc chạy các Local Inference Engine (như Ollama, vLLM) cho các tác vụ suy luận cốt lõi để bảo vệ ranh giới kiến trúc.
7. **Distributed Autonomy (Tự chủ phân tán):** Khi thiết kế hoặc audit SCP, khái niệm "External Reviewer" (Người đánh giá bên ngoài) phải được hiểu là một Subsystem độc lập (Ví dụ: Agent A kiểm duyệt Agent B), chứ không phải tạo Nút thắt cổ chai bằng cách đẩy cho Con người.
