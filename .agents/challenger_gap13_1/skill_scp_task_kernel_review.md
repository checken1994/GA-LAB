# SCP Task Kernel Review

## Mục tiêu

Xác định Task Kernel có thật sự là source of truth cho lifecycle hay chỉ là một tập module rời. Review theo hợp đồng, transition và test runtime; không đánh giá bằng số file hoặc sơ đồ đẹp.

## Các năng lực phải kiểm tra

| Năng lực | Điều phải chứng minh |
|---|---|
| Task identity | Mỗi task có ID, owner, deadline, version và risk profile |
| State machine | Transition hợp lệ, có precondition/postcondition, không module tự set state |
| Event journal | Append-only, sequence tăng, hash chain, idempotent event ID |
| Projection | Có thể rebuild từ journal; journal thắng projection |
| Lease | TTL, heartbeat, fencing; worker cũ bị từ chối bằng `STALE_LEASE` |
| Queue/resource | Priority, fairness, quota, deadline và resource claim đo được |
| Checkpoint | Hash/reference, trước và sau side-effect boundary, không chứa secret |
| Idempotency | Logical action key ổn định qua các attempt |
| Verifier | Độc lập với planner/model, kiểm evidence và postcondition |
| Recovery | Phân biệt retryable, unknown-state, policy-denied, human-required |
| Kill switch | Task/cell/global kill độc lập với dashboard |
| Observability | Trace từ request → task → attempt → lease → tool → evidence → event |

## Acceptance tests tối thiểu

| Test | Kết quả bắt buộc |
|---|---|
| Hai worker claim một task | Chỉ một lease hợp lệ |
| Heartbeat mất | Lease hết hạn, task vào recovery |
| Worker cũ commit | Bị từ chối `STALE_LEASE` |
| Event gửi lại | Không duplicate event |
| Projection bị xóa | Rebuild đúng từ journal |
| Worker chết trước tool | Resume an toàn |
| Worker chết sau submit | `UNKNOWN` hoặc reconcile, không retry mù |
| Global kill | Không commit action mới |
| Dashboard tắt | Kernel/audit vẫn sống |
| Checkpoint hash sai | Không resume |
