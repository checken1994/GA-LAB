# SCP — Structured Constraint Protocol (V3 Enterprise)

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Status: V3 Reality-Checked Kernel](https://img.shields.io/badge/status-Reality_Checked_Kernel-red.svg)](#)

> **"Thực tế > Mô hình. PASS ≠ TRUE."**
> SCP V3 là một hệ thống kiểm chứng chéo (Independent Verification Kernel) tàn nhẫn, sinh ra từ triết lý không bao giờ tin tưởng vào suy đoán hay ảo giác của AI.

## Thực Trạng Sau Đợt Đại Tu V3 (Reality Check)
Vào tháng 08/2026, SCP đã trải qua một đợt Đánh giá Khắt khe (Reality Audit). Bản báo cáo này đã xé toạc lớp áo "hoàn hảo" của các phiên bản trước, vạch trần các ảo giác như: *Sandbox giả cầy*, *Regex đếm từ mạo danh Verifier*, và *Lỗ hổng cú pháp làm sập cổng bảo vệ*.

**SCP V3 đã được đập đi xây lại dựa trên nguyên lý Fail-Closed:**
1. **OS-Level Isolation:** Chuyển đổi từ `subprocess.run` trần trụi sang `ProcessIsolationEnvironment` kết hợp **Windows Job Objects**. Mọi tiến trình con bị giới hạn nghiêm ngặt về RAM (512MB) và chặn lây lan.
2. **Immutable Policy Gate:** Khóa chặt `FORBIDDEN_PATTERNS` thành dữ liệu bất biến. Các module AutoFix (Agent) hoàn toàn mất khả năng lách luật bằng cách tự sửa mã bảo vệ (Meta-bypass).
3. **LLM-As-A-Judge độc lập:** Khai tử thuật toán "Grounded Ratio" đếm từ ngô nghê. SCP V3 dùng một LLM trung lập (OpenRouter Gateway) để đối chiếu "Bằng chứng" và "Câu trả lời". Thiếu bằng chứng hoặc LLM sập -> Trả về FAIL.
4. **Zero-Trust API:** Cổng `/ask` được rào bằng JWT, OpenTelemetry, và Rate Limiting. Bất cứ lệnh gọi API nào không có Authorization Bearer Token hợp lệ sẽ bị từ chối ngay ở vòng gửi xe.

## Nguyên Lý Bất Biến (SCP DNA)
Cốt lõi của SCP không nằm ở chỗ sinh ra câu trả lời hay, mà là **Kháng cự lại bản chất xác suất của AI**. 
- AI (Generator) đưa ra đáp án.
- SCP (Verifier) kiểm chứng độc lập bằng bằng chứng thực tế.
- Nếu không chứng minh được, SCP sẽ đóng sập cửa và ghi lỗi: `[SCP: Answer withheld — evidence not verified]`.

## Bộ Skill SCP
SCP được trang bị bộ 9 kỹ năng chuyên biệt cho Agent (đặt tại `.agents/skills/`), tập trung vào:
- **`scp-dna`**: Thấm nhuần triết lý Reality > Model.
- **`scp-reality-verifier`**: Ép buộc kiểm chứng kết quả thực tế thay vì tin lời model.
- **`scp-capability-security-review`**: Đánh giá an toàn cổng quyền hạn.
- Cùng các cơ chế phục hồi hệ thống (Watchdog) và Troubleshoot khởi động.

*(Tài liệu lịch sử Khởi thủy V1-V14 của SCP hiện được lưu trữ tại `collatz-archive` repository).*
