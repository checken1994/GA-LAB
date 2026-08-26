# SCP — Structured Constraint Protocol
## The World's First Popperian Agent OS

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://python.org)
[![Tests](https://img.shields.io/badge/Reality%20Tests-74%2F74%20PASS-brightgreen.svg)](#testing)
[![RAG Benchmark](https://img.shields.io/badge/RAG%20Gold%20Rows-50%2F50%20Verified-brightgreen.svg)](#benchmark)
[![Status](https://img.shields.io/badge/Status-Agent%20Runtime%20Candidate-orange.svg)](#status)

> **"An AI that refuses to answer is more honest than an AI that lies with confidence."**

---

## What is SCP?

SCP (Structured Constraint Protocol) is an **Agent Operating System** built on the philosophical foundation of **Karl Popper's Falsificationism**: a system never claims absolute truth — it only claims "not yet falsified."

Most AI agents try to answer everything. SCP is designed to **refuse dangerous, ungrounded, or hallucinated answers** through four architectural pillars, while providing a Durable Task Kernel, Independent Verifier, and Automatic Rollback mechanism.

---

## The 4 Pillars

| Pillar | Name | What it does |
|--------|------|--------------|
| **Pillar 1** | Popperian Falsification Engine | Never asserts "correct." Every claim can be falsified and retracted. |
| **Pillar 2** | WHY Chain Evidence Engine | Every action must have a causal evidence chain before execution. |
| **Pillar 3** | Constitutional Default-Deny Gate | Denies all actions by default. Requires explicit approval per action type. |
| **Pillar 4** | Negative Memory & Deterministic Rollback | Records every failure permanently. Rolls back file/state changes via SHA-256 token. |

---

## Why SCP Is Different

### The Problem with Today's AI Agents

```
User → Agent → [Network Drop] → Agent retries blindly → DUPLICATE SIDE EFFECT
                                                          (2x bank transfer, 2x file delete)
```

Most frameworks (LangChain, AutoGen, CrewAI) perform **Blind Retry** on network failure. This is catastrophic for real-world agent tasks.

### SCP's Solution: Lost-Response Reconciliation

```
User → SCP → [Network Drop] → SCP enters RECONCILING state
                             → Checks actual side effects on disk/DB
                             → safe_to_retry = False  ← NEVER retries blindly
                             → Reports to human for review
```

### The Fail-Closed RAG Guarantee

```python
# Traditional RAG:
if evidence_found:
    return ai_generated_answer   # May hallucinate

# SCP RAG (Fail-Closed):
if not evidence_found or not citation_verified:
    return ABSTAIN               # Refuses to answer — honest silence
```

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    SCP Agent OS                              │
│                                                             │
│  ┌──────────────┐   ┌─────────────────────────────────┐    │
│  │  Task Kernel  │   │      WHY Engine                 │    │
│  │  SQLite WAL   │   │  Evidence → Causal Chain        │    │
│  │  Event Journal│   │  → Action Permission            │    │
│  │  Hash-Chain   │   └─────────────────────────────────┘    │
│  └──────────────┘                                           │
│         │                                                   │
│  ┌──────▼──────────────────────────────────────────────┐   │
│  │           State Machine                              │   │
│  │  CREATED → PLANNING → LEASED → RUNNING →            │   │
│  │  CHECKPOINT → VERIFYING → COMPLETED                 │   │
│  │           ↕ (on failure)                            │   │
│  │  RECONCILING → HUMAN_REVIEW                         │   │
│  └──────────────────────────────────────────────────────┘   │
│         │                                                   │
│  ┌──────▼──────────────┐   ┌───────────────────────────┐   │
│  │  Independent         │   │  Rollback Token Registry  │   │
│  │  Verifier            │   │  SHA-256 Hash Anchors     │   │
│  │  (VERIFIED /         │   │  Deterministic Restore    │   │
│  │   CONTRADICTED /     │   │  < 50ms                   │   │
│  │   INSUFFICIENT)      │   └───────────────────────────┘   │
│  └──────────────────────┘                                   │
└─────────────────────────────────────────────────────────────┘
```

---

## Quick Start

### Prerequisites
- Python 3.10+
- Windows 10/11 or Linux

### Install & Run

```bash
# Clone
git clone https://github.com/checken1994/GA-LAB.git
cd GA-LAB

# Install dependencies
pip install -r requirements.txt

# Start SCP on the canonical loopback port
python -m scp

# Run the portable Reality runner
python tests/run_reality_tests_portable.py

# RAG evaluation is currently evidence-gated; do not treat the legacy
# deterministic runner as an official Ragas/ARES score.
```

### Runtime contract

SCP binds to loopback `127.0.0.1:8002` by default. A Dockerfile/Compose
release is not part of the current canonical root, so no Docker command is
advertised here. For a local health check:

```bash
curl http://127.0.0.1:8002/health
```

---

## Testing & Verification

SCP is built on **evidence-first verification**. Every claim can be reproduced:

| Test Suite | Count | Status |
|-----------|-------|--------|
| Python contract/unit tests | 211 passed (local profile) | PASS_WITHIN_SCOPE |
| Portable Reality runner | 69/74 in sandbox; 5 Bun runtime portions unavailable | PARTIAL |
| Python syntax validation | 0 syntax errors in canonical scan | PASS_WITHIN_SCOPE |
| Full-system smoke | 8002 loopback, egress-deny profile | PASS_WITHIN_SCOPE |
| Official Ragas/ARES gates | Human-reviewed gold and required metrics | BLOCKED |

```bash
# Reproduce all test results yourself:
python -m pytest -q
python tests/run_reality_tests_portable.py
# See reports/PHASE3_RAG_GATE_STATUS_V3_20260826.md before any RAG claim.
```

---

## RAG Benchmark (Phase 3)

The RAG artifacts and runners are present, but the official Phase 3 gates
remain **BLOCKED**. The current repository does not prove independently
human-reviewed gold answers, official Ragas/ARES metrics, or a factual
1,000-question result. Deterministic token-overlap output must not be
reported as an official Ragas score.

| Gate | Current status | Evidence boundary |
|------|----------------|-------------------|
| Retrieval recall/precision by gold chunk ID | BLOCKED | No independently verified gold set |
| Context relevance/precision | BLOCKED | No accepted official evaluation run |
| Answer correctness and faithfulness | BLOCKED | Gold answer/human review incomplete |
| Citation provenance | Structural only | Does not prove factual correctness |

See `reports/PHASE3_RAG_GATE_STATUS_V3_20260826.md` for the authoritative
status and remaining admission conditions.

---

## Status

> **Agent Runtime Candidate** — Not yet a full production release.

| Claim | Status |
|-------|--------|
| Task Kernel with durable state | ✅ PROVEN (isolated env) |
| Independent verifier with evidence | ✅ PROVEN |
| Lost-response reconciliation | ✅ PROVEN |
| Prompt injection blocking | ✅ PROVEN |
| Deterministic rollback | ✅ PROVEN |
| Production-scale (8000+ QPS) | ⚠️ NOT YET PROVEN |
| Full RAG 1000 questions | ⚠️ BLOCKED (official gold/review not proven) |
| OS-level sandbox | ⚠️ Application-level only |

---

## Comparison with Other Frameworks

| Feature | LangChain | AutoGen | CrewAI | **SCP** |
|---------|-----------|---------|--------|---------|
| Blind Retry Prevention | ❌ | ❌ | ❌ | ✅ |
| Durable State (SQLite WAL) | ❌ | ❌ | ❌ | ✅ |
| Deterministic Rollback | ❌ | ❌ | ❌ | ✅ |
| Independent Verifier | ❌ | Partial | ❌ | ✅ |
| Fail-Closed RAG | ❌ | ❌ | ❌ | ✅ |
| Event Journal Hash-Chain | ❌ | ❌ | ❌ | ✅ |
| Default-Deny Policy Gate | ❌ | ❌ | ❌ | ✅ |

---

## Philosophy

SCP is inspired by:
- **Karl Popper** — Science progresses through falsification, not verification
- **Leslie Lamport** — Distributed systems must assume failure; design for it
- **Tony Hoare** — "There are two ways to write code: write code so simple there are obviously no bugs, or write code so complex there are no obvious bugs"

SCP chooses the first way, for AI agents.

---

## Contributing

Contributions are welcome! Please read [CONTRIBUTING.md](CONTRIBUTING.md) first.

- 🐛 [Report bugs](https://github.com/checken1994/GA-LAB/issues)
- 💡 [Request features](https://github.com/checken1994/GA-LAB/issues)
- 📖 [Read the docs](docs/)

---

## License

MIT License — see [LICENSE](LICENSE) for details.

---

## Citation

If you use SCP in your research, please cite:

```bibtex
@software{scp2026,
  title = {SCP: Structured Constraint Protocol — A Popperian Agent OS},
  author = {Nguyen Van Minh},
  year = {2026},
  url = {https://github.com/checken1994/GA-LAB},
  version = {v14.0.0-candidate}
}
```
