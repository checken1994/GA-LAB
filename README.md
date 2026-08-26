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

# Start SCP
python -m scp.api_server

# Run 74 Reality Tests (should all PASS)
python run_reality_tests_portable.py

# Run RAG Benchmark (50 gold rows)
python benchmark/run_ragas_v1.py
```

### Docker (Coming Soon)

```bash
docker compose up
# Access at http://localhost:8000/docs
```

---

## Testing & Verification

SCP is built on **evidence-first verification**. Every claim can be reproduced:

| Test Suite | Count | Status |
|-----------|-------|--------|
| Unit Tests | 101 | ✅ ALL PASS |
| Reality Tests | 74 | ✅ ALL PASS |
| Module Import Tests | 444 | ✅ ALL PASS |
| Syntax Validation | 860 files | ✅ 0 errors |
| API Routes | 136 | ✅ ALL LOADED |
| RAG Gold Benchmark | 50 rows | ✅ OPEN |

```bash
# Reproduce all test results yourself:
python -m pytest scp/tests/ -v
python run_reality_tests_portable.py
python benchmark/run_ragas_v1.py
```

---

## RAG Benchmark (Phase 3)

SCP's RAG system was evaluated on **50 verified gold anchor rows** extracted from Wikipedia (open, reproducible) and a curated Vietnamese knowledge base.

| Metric | Score | Method |
|--------|-------|--------|
| Context Precision | *see benchmark output* | Token-overlap (deterministic) |
| Faithfulness | *see benchmark output* | Token-overlap (deterministic) |
| Answer Relevancy | *see benchmark output* | Token-overlap (deterministic) |
| Fail-Closed Compliance | 100% | SCP ABSTAIN policy |

**Dataset SHA-256:** `4dacd4f05768bec7f3271de36c3c7f91022a097f38332720fb68af98984c3acd`

Reproduce:
```bash
python benchmark/run_ragas_v1.py
# Output: benchmark/ragas_results_v1.json
```

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
| Full RAG 1000 questions | ⚠️ PARTIAL (50 gold verified) |
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
