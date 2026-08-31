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

* **Tính Khả Dụng (Availability) & Kiến Trúc:** `TaskKernel` đã được tách rời (Decoupled) khỏi cơ sở dữ liệu vật lý thông qua Dependency Injection (`KernelStorage`), hỗ trợ thay thế linh hoạt (ví dụ: in-memory, Postgres, SQLite).
* **Soak Test (Độ Bền):** **Đã PASS.** Kiểm thử chịu tải tự động (629 task liên tục, 22 batch) đạt 100% Ledger Consistency (tính nhất quán của sổ cái trạng thái) mà không rò rỉ hay deadlock.
* **Môi Trường LLM Độc Lập (Environment-Agnostic):** LLM Gateway không còn khóa cứng vào OpenRouter. Hệ thống tự động ưu tiên nhận diện và giao tiếp thông qua các chuẩn API tương thích OpenAI (`OPENAI_API_KEY`, `OPENAI_BASE_URL`) nếu được cung cấp ở môi trường triển khai mới.
* **Test Coverage & Release Gate:** Hệ thống tích hợp **Mutation Testing** (chạy dry-run qua CI) và **Test Factory Daemon** tự động sinh test để kiểm soát chất lượng mã nguồn khi có thay đổi. Hiện tại vẫn đang củng cố độ bao phủ (coverage) và cần hoàn thiện ranh giới Sandbox trên Windows.

## Quick Start

```bash
pip install -r requirements.txt

# Yêu cầu biến môi trường (.env)
#   SCP_JWT_SECRET=<random hex 64>
#   SCP_ADMIN_KEY=<random urlsafe 24>

# Cấu hình API cho LLM (chọn 1 trong 2):
# Dùng Custom OpenAI-Compatible API (ưu tiên):
#   OPENAI_API_KEY=<your key>
#   OPENAI_BASE_URL=<your base url>
#   OPENAI_MODEL=<your model>
# Hoặc dùng OpenRouter:
#   OPENROUTER_API_KEY=<your openrouter key>
#   OPENROUTER_MODEL=<your model>

python -m scp 8000
```

## Cấu trúc Hệ Thống

| Module lõi | Mô tả thực tế |
|---|---|
| `scp/task_kernel.py` | Trái tim của hệ thống. Quản lý State Machine, cấp Lease (Khóa tác vụ), và Dependency Injection (DI) qua `KernelStorage`. |
| `scp/kernel_storage.py` | Abstraction layer cho lưu trữ trạng thái TaskKernel (SQLite, v.v.). |
| `scp/hands/planner.py` | Quản lý DAG Plan. Ép buộc phân quyền Capability cho AI ngoài, mở luồng tự nâng quyền cho định danh SCP. |
| `scp/llm_gateway/` | Gateway gọi API linh hoạt, không khóa nhà cung cấp (vendor lock-in), tự động failover và ưu tiên Env API. |
| `scp/security/` | Quản lý Sandbox và phân quyền hệ thống. |
| `scripts/run_mutation_ci.py` | Trình đánh giá Release Gate đảm bảo Mutation Score. |
| `scripts/scp_test_factory.py` | Trình sinh test tự động dựa vào Autofix. |

## Giấy phép
MIT License.

