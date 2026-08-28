# SCP — Structured Constraint Protocol

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Status: Agent Runtime Candidate](https://img.shields.io/badge/status-Agent%20Runtime%20Candidate-orange.svg)](#trạng-thái-hiện-tại)

> **SCP là một dự án nghiên cứu về lớp control/runtime cho AI agent: giới hạn quyền, ghi bằng chứng, kiểm tra kết quả và xử lý trạng thái không chắc chắn.**

## Tóm tắt trung thực

SCP không phải là một mô hình ngôn ngữ lớn hơn. SCP là một codebase thử nghiệm các cơ chế nằm giữa agent, tool và môi trường mà agent có thể tác động. Mục tiêu là giảm các lỗi nguy hiểm như retry mù sau timeout, thực thi khi thiếu quyền, coi lời tự báo cáo của model là bằng chứng, hoặc ghi nhận một tác vụ là hoàn thành khi postcondition chưa được kiểm tra.

Trạng thái hiện tại của repository là **Agent Runtime Candidate / BROKEN_CANDIDATE**. Một số control, contract test, bounded runtime smoke và recovery path đã được kiểm chứng trong phạm vi cụ thể. Điều đó **không** có nghĩa SCP đã chứng minh được uptime 24/7 không gián đoạn, production readiness, OS-level sandbox, complete security, official Ragas/ARES pass hoặc vị trí TOP 1.

## Đánh Giá Khắt Khe (Reality Check - 08/2026)
Hệ thống vừa trải qua một đợt đánh giá độc lập tàn nhẫn.
- **Điểm yếu đã xác nhận:** Sandbox (ProcessIsolationEnvironment) còn nhiều lỗi trên Windows và chưa hỗ trợ Linux. Xác thực JWT đang được khắc phục. Benchmark từng bị lọt đáp án (data leakage) và đang được viết lại bằng Exact-Match.
- **Thành tựu cốt lõi còn giữ được:** Durable Task Kernel, Capability Fencing, và Evidence Journal.

Hệ thống TUYỆT ĐỐI không phải là "V3 Enterprise". Đây là một phiên bản Candidate đang nỗ lực đạt đến ngưỡng tin cậy. Tất cả những "lời hứa" về Zero-Trust và Isolation đang được xây dựng dựa trên nguyên lý Fail-Closed và Reality > Model.

## Hướng Dẫn Chạy (Quick Start)

### 1. Cài đặt Dependency
Yêu cầu Python 3.10+. Khuyến nghị dùng môi trường ảo (venv):
```bash
python -m venv venv
.\venv\Scripts\activate   # Windows
# source venv/bin/activate # Linux/Mac

pip install -r requirements.txt
```

### 2. Cấu hình Biến Môi Trường (ConfigContract)
SCP áp dụng Zero-Trust ngay từ lúc khởi động. Nếu thiếu biến môi trường, server sẽ từ chối boot.
Tạo file `.env` tại thư mục gốc:
```env
# Tạo bằng: python -c "import secrets; print(secrets.token_hex(32))"
SCP_JWT_SECRET="chuoi-bi-mat-cua-ban"

# Tạo bằng: python -c "import secrets; print(secrets.token_urlsafe(24))"
SCP_ADMIN_KEY="mat-khau-admin-cua-ban"
```
*(Lưu ý: Không được dùng các giá trị như `admin`, `password` — ConfigContract sẽ bắt lỗi).*

### 3. Kiểm chứng Toàn Hệ Thống (Pre-Push Gate)
Trước khi chạy server, hệ thống bắt buộc phải qua bài kiểm tra sức khỏe, bảo mật, và format:
```powershell
# Trên Windows PowerShell:
$env:SCP_JWT_SECRET="chuoi-bi-mat"
$env:SCP_ADMIN_KEY="mat-khau-admin"
.\pre_push_gate.ps1
```
Gate này sẽ:
1. Chạy `scripts/check_imports_vs_requirements.py` để chống gãy manifest.
2. Boot server trên port 8002.
3. Test Health, cấp JWT Token và test RAG verification path.

### 4. Khởi động Server Thủ Công
```bash
python -m scp 8002
```

### 5. Benchmark & Grader Độc Lập
Để kiểm tra năng lực của SCP mà không bị dính ảo giác "tự chấm điểm", chạy benchmark và grader riêng biệt:
```bash
# 1. Chạy benchmark (lưu kết quả raw)
python benchmark/run_world_exam.py benchmark/gsm8k_sample_10.jsonl

# 2. Chấm điểm độc lập bằng Grader
python benchmark/grader.py raw_results.jsonl --dataset gsm8k
```
