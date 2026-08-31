# SCP — Self-Correcting Pipeline / Agent Runtime

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Status: API-Only Agent Runtime](https://img.shields.io/badge/status-API--Only%20Agent%20Runtime-green.svg)](#trạng-thái)
[![Tests](https://img.shields.io/badge/pytest-215%20passed-brightgreen.svg)](#bằng-chứng)
[![Reality](https://img.shields.io/badge/reality-76%2F76%20PASS-brightgreen.svg)](#bằng-chứng)

> **SCP là một Agent Runtime tự tiến hóa: giới hạn quyền, ghi bằng chứng có hash-chain, tự xác minh kết quả bằng toán học, và học từ Internet — mọi thứ fail-closed.**

## SCP là gì (và không phải là gì)

SCP **không phải** một LLM. SCP là lớp runtime/control giữa AI agent và thế giới thực:

- **Không tin model** — mọi phán quyết qua 2 tầng: Tier-1 deterministic (~0.02ms) chém cấu trúc sai trước khi LLM kịp thấy; Tier-2 LLM chỉ phán giá ngữ nghĩa, và luôn tri-state (bất đồng → escalate cho người)
- **Không tin bằng chứng chưa xác minh** — Task Kernel ghi event journal hash-chain, máy tự replay + rebuild projection lúc boot
- **Không tin dữ liệu Internet** — mọi thứ cào về qua quarantine (10 họ injection pattern) + sha256 provenance, độc thì cách ly không bao giờ vào prompt
- **Không tự hoàn thành khi chưa verify** — `commit_completed` bắt buộc `verdict=VERIFIED` + `evidence_ref`, không có thì task nằm ở `HUMAN_REVIEW`

## Kiến trúc (56 mảnh ghép đã hiện thực)

```
Z: Boot Guard (production_guard + env_loader + hermetic boot)
  → A: FastAPI + AskKernelAdapter (idempotency, backpressure, fail-closed)
    → G: Task Kernel (per-thread SQLite WAL, hash-chain journal, lease fencing,
       capability epoch, kill switch, recover_on_boot chaos recovery)
      → B1: LLM Gateway (OpenRouter → extras → Groq, CircuitBreaker per provider,
         brand-neutral rotation, budget engine, resilient transport backoff+jitter)
      → B2: Sandbox (Windows Job Object + Linux bwrap, capability epoch)
    → C: Reality Judge (Tier-1 deterministic → Tier-2 tri-state cascade →
       second opinion qua model mạnh hơn → bất đồng → ESCALATE)
    → D: Recovery (recover_on_boot replays journal; corrupted = report, không tự sửa)
  → E: Learning Loop (Deep Scraper README thật + Quarantine + Wired Brain vào
     WHY Gate + Fix Prompt + Reflect; Fitness Engine gate PROMOTE/ROLLBACK)
```

Chi tiết đầy đủ: [`docs/SCP_CHAIN_AUDIT_20260829.md`](docs/SCP_CHAIN_AUDIT_20260829.md) · [`docs/SCP_HARDENING_20260829.md`](docs/SCP_HARDENING_20260829.md) · [`docs/SCP_FREE_API_WAREHOUSE_20260829.md`](docs/SCP_FREE_API_WAREHOUSE_20260829.md)

## Bằng chứng (2026-08-29, tự chạy — không phải claim)

| Gate | Kết quả |
|---|---|
| pytest | **190 passed, 1 skipped** (PYTEST_EXIT=0) |
| Reality suite | **76/76 PASS** (gồm chaos recovery, hermetic boot, warehouse, wiring) |
| Pre-push gate | **PASS** (import manifest + clean start + auth + RAG-verified ask) |
| Live E2E | `/ask` chat PASS · repeat re-ask PASS · RAG-verified PASS · prompt-injection KILL |
| Fitness baseline | accuracy 1.0 · false-accept 0.0 · 0.023ms/decision |
| Chain audit | 0 task loss dưới 100-thread load storm · hash-chain 100/100 valid |

## Quick Start

```bash
pip install -r requirements.txt

# .env bắt buộc:
#   SCP_JWT_SECRET=<random hex 64>       (python -c "import secrets; print(secrets.token_hex(32))")
#   SCP_ADMIN_KEY=<random urlsafe 24>    (python -c "import secrets; print(secrets.token_urlsafe(24))")
#   OPENROUTER_API_KEY=<your key>
#   OPENROUTER_MODEL=<model>             (vd: deepseek/deepseek-v4-flash-0731)
#   GROQ_API_KEY=<your key>              (optional — failover tier 2)

python -m scp                    # 127.0.0.1:8000
# hoặc custom port:
python -m scp 8080
```

## Các năng lực chính

| Tầng | Năng lực | Module |
|---|---|---|
| **Kernel** | Hash-chain journal, lease fencing, idempotency, kill switch, backpressure, boot recovery, chaos-proof | `scp/task_kernel.py` |
| **Gateway** | OpenRouter → extras → Groq failover, CircuitBreaker, backoff+jitter, budget routing | `scp/llm_gateway/client.py` |
| **Judge** | Tier-1 deterministic guard, Tier-2 tri-state cascade, think-block stripping, second-opinion escalation | `scp/runtime/judge.py` + `judge_llm.py` |
| **Sandbox** | Windows Job Object, Linux bwrap, capability epoch fencing, honest capability report | `scp/security/os_sandbox.py` |
| **Learning** | Free-API warehouse (1689 APIs), Deep README scraper, quarantine, Wired Brain (WHY+Fix+Reflect), TOP-1% topics | `scp/core/top_systems_learning.py` + `free_api_catalog.py` |
| **Fitness** | Golden Suite 100 decisions, deterministic solver recompute, PROMOTE/ROLLBACK gate | `scp/core/fitness_engine.py` |
| **Doubt** | Tự nghi ngờ mình định kỳ: fitness drift + integrity + backlog + WHY anomaly | `scp/core/doubt_cron.py` |
| **Security** | Tier-1 guard, quorum WHY cross-falsification, red-team agent, knowledge quarantine, capability epoch | `scp/security/` |

## Trạng thái trung thực

**Đã chứng minh:** từng mắt xích có bằng chứng runtime, chuỗi Z→A→G→B→C→D chạy end-to-end với 0 task loss dưới 100-thread load, hash-chain toàn vẹn sau chaos kill, hermetic boot trên môi trường trắng.

**Chưa chứng minh (khai báo thẳng):** uptime 24/7 đa ngày · multi-node HA (SQLite đơn node) · sandbox namespace thật trên Windows (Job Object ≠ container) · Tree-of-Thoughts backtracking · multi-agent swarm · semantic vector retrieval trong learning loop · LoRA self-distillation · content-level reputation (hiện chỉ metadata-based).

## Project Structure

```
scp/                  # Core package (kernel, gateway, judge, security, learning...)
  task_kernel.py      #   Durable kernel: hash-chain journal, lease, idempotency
  llm_gateway/        #   Multi-provider failover (OpenRouter → Groq)
  runtime/            #   RealityJudge (2-tier verification)
  security/           #   Tier-1 guard, quorum, red-team, sandbox, quarantine
  core/               #   Fitness engine, curation, doubt cron, pruner, resolver
  data_sources/       #   Free-API catalog (1689 APIs from public-apis)
  api/                #   FastAPI routes (v98-v105, hands, web-control)
  meta/               #   WHY gate, constitution, falsification engine
docs/                 #   Architecture + audit + hardening reports
tests/                #   pytest (215) + reality tests (76) + golden suite
scripts/              #   Setup, generation, audit tools
agents/skills/        #   13 SCP skills (DNA + domain-specific)
benchmark/            #   Benchmark runner + grader (exact-match, no LLM grading)
```

## License

MIT — see [LICENSE](LICENSE).
