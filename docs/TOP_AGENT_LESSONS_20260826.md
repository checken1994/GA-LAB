# Bài học từ hệ thống agent hàng đầu và phần đã triển khai

## Phạm vi

Tài liệu này không xếp hạng hệ thống nào là “TOP 1” tuyệt đối. Nó ghi lại những pattern được tài liệu chính thức mô tả, sau đó đối chiếu với khoảng trống của SCP và chỉ đánh dấu **đã triển khai** khi có code/test tương ứng.

## Bằng chứng tham khảo

| Hệ thống / chuẩn | Pattern quan sát được | Áp dụng vào SCP |
|---|---|---|
| [OpenAI Agents SDK](https://openai.github.io/openai-agents-python/) | Primitive nhỏ: agent/tool, handoff, guardrail; tracing, sessions, human-in-the-loop và sandbox | SCP giữ TaskKernel/Hands/policy hiện tại và thêm trace/span contract additive, không thay thế ledger |
| [OpenAI tracing](https://openai.github.io/openai-agents-python/tracing/) | Trace là một workflow end-to-end; span có parent, timestamps, status; có cảnh báo dữ liệu nhạy cảm | `scp/core/trace_contract.py` có `trace_id`, `span_id`, `parent_id`, timestamps, status, hashes và redaction |
| [Anthropic — Building effective agents](https://www.anthropic.com/engineering/building-effective-agents) | Ưu tiên giải pháp đơn giản; minh bạch kế hoạch; thiết kế và kiểm thử agent-computer interface | Chọn contract nhỏ và test boundary thay vì nhập nguyên framework hoặc thêm agent loop |
| [Temporal — Durable Execution](https://temporal.io/blog/what-is-durable-execution) | Crash không được làm mất tiến trình; state phải được phục hồi qua process/machine | SCP giữ checkpoint/lease/reconcile hiện tại; durable execution cấp Temporal vẫn là khoảng trống chưa claim |
| [MCP Specification](https://modelcontextprotocol.io/specification/2026-07-28) | JSON-RPC, capability negotiation, cancellation, progress, error reporting, consent và tool safety | Ghi backlog connector/task contract; chưa claim MCP conformance |
| [Google A2A announcement](https://developers.googleblog.com/en/a2a-a-new-era-of-agent-interoperability/) | Agent Card, task lifecycle, artifacts, long-running updates, auth và content negotiation | Ghi backlog protocol adapter; chưa claim A2A interoperability |

## Phần đã triển khai trong branch này

`RequestRunLedger` tạo trace root cho route dùng `@traced_request`; `stage()` tạo child span dưới root đang active. Span chỉ lưu hash input/output, metadata bounded và giá trị đã redact. Span luôn được đóng ở nhánh success, exception hoặc audit-ledger failure. Nếu ghi span thất bại, request ledger và policy decision không bị biến thành lỗi mới; observability là best-effort.

Các contract test trong `tests/test_trace_contract.py` chứng minh parent-child linkage, start/finish order, duration không âm, hash không lộ dữ liệu, redaction khóa nhạy cảm, status bất hợp lệ chuyển thành `ERROR`, double-finish bị từ chối và decorator giữ nguyên `SUCCESS`/`ledger_status=OK`.

`ARCHITECTURE_CANONICAL_ROOT.md`, `reports/PORT_BACKLOG_SCP_AGENT_TO_GA_LAB_20260826.json` và `tools/verify_canonical_root.py` biến quyết định một thư mục gốc thành policy có thể kiểm tra. Code từ repo phụ không được copy toàn bộ; trace implementation cũ bị thay thế bằng native port có lock/fsync của GA-LAB.

## Những phần vẫn chưa thể gọi là đã hoàn thiện

Một trace contract cục bộ không phải OpenTelemetry exporter; chưa có bằng chứng distributed tracing hoặc multi-host. Một checkpoint/lease của SCP không tự động tương đương Temporal Durable Execution. Contract nội bộ không phải MCP/A2A conformance. Root span không chứng minh mọi route hoặc mọi công cụ đều được instrument nếu route không đi qua decorator. RAG Gold/Ragas/ARES và OS-level isolation vẫn giữ trạng thái theo evidence gate hiện tại.

## Nguyên tắc thực hiện tiếp

Mọi port tiếp theo phải có: provenance của file nguồn, review license, lý do không trùng logic hiện tại, focused tests, CI, full loopback smoke trên `127.0.0.1:8002`, clean stop và rollback ref. Không được đổi trạng thái BLOCKED thành PASS chỉ bằng cách đổi evaluator hoặc tự sinh dữ liệu review.
