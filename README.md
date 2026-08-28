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

### Yêu cầu
Cài đặt các dependency cần thiết (yêu cầu Python 3.10+):
```bash
pip install -r requirements.txt
```

### Cấu hình biến môi trường
Tạo file `.env` ở thư mục gốc:
```env
# Yêu cầu bắt buộc để JWT hoạt động (Zero-Trust)
SCP_JWT_SECRET="chon-mot-chuoi-bi-mat-tu-tao-ra"
SCP_ADMIN_KEY="mat-khau-admin-cua-ban"
SCP_PRODUCTION_MODE=0
```

### Khởi động Server
Bạn phải vượt qua `pre_push_gate.ps1` (kịch bản kiểm tra trước khi đẩy code) để đảm bảo server còn sống sót:
```bash
python -m scp 8002
```

### Tạo Token và Kiểm chứng chéo (The Loop)
```bash
# Lấy Token từ Endpoint Auth mới
curl -X POST http://127.0.0.1:8002/auth/token -H "Content-Type: application/json" -d '{"admin_key": "mat-khau-admin-cua-ban"}'

# Gửi kết quả để Thẩm phán kiểm chứng (Fail-Closed)
curl -X POST http://127.0.0.1:8002/ask \
    -H "Authorization: Bearer <TOKEN_VUA_LAY>" \
    -H "Content-Type: application/json" \
    -d '{
        "question": "1+1 bằng mấy?",
        "contexts": ["1+1=2"],
        "session_id": "test_01"
    }'
```
