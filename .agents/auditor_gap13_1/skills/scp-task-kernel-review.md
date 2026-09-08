# Local copy of scp-task-kernel-review SKILL.md
---
name: scp-task-kernel-review
description: Review kiến trúc và bằng chứng của SCP Task Kernel gồm state machine, event journal, queue, lease, checkpoint, idempotency, verifier, recovery, observability và kill switch.
---

# SCP Task Kernel Review
## Mục tiêu
Xác định Task Kernel có thật sự là source of truth cho lifecycle hay chỉ là một tập module rời. Review theo hợp đồng, transition và test runtime; không đánh giá bằng số file hoặc sơ đồ đẹp.
## State machine tối thiểu
CREATED → PLANNING → READY → QUEUED → LEASED → RUNNING
RUNNING → WAITING_TOOL → VERIFYING → COMPLETED
RUNNING/WAITING_TOOL → RECOVERING/UNKNOWN/HUMAN_REVIEW/FAILED/CANCELLED
RECOVERING → CHECKPOINTED/QUEUED/HUMAN_REVIEW/FAILED
State cuối COMPLETED, FAILED, CANCELLED không được tự quay lại state chạy. UNKNOWN không được dispatch side effect mới.
