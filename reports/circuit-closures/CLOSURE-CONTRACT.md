# HỢP ĐỒNG ĐÓNG MẠCH SCP — Definition of Done chuẩn hóa (v1)
Nguyên tắc: "ĐÓNG" là tuyên bố có phạm vi, mang falsification_status riêng + missing pieces.
D0 Khóa phạm vi: liệt kê file/route/service + SHA nền (sha_pin) + owner; ngoài danh sách không tính.
D1 Contract tests: suite chính exit 0; lưu toàn bộ output làm artifact; cấm mock golden path; cấm skip/xfail; cấm assertion mơ hồ.
D2 Runtime proof: service LISTENING tại SHA pin; /health và /ready 200; chạy luồng thật (HTTP/WS/CLI); trace journal hash-chain; service identity commit == SHA pin.
D3 Adversarial: suite adversarial exit 0; ≥1 probe khai thác thật chứng minh fail-closed.
D4 Ratchet bảo mật: Mimosa focus phạm vi: HIGH = 0 (FP phải kèm xác minh tay); HIGH toàn dự án không tăng so mốc trước.
D5 Kiểm chứng độc lập: reviewer ngoài chuỗi fix, không chung context/prompt; duyệt từng claim; cấm self-approve.
D6 Fail loudly: AST phạm vi: 0 khối except...: pass không log; suy thoái có field quan sát; đường lỗi log warning+.
D7 Wiring & tài liệu: 0 TODO dangling phạm vi; WIRED/CLOSED tại module header; flow map + runbook cập nhật; missing pieces liệt kê.
D8 Closure record: reports/circuit-closures/MXX-closure.json (sha_pin, hash evidence, checklist D1–D7, known gaps, falsification_status, chữ ký reviewer); commit closure cùng commit đóng mạch.
Điều khoản hồi quy: closure hiệu lực tại sha_pin; commit sau chạm file phạm vi phải chạy lại tối thiểu D1+D2+D4; đổi kiến trúc phải đóng lại toàn bộ D1–D8.
Điều mạch ĐÓNG không tuyên bố: không soak/uptime; không production ngoài phạm vi; không an toàn trước lớp tấn công chưa mô hình hóa.
Phụ lục 14 mạch: M1 Boot&Background (T01_boot+lifespan; probe watchdog+health); M2 Ask&Chat (flow_02; WS+trace kernel); M3 OpenAI-compat (flow_03); M4 Control&Hands (flow_04+T03_capability); M5 Agent/Call (flow_05); M6 Prediction (flow_06); M7 AutoFix&Policy (flow_07); M8 Audit/Benchmark (flow_08); M9 Threat&Counter (flow_09); M10 Streaming (flow_10); M11 Admin/Import (flow_11); M12 Background WHY (flow_12); M13 Data sources&Learning (flow_13); M14 v106 Audit/Self-model (flow_17_self_model_capability + T11_release).
