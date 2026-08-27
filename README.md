# SCP — Structured Constraint Protocol

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![CI: SCP Release Gate](https://img.shields.io/badge/CI-SCP%20Release%20Gate-blue.svg)](https://github.com/checken1994/GA-LAB/actions/workflows/scp-release-gate.yml)
[![Status: Agent Runtime Candidate](https://img.shields.io/badge/status-Agent%20Runtime%20Candidate-orange.svg)](#trạng-thái-hiện-tại)

> **SCP là một dự án nghiên cứu về lớp control/runtime cho AI agent: giới hạn quyền, ghi bằng chứng, kiểm tra kết quả và xử lý trạng thái không chắc chắn.**

## Tóm tắt trung thực

SCP không phải là một mô hình ngôn ngữ lớn hơn. SCP là một codebase thử nghiệm các cơ chế nằm giữa agent, tool và môi trường mà agent có thể tác động. Mục tiêu là giảm các lỗi nguy hiểm như retry mù sau timeout, thực thi khi thiếu quyền, coi lời tự báo cáo của model là bằng chứng, hoặc ghi nhận một tác vụ là hoàn thành khi postcondition chưa được kiểm tra.

Trạng thái hiện tại của repository là **Agent Runtime Candidate / CANDIDATE_NOT_PROVEN**. Một số control, contract test, bounded runtime smoke và recovery path đã được kiểm chứng trong phạm vi cụ thể. Điều đó **không** có nghĩa SCP đã chứng minh được uptime 24/7 không gián đoạn, production readiness, OS-level sandbox, complete security, official Ragas/ARES pass hoặc vị trí TOP 1.

## Bộ Skill SCP

SCP có một bộ 9 Skill chuyên biệt cho việc suy luận bằng evidence, cấp quyền an toàn, recovery sau lỗi computer-use, reality verification, release gate, runtime audit, tối ưu latency có bảo toàn safety, startup troubleshooting và Task Kernel review. Đây là các workflow dùng để **kiểm soát và chứng minh** agent/runtime, không phải model AI hoặc giấy chứng nhận bảo mật.

Xem toàn bộ gói tại [`skills/README.md`](skills/README.md). Các skill riêng lẻ gồm [`scp-dna`](skills/scp-dna/SKILL.md), [`capability-security-review`](skills/scp-capability-security-review/SKILL.md), [`computer-use-recovery`](skills/scp-computer-use-recovery/SKILL.md), [`reality-verifier`](skills/scp-reality-verifier/SKILL.md), [`release-evidence-gate`](skills/scp-release-evidence-gate/SKILL.md), [`runtime-audit`](skills/scp-runtime-audit/SKILL.md), [`safe-latency-optimizer`](skills/scp-safe-latency-optimizer/SKILL.md), [`startup-troubleshooter`](skills/scp-startup-troubleshooter/SKILL.md) và [`task-kernel-review`](skills/scp-task-kernel-review/SKILL.md).

## Vấn đề SCP đang nghiên cứu

Một agent thông thường có thể xử lý timeout như sau:

```text
Action sent
   ↓
Network timeout
   ↓
Agent assumes failure
   ↓
Blind retry
   ↓
Possible duplicate side effect
```

Timeout chỉ cho biết client chưa nhận được kết quả. Nó không tự chứng minh side effect chưa xảy ra. SCP thử một đường xử lý thận trọng hơn:

```text
Timeout
   ↓
RECONCILING
   ↓
Check the actual state
   ↓
Determine whether the side effect occurred
   ↓
VERIFY
   ↓
Retry only when safe; otherwise UNKNOWN / human review
```

Các nguyên tắc thiết kế chính là **Reality > Model**, **Evidence > Belief**, **Missing Piece > Optimization**, **Default-Deny**, **Verification** và **Recovery**. Đây là nguyên tắc nghiên cứu của dự án, không phải lời chứng nhận rằng mọi đường chạy hiện tại đều đã thực thi đầy đủ các nguyên tắc đó.

## Luồng control/runtime đang được kiểm chứng

```text
Agent
  ↓
Goal → Plan
  ↓
Policy / Capability / Approval
  ↓
Action or Dry-run
  ↓
Observation / Evidence
  ↓
Independent verification
  ↓
COMPLETED / RECONCILING / UNKNOWN / HUMAN_REVIEW
```

SCP **chưa** chứng minh rằng mọi endpoint đều đi qua một kernel lifecycle duy nhất. Context-backed/RAG `/ask` có thể dùng `AskKernelAdapter` khi được bật và có context; chat thông thường vẫn giữ JudgeCore path. Đây là giới hạn quan trọng khi đọc các sơ đồ kiến trúc trong repository.

## Các capability hiện có trong code

| Nhóm | Thành phần hiện có | Mức bằng chứng hiện tại |
|---|---|---|
| Task execution | SQLite WAL, state machine, event journal, task identity, idempotency, lease, heartbeat, fencing, checkpoint và recovery states | Có contract/unit test và một phần integration; chưa có chaos proof cho mọi state |
| Verification | Evidence/provenance fields, verdicts `PASS`, `FAIL`, `UNKNOWN`, `ESCALATE`, `KILL`, postcondition-oriented checks | Đã kiểm tra trong bounded scope; chưa chứng minh judge đúng cho mọi domain |
| Hands/control | Action registry, capability level, approval, dry-run, execute, reconcile, rollback metadata và kiểm tra lại quyền trước dispatch | Có runtime proof giới hạn; external side-effect matrix chưa đầy đủ |
| Lost-response recovery | `RECONCILING`, `UNKNOWN`, `safeToRetry=false` và reconcile thay cho retry mù | Có test/runtime proof giới hạn; chưa chạy đủ mọi crash/timeout/lease/checkpoint combination |
| Security controls | Authentication, production guard, capability epoch/revoke, action allowlist, path boundary, SSRF/LFI checks, egress mode, injection detectors, DoS protection, kill switch, secret redaction/audit | Có code và test trong scope; không phải security certification |
| RAG/retrieval | Context-backed `/ask`, retriever/source metadata, context checks, grounded/provenance fields và fail-closed admission lane | Có bounded path; official Ragas/ARES gates vẫn `BLOCKED` |
| Model gateway | Local Ollama mode, task/model mapping, timeout/fallback paths và Windows Retry-After handling | Contract/bounded tests; live fallback qua mọi provider chưa được chứng minh |
| AutoFix | Deterministic scanner/recipe, restricted execution, policy gate, postcondition, rollback token và audit | Một số recipe đã kiểm chứng; không tự sửa an toàn mọi loại bug |
| Observability | Request/run ledger, trace/evidence ledgers, JSONL telemetry, health endpoints, metrics và dashboard views | Có artifact/audit trong scope; chưa có SLO/endurance trend đầy đủ |
| Runtime operations | Windows supervisor, Job Object, watchdog, restart budget, circuit events và hourly read-only monitor | Recovery bounded đã chạy; user-session scope, chưa phải pre-logon/system-service proof |

> **Có module trong source không đồng nghĩa module đó đã được chứng minh end-to-end trong production.**

## Bảo mật: có thật, nhưng không được phóng đại

SCP hiện có các lớp bảo vệ ứng dụng như deny-by-default, capability theo action, approval cho hành động có rủi ro, kiểm tra lại quyền ngay trước dispatch, giới hạn workspace/path, chặn một số URL private/loopback nguy hiểm, egress `deny`/allowlist trong profile phù hợp, kill switch, audit trước/sau side effect, secret redaction và `UNKNOWN` khi chưa biết trạng thái thật.

Các control này đã được kiểm tra bằng contract/security/reality tests trong phạm vi hiện tại. Tuy nhiên, chúng **không** chứng minh được tất cả các điều sau:

| Chưa được chứng minh | Vì sao chưa thể gọi là đã đạt |
|---|---|
| OS-level sandbox | Application policy và `shell=False` không thay thế isolation của operating system |
| Toàn bộ outbound network | Một URL helper an toàn không chứng minh mọi code path/provider đều bị chặn đúng |
| Prompt-injection coverage hoàn chỉnh | Detector hiện có vẫn là heuristic/pattern-based và cần corpus adversarial độc lập |
| Secret lifecycle hoàn chỉnh | Chưa có evidence đầy đủ cho rotation, expiry, Windows ACL và encryption at rest trên mọi log/dependency |
| Distributed rate limiting | Một phần state vẫn theo process, chưa phải limiter dùng chung cho nhiều worker/host |
| Mọi side effect nguy hiểm | Chưa có full approval/reconcile matrix cho publish, upload, payment, delete, credential và production change |
| Independent security assessment | Chưa có pentest, red-team hoặc chứng nhận độc lập được công bố |

## RAG và benchmark: trạng thái fail-closed

SCP không dùng token overlap nội bộ để tự gọi đó là điểm Ragas hoặc ARES. Bốn gate RAG chính vẫn chưa được promote:

| Gate | Trạng thái hiện tại | Lý do |
|---|---|---|
| Retrieval recall/precision theo gold chunk ID | `BLOCKED` | Chưa có bộ Gold được review độc lập với provenance đủ tin cậy |
| Context relevance/precision | `BLOCKED` | Chưa có official evaluation run được admission |
| Answer correctness/faithfulness | `BLOCKED` | Gold answer và human review chưa hoàn tất |
| Citation provenance | Structural only | Có trường provenance không đồng nghĩa nội dung đã đúng |

Đã có một pilot nhỏ chạy được đường official Ragas trong môi trường cô lập, nhưng pilot đó không phải score để phát hành: dữ liệu quá nhỏ, không có human-reviewed Gold và có metric non-finite phải chuẩn hóa thành `null`. Đối với bộ 1.000 câu, audit admission đã nhìn thấy các runtime rows nhưng **không có row nào được nhận vào official Ragas evaluation**. Vì vậy README này không quảng cáo “1.000 câu đạt RAG”, “50/50 Gold verified” hoặc “Ragas/ARES PASS”.

Các khái niệm đánh giá RAG được đối chiếu với các công trình mô tả context relevance, faithfulness và answer relevance như ARES; tuy nhiên, việc có thư viện hoặc runner không tự tạo ra dữ liệu sự thật, human annotation hay provenance độc lập. [1] [2]

## Runtime 24/7 và evidence hiện tại

Profile runtime trên PC sử dụng Windows Task Scheduler cho `SCP-247-Supervisor`, recovery watchdog và hourly read-only monitor. Các thành phần trong profile hiện có các port loopback sau:

| Thành phần | Port | Phạm vi |
|---|---:|---|
| Dashboard | `3000` | Local dashboard |
| Loop scheduler | `3030` | Local scheduler service |
| SCP API | `8002` | Canonical backend loopback |
| Ollama | `11434` | External local model dependency |

Bounded recovery evidence cho việc khởi động lại Ollama sau process kill đã được ghi trong các report/release artifacts tương ứng, gồm một cycle 17 giây và một run ba cycle 11/18/18 giây. Đây là evidence bounded của một snapshot cụ thể, không phải SLO dài hạn. README không đóng đinh commit hoặc số test tại đây; hãy xem [branch `main`](https://github.com/checken1994/GA-LAB/commits/main) và [GitHub Actions](https://github.com/checken1994/GA-LAB/actions) để lấy release evidence mới nhất.

Đây là **bounded recovery evidence**, không phải chứng minh uptime liên tục. Những điều vẫn chưa được chứng minh gồm logoff, pre-logon/system-service, cold boot, sleep/hibernate, mất điện, disk-full, memory leak, SQLite corruption/busy kéo dài, log rotation, load/endurance nhiều ngày và mọi external-provider outage. Trên PC hiện tại, supervisor/recovery boundary vẫn nằm trong **interactive user-session scope**.

Hourly monitor là chương trình read-only: nó kiểm tra health/readiness, port, policy preview và sentinel no-write; nó không tự publish, upload, delete, đổi credential hay thực thi write action. Lịch review sáu giờ của phiên có thể ở trạng thái `ask_user`; không nên hiểu rằng nền tảng chắc chắn tự gửi báo cáo khi không có tương tác.

## Trạng thái hiện tại

| Claim | Verdict hiện tại |
|---|---|
| Có một agent-runtime codebase với nhiều control production-like | `STATIC_PRESENT` / `PASS_WITHIN_SCOPE` |
| Contract/security/reality checks trong workload đã chạy | `PASS_WITHIN_SCOPE` |
| Bounded supervisor/Ollama recovery đã kiểm chứng | `PASS_WITHIN_SCOPE` |
| Uninterrupted 24/7, pre-logon và power-loss recovery | `BLOCKED / UNPROVEN` |
| Production-ready hoặc security tuyệt đối | `BLOCKED / UNPROVEN` |
| OS-level isolation và complete prompt-injection resistance | `BLOCKED / UNPROVEN` |
| Official Ragas/ARES admission cho RAG | `BLOCKED` |
| Full factual RAG 1.000 câu | `BLOCKED` |
| TOP 1 hoặc tốt hơn mọi AI/con người | `UNPROVEN` |

> **Verdict tổng: `CANDIDATE_NOT_PROVEN`.** `PASS` trong một test chỉ có nghĩa là không phát hiện lỗi trong phạm vi, profile và dữ liệu của test đó.

## Bố cục repository

Root chỉ giữ entry guide, policy GitHub, cấu hình test và launcher tương thích. Code đang chạy nằm trong `scp/`, `dashboard/` và `mini-services/`; supervisor/monitor/harness hiện hành nằm trong `scripts/ops/`; maintenance helper nằm trong `scripts/maintenance/`; tài liệu và lịch sử nằm trong `docs/`; test nằm trong `tests/`; report/evidence nằm trong `reports/`.

| Khu vực | Vai trò |
|---|---|
| [`docs/README.md`](docs/README.md) | Mục lục chung của tài liệu |
| [`docs/architecture/REPOSITORY_LAYOUT.md`](docs/architecture/REPOSITORY_LAYOUT.md) | Hợp đồng bố cục canonical và quy tắc move |
| `scripts/ops/` | Runtime supervisor, watchdog, monitor và harness active |
| `scripts/maintenance/` | Migration/maintenance; patch one-off đã chuyển vào `legacy/` |
| `reports/` | Evidence/report theo run và snapshot; không phải source |

Không dùng số lượng file, thư mục hoặc tên “final” để suy ra release readiness. Xem [`docs/README.md`](docs/README.md) trước khi thêm tài liệu mới.

## Cài đặt và chạy API tối thiểu

### Yêu cầu

Cấu hình runtime tối thiểu được kiểm thử trong repository là Python 3.10 trở lên. CI release gate hiện chạy Python 3.12 và Bun 1.3.14 cho phần dashboard. Ollama là dependency ngoài, chỉ cần khi bật profile local-model tương ứng.

### Linux/macOS hoặc Git Bash

```bash
git clone https://github.com/checken1994/GA-LAB.git
cd GA-LAB

python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r scp/requirements-dev.txt

# Chạy API loopback, mặc định tại 127.0.0.1:8002
python -m scp
```

### Windows PowerShell

```powershell
git clone https://github.com/checken1994/GA-LAB.git
Set-Location GA-LAB

py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r scp\requirements-dev.txt

# Chạy API loopback, mặc định tại 127.0.0.1:8002
python -m scp
```

Entrypoint thật là `python -m scp [PORT]`. Host mặc định là `127.0.0.1`; port mặc định là `8002`, có thể đổi bằng đối số hoặc `SCP_PORT`. Startup gọi production guard trước khi mở API. Không bind ra mạng công khai nếu chưa có cấu hình, isolation và review bảo mật phù hợp.

Kiểm tra health:

```bash
curl http://127.0.0.1:8002/health
```

Để chạy bộ dịch vụ local đầy đủ, xem hướng dẫn nền tảng trong [`docs/guides/WINDOWS-README.md`](docs/guides/WINDOWS-README.md), bản đồ repository trong [`docs/architecture/REPOSITORY_LAYOUT.md`](docs/architecture/REPOSITORY_LAYOUT.md) và các launcher trong repository. Các launcher local không phải bằng chứng rằng deployment đã đạt production hoặc 24/7 độc lập đăng nhập.

## Kiểm thử và release gate

Workflow chính là [SCP Release Gate](.github/workflows/scp-release-gate.yml). Nó chạy trên Windows và hiện kiểm tra các nhóm sau:

1. Cài dependency từ `scp/requirements-dev.txt`.
2. `py_compile` các entrypoint/security/runtime files được chỉ định.
3. Xác minh snapshot manifest.
4. Ruff focused check cho nhóm lỗi cú pháp/import/runtime-critical.
5. `pytest -q` với cấu hình test trong `scp/pyproject.toml`.
6. Bandit production scan, summary và policy threshold.
7. Portable reality runner.
8. Bounded full-system smoke trên loopback `8002` với egress-deny profile.
9. `npm ci`, `npm audit --omit=dev --audit-level=high` và `npm run build` cho dashboard.

Chạy local:

```bash
python -m pytest -q
python run_reality_tests_portable.py
python tools/run_bounded_system_smoke.py --output-dir reports/bounded_system_smoke_local
```

Kết quả phải được gắn với commit, môi trường, cấu hình, dataset và artifact tương ứng. Không dùng một con số test cũ trong README để đại diện cho mọi commit sau này. Không coi build xanh là bằng chứng end-to-end hoặc production readiness.

## Release evidence và provenance

Snapshot hiện tại của branch `main`:

| Trường | Giá trị |
|---|---|
| Repository | `checken1994/GA-LAB` |
| Branch cần kiểm tra | [`main`](https://github.com/checken1994/GA-LAB/tree/main) |
| Python package version | `0.14.0` trong `scp/pyproject.toml` |
| Release label | `Agent Runtime Candidate` |
| Tổng verdict | `CANDIDATE_NOT_PROVEN` |

Các báo cáo runtime/RAG chi tiết nằm trong repository hoặc vùng evidence tương ứng. Không commit token, cookie, `.env`, SQLite runtime database, raw private log, prompt chứa dữ liệu cá nhân hoặc file evidence chưa sanitize.

## So sánh với hệ thống khác

SCP có một số ý tưởng đáng kiểm chứng như default-deny, lost-response reconciliation, `UNKNOWN`, capability recheck, audit và rollback metadata. Tuy nhiên, repository hiện chưa có benchmark đối chứng công bằng để kết luận SCP ngang, hơn hoặc đứng TOP 1 so với OpenAI Agents, LangGraph, Microsoft Agent Governance Toolkit, AWS Dogwood hay các hệ thống agent khác.

So sánh nghiêm túc cần cố định cùng task, model, hardware, dataset, network profile và metric; đồng thời phải báo cáo correctness, safety, recovery, latency, cost, calibration và failure modes. Một architecture diagram hoặc số module không thay thế được benchmark đó.

Các nguồn công khai về agent runtime cho thấy những baseline mạnh thường bao gồm tracing, guardrails, sessions/state, approvals, durable execution, persistence, human-in-the-loop, fault tolerance và observability. [3] [4] SCP đang xây dựng và kiểm chứng một số primitive tương tự, nhưng breadth và evidence runtime chưa đủ để gọi là production-equivalent.

## Đóng góp và báo lỗi

Repository hiện được duy trì trong giai đoạn validation. Nếu phát hiện lỗi, hãy mở [GitHub Issue](https://github.com/checken1994/GA-LAB/issues) với commit, môi trường, lệnh tái hiện và log đã redact. Với vấn đề bảo mật, xem [`SECURITY.md`](SECURITY.md) và không đăng secret hoặc exploit có thể dùng ngay vào issue công khai.

Trước khi gửi pull request, hãy đọc [`CONTRIBUTING.md`](CONTRIBUTING.md), chạy test phù hợp và mô tả rõ phần nào là static evidence, integration evidence, runtime evidence hay recovery evidence.

## Giấy phép

MIT License — xem [`LICENSE`](LICENSE). Các dependency bên thứ ba có thể có giấy phép riêng; xem [`docs/legal/THIRD_PARTY_NOTICES.md`](docs/legal/THIRD_PARTY_NOTICES.md).

## Trích dẫn

```bibtex
@software{scp2026,
  title = {SCP: Structured Constraint Protocol},
  author = {Nguyen Van Minh},
  year = {2026},
  version = {0.14.0},
  note = {Agent Runtime Candidate; current evidence status CANDIDATE_NOT_PROVEN},
  url = {https://github.com/checken1994/GA-LAB}
}
```

## Tài liệu tham khảo

[1]: https://arxiv.org/abs/2311.09476 "ARES: An Automated Evaluation Framework for Retrieval-Augmented Generation Systems"

[2]: https://docs.ragas.io/en/stable/ "Ragas documentation"

[3]: https://developers.openai.com/api/docs/guides/agents "OpenAI Agents SDK guide"

[4]: https://docs.langchain.com/oss/python/langgraph/overview "LangGraph official overview"
