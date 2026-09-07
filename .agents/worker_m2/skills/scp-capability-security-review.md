---
name: scp-capability-security-review
description: Review capability security, policy enforcement, sandbox, egress, filesystem scope, secret handling và approval của SCP agent/tool.
---

# SCP Capability Security Review

## Mục tiêu
Kiểm tra quyền theo **task + attempt + resource + action**, không đánh giá bằng role rộng như `admin` hoặc `agent`. Mọi kết luận phải phân biệt policy decision, enforcement thực tế và bằng chứng runtime.

## Fail-Closed & Secret Handling
- Secret broker: không raw secret trong prompt, screenshot, stdout, log, exception, trace hoặc artifact.
- Không có fallback secret trong source code.
- Missing / invalid secret phải raise exception ngay lập tức (fail-closed).
