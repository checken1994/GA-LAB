# Original User Request

## 2026-09-07T11:59:14Z

# Teamwork Project Prompt — GAP-05 + GAP-06 + GAP-08 + GAP-09

Dự án SCP (Agent OS) đang trong quá trình vá các Tử huyệt bảo mật nghiêm trọng
được phát hiện trong Delta Audit. GAP-01, 02, 03, 04, 07 đã được vá và xác nhận
thực tế (450 tests PASS). Nhiệm vụ này xử lý 4 GAP tiếp theo theo thứ tự ưu tiên.

Working directory: c:\Users\check\Downloads\scp
Branch: omega/gap-01-remediation
Integrity mode: benchmark

MANDATORY BINDING: You are strictly bound by Zero-Trust and Fail-Closed principles.
You MUST adhere to FA-01 through FA-10. You are FORBIDDEN from self-granting
authority or simulating PASS results. Any code modifications must explicitly enforce
boundaries at the Database/Hardware level, not via RAM/Variables.

---

## Requirements

### R1. GAP-05: Xác minh và loại bỏ RLock Placebo

Kiểm tra toàn bộ `scp/kernel_storage.py` và toàn bộ codebase `scp/` xem có
`threading.RLock()` nào còn tồn tại không (dùng `with self._lock:` bao quanh
logic đọc/ghi). Nếu còn tồn tại: xóa bỏ, chứng minh hệ thống vẫn an toàn
nhờ OCC. Nếu không còn: lập báo cáo bằng chứng thực tế (FA-09 Exploit Mandate
— phải chứng minh không tồn tại, không phải giả định).

### R2. GAP-06: SQLite SPOF Documentation + Guard

`make_storage()` trong `kernel_storage.py` chỉ hỗ trợ SQLite — đây là
Single Point of Failure cho môi trường distributed. Yêu cầu:
- Thêm WARNING rõ ràng trong docstring của `make_storage()`.
- Thêm `SCP_STORAGE_BACKEND` environment variable check: nếu set giá trị
  khác `sqlite` thì raise `NotImplementedError` với hướng dẫn rõ ràng.
- Viết test kiểm tra guard này hoạt động đúng.

### R3. GAP-08: CapabilityToken HMAC Signing

`scp/core/capability_token.py`: `CapabilityToken` hiện là plain dataclass,
không có chữ ký. Bất kỳ ai cũng có thể forge token tùy ý.
Yêu cầu:
- Thêm HMAC-SHA256 signing khi `issue()` token.
- Thêm signature verification khi `validate()` token.
- Token thiếu/sai chữ ký → `InvalidTokenSignatureError` (fail-closed).
- Backward compat: token cũ không có sig → bị reject, không silently accept.

### R4. GAP-09: Xóa Hardcoded Fallback Secret

`scp/core/capability_token.py` có hardcoded fallback:
`b"dev-secret-do-not-use-in-prod-12345"`.
Yêu cầu:
- Xóa fallback secret.
- Nếu `SCP_CAPABILITY_SECRET` không được set → raise `MissingSecretError`
  ngay khi import module (fail-closed hoàn toàn).
- Cập nhật `.env.example` với hướng dẫn set secret.
- Cập nhật test fixtures để inject secret đúng cách.

---

## Acceptance Criteria

### Anti-Placebo (FA-09 bắt buộc)
- [ ] Mỗi GAP phải có script/probe chứng minh trạng thái RED trước khi sửa
  (hoặc bằng chứng thực tế rằng GAP đã không còn tồn tại nếu đã được fix trước).
- [ ] Sau khi sửa: probe chuyển GREEN, không phải chỉ static analysis.

### Test Suite
- [ ] `pytest tests/ -q` PASS 100% (>= 450 tests), exit code 0.
- [ ] `python tools/t00_meta_audit.py` PASS, 0 new regressions.

### Adversarial Review
- [ ] Ít nhất 1 Challenger thử forge token, bypass secret check, hoặc
  inject payload qua environment variable.
- [ ] Kết quả Challenger: tất cả bị chặn (fail-closed).

### Handoff
- [ ] Báo cáo handoff tại `.agents/sentinel_4/handoff.md` với đầy đủ
  HEAD_SHA, TREE_HASH, runtime version, evidence links.

## 2026-09-07T12:23:07Z

# Teamwork Project Prompt — GAP-05 + GAP-06 + GAP-08 + GAP-09

Dự án SCP (Agent OS) đang trong quá trình vá các Tử huyệt bảo mật nghiêm trọng
được phát hiện trong Delta Audit. GAP-01, 02, 03, 04, 07 đã được vá và xác nhận
thực tế (482 tests PASS). Nhiệm vụ này xử lý 4 GAP tiếp theo.

Working directory: c:\Users\check\Downloads\scp
Branch: omega/gap-01-remediation
Integrity mode: benchmark

MANDATORY BINDING: You are strictly bound by Zero-Trust and Fail-Closed principles.
You MUST adhere to FA-01 through FA-10. You are FORBIDDEN from self-granting
authority or simulating PASS results. Any code modifications must explicitly enforce
boundaries at the Database/Hardware level, not via RAM/Variables.

CONTEXT: Một đợt teamwork trước đã hoàn thành Milestone 1 (GAP-05 xác nhận + GAP-06 guard)
nhung bị ngắt do quota. Kiểm tra lại kết quả Milestone 1 trước, rồi tiếp tục Milestone 2+3.

## Requirements

### R1. GAP-05: Xác minh RLock Placebo đã vắng mặt
Kiểm tra toàn bộ `scp/` xem có `threading.RLock()` nào còn tồn tại không.
Nếu không còn: lập báo cáo bằng chứng thực tế (chạy grep/rg thực tế trên shell).

### R2. GAP-06: SQLite SPOF Guard
`make_storage()` trong `kernel_storage.py` phải:
- Có WARNING trong docstring.
- Kiểm tra env var `SCP_STORAGE_BACKEND`: nếu khác `sqlite` → raise `NotImplementedError`.
- Có test bảo vệ guard này.
Nếu Milestone 1 đã làm xong: xác nhận bằng chạy pytest — không giả định.

### R3. GAP-09: Xóa Hardcoded Fallback Secret
`scp/core/capability_token.py` có hardcoded fallback `b"dev-secret-do-not-use-in-prod-12345"`.
- Xóa fallback secret hoàn toàn.
- Nếu `SCP_CAPABILITY_SECRET` không set → raise `MissingSecretError` (fail-closed).
- Cập nhật `.env.example`.
- Cập nhật test fixtures inject secret đúng cách.

### R4. GAP-08: CapabilityToken HMAC-SHA256 Signing
`scp/core/capability_token.py`:
- Thêm HMAC-SHA256 signing khi `issue()` token.
- Thêm signature verification trong `validate()`.
- Token sai/thiếu chữ ký → `InvalidTokenSignatureError` (fail-closed).
- Token cũ không có sig → bị reject (không silently accept).

## Acceptance Criteria
- [ ] Anti-Placebo: mỗi GAP có probe RED trước / GREEN sau (hoặc bằng chứng thực tế không tồn tại).
- [ ] `pytest tests/ -q` PASS 100% (>= 482 tests), exit 0.
- [ ] `python tools/t00_meta_audit.py` PASS, 0 new regressions.
- [ ] Challenger thử forge token + bypass secret → bị chặn hoàn toàn.
- [ ] Handoff tại `.agents/sentinel_4/handoff.md` với HEAD_SHA, TREE_HASH, evidence links.
