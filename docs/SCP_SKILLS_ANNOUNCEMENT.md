# Introducing SCP Skills: Evidence-First Controls for AI-Agent Runtimes

## English

SCP Skills is a focused, open engineering skill pack for teams building AI-agent runtimes that must do more than produce a plausible answer. The pack treats **evidence, capability boundaries, recovery, verification, and rollback** as first-class engineering concerns.

The pack contains nine reusable skills:

| Skill | Focus |
|---|---|
| `scp-dna` | Evidence-first reasoning, missing-piece detection, and self-audit |
| `scp-capability-security-review` | Task-scoped capability, resource boundaries, approval, egress, and secret safety |
| `scp-computer-use-recovery` | Safe recovery when a browser/tool may have already caused a side effect |
| `scp-reality-verifier` | Static vs integration vs end-to-end vs recovery proof |
| `scp-release-evidence-gate` | Reproducible release, runtime, security, chaos, and rollback gates |
| `scp-runtime-audit` | Process, port, health, readiness, and live evidence checks |
| `scp-safe-latency-optimizer` | Lower latency without bypassing policy, verifier, revocation, or approval |
| `scp-startup-troubleshooter` | Evidence-led diagnosis of launcher, dependency, port, and readiness failures |
| `scp-task-kernel-review` | Durable task identity, state machine, journal, lease, checkpoint, idempotency, and kill switch |

A skill is a workflow contract, not a permission grant. Before an external write, upload, publish, delete, payment, credential change, or privilege change, the runtime still needs a task-scoped capability, an explicit policy decision, the required approval, an independent postcondition, and an audit trail.

The pack uses four evidence levels:

1. **Static:** a file, route, schema, or assertion exists.
2. **Integration:** components connect in a bounded interaction.
3. **End-to-end:** a real task crosses planning, policy, tool, observation, verification, audit, and artifact boundaries.
4. **Recovery:** end-to-end proof plus crash, timeout, lease, unknown-state, or restart handling.

A green test is reported as `PASS_WITHIN_SCOPE`; it is not automatically a claim of zero bugs, production safety, or top performance. When state or evidence is unclear, the safe outcome is `UNKNOWN`, `RECONCILING`, `HUMAN_REVIEW`, or `BLOCKED` rather than a blind retry.

The complete pack is available in [`skills/`](../skills/README.md). The surrounding SCP repository contains an experimental agent-runtime implementation and explicitly documents its current limitations. Contributions are welcome when they include a small reproducible example, focused tests, a rollback path, and clear evidence provenance.

## Tiếng Việt

**SCP Skills** là bộ skill mã nguồn mở tập trung vào việc xây dựng runtime cho AI agent có kiểm soát. Mục tiêu không chỉ là tạo ra câu trả lời nghe có vẻ đúng, mà còn phải biết agent được phép làm gì, thực tế đã xảy ra gì, nếu mất kết nối thì có thể đã gây side effect hay chưa, và bằng chứng nào đủ để kết luận.

Bộ này có 9 skill: suy luận bằng evidence; review capability và bảo mật; recovery cho computer-use; kiểm chứng reality; release gate; runtime audit; tối ưu latency nhưng không bỏ lớp an toàn; sửa lỗi startup; và review Task Kernel durable.

Đây là **workflow hướng dẫn**, không phải model AI, sandbox, secret broker, giấy chứng nhận bảo mật hoặc lời hứa rằng mọi đường chạy đã production-ready. `PASS_WITHIN_SCOPE` chỉ có nghĩa là chưa thấy lỗi trong phạm vi test/evidence đã chạy. Nếu trạng thái không rõ, SCP ưu tiên `UNKNOWN` hoặc `HUMAN_REVIEW`, không retry mù.

Xem gói đầy đủ tại [`skills/README.md`](../skills/README.md) và trạng thái trung thực của runtime tại [README chính](../README.md).

## Scope and limitations

This release publishes the reusable skill documents and their review contracts. It does not claim that the SCP runtime has complete security, uninterrupted 24/7 operation, OS-level isolation, official Ragas/ARES success on 1,000 RAG questions, or superiority over every other agent system. Those claims require independent workload-specific evidence.

## License

MIT for this repository. Third-party tools, models, and dependencies may have separate licenses.
