# SCP — Self-Correcting Pipeline (Agent Runtime)

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Status: API-Only Agent Runtime](https://img.shields.io/badge/status-API--Only%20Agent%20Runtime-green.svg)](#trạng-thái-thực-tế-ground-truth)

> **SCP không phải là một mô hình ngôn ngữ (LLM). SCP là một Hệ điều hành trung gian (Agent OS/Runtime) đứng giữa AI và thế giới thực.**
> **Tôn chỉ cốt lõi (SCP DNA): Reality > Model. Lỗi thì đóng cửa (Fail-Closed). Bằng chứng thực thi quan trọng hơn suy luận của AI.**

## Cách SCP Thực Sự Hoạt Động

Thay vì để AI trực tiếp gọi hàm (Function Calling) một cách vô tội vạ, SCP ép AI phải tuân thủ một cỗ máy trạng thái (State Machine) khắt khe:

1. **State Machine Bất Biến:** Mọi task đi qua luồng CREATED -> PLANNING -> READY -> QUEUED -> LEASED -> RUNNING. Nếu tiến trình chết ngang giữa chừng, SCP tự động đóng băng và đưa vào trạng thái HUMAN_REVIEW (Chờ người kiểm duyệt) khi khởi động lại, tuyệt đối không tự ý đoán mò để chạy tiếp.
2. **Quản Lý Quyền (Capability Guard):** 
   - Mọi AI/Agent bên ngoài đều bị khóa cứng bởi capabilityLevel của phiên làm việc (Session). Nếu yêu cầu quyền cao hơn, hệ thống trả về WAITING_APPROVAL.
   - **Đặc quyền duy nhất:** Trừ duy nhất AI định danh là SCP (gent_id="SCP") được thiết kế kiến trúc cho phép tự nâng quyền (Self-escalation) để giải quyết các luồng hệ thống lõi.
3. **Cổng Xác Minh (Verification Gates):**
   - Không có khái niệm "Làm xong". Mọi kết quả phải vượt qua Reality Judge (kiểm tra trạng thái hệ thống, log, post-condition) trước khi được đánh dấu là VERIFIED.
   - Các tri thức thu thập từ Internet phải đi qua Quarantine (Cách ly) trước khi được nạp vào Kho Tri Thức (Knowledge Warehouse).
4. **Gateway Độ Trễ Thấp:** 
   - Đứng giữa SCP và các LLM là một LLM Gateway (OpenRouter, Groq) tích hợp sẵn Circuit Breaker (ngắt mạch khi lỗi), Retry Backoff, và luân chuyển Model. Không chạy Local Inference Engine để bảo vệ tài nguyên lõi.

## Trạng Thái Thực Tế (Ground Truth)

Không phóng đại, không ảo tưởng, đây là tình trạng hiện tại của hệ thống được ghi nhận bởi log thực thi:

* **Tính Khả Dụng (Availability):** Kiến trúc Kernel + SQLite WAL cho thấy khả năng phục hồi an toàn sau các đợt Crash (đã có Test E2E Chaos Recovery).
* **Test Coverage (Bao phủ mã):** 
  - **Sự thật:** Test viết tay hiện tại mới chỉ bao phủ **~16%** trên tổng số hơn 50.000 dòng code. Hàng loạt module liên quan đến Sandbox, Threat Simulator đang mù.
  - **Giải pháp:** Đang kích hoạt chạy ngầm **Test Factory Daemon** (scripts/scp_test_factory.py). Tiến trình này dùng watchdog lắng nghe sự thay đổi code, tự động gọi Autofix LLM của SCP để viết thêm/sửa test ngay khi có file thay đổi, với mục tiêu cày lên 100% tự động.
* **Release:** Vẫn đang ở mức Integration Test. **Chưa qua Soak Test dài ngày trên Windows**, chưa chứng minh được Ranh giới Sandbox an toàn tuyệt đối với mã độc.

## Quick Start

`ash
pip install -r requirements.txt

# Yêu cầu biến môi trường (.env)
#   SCP_JWT_SECRET=<random hex 64>
#   SCP_ADMIN_KEY=<random urlsafe 24>
#   OPENROUTER_API_KEY=<your key>

python -m scp 8000
`

## Cấu trúc Hệ Thống

| Module lõi | Mô tả thực tế |
|---|---|
| scp/task_kernel.py | Trái tim của hệ thống. Ghi log State Machine vào SQLite, cấp Lease (Khóa tác vụ), và rà soát Crash khi boot. |
| scp/hands/planner.py | Quản lý DAG Plan. Ép buộc phân quyền Capability cho AI ngoài, mở luồng cho SCP. |
| scp/llm_gateway/ | Quản lý kết nối ra các LLM API ngoài, chống rate-limit. |
| scp/learning/ | Promotion Gate và Quarantine. Lọc dữ liệu đầu vào. |
| scp/security/ | OS Sandbox và các cổng chặn (Chưa hoàn thiện 100% trên Windows Job Object). |
| scripts/scp_test_factory.py | Trình sinh test tự động dựa vào Autofix. |

## Giấy phép
MIT License.
