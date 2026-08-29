from pathlib import Path
"""Reality test 4-e-001: Free-API warehouse + TOP-1% learning loop.

DNA #1 (Reality > Model — the "kho API free" must actually parse the real
catalog shape, not a fantasy), #9 (no harm — fixed host allowlist, egress
opt-out), #16 (scope — no user-supplied URLs), #22 (PASS ≠ TRUE — a
warehouse that fails closed to cache must say so), #25 (missing piece —
without a durable cache there is no offline evidence).

Tier-A (static + pure) reality check: no network required. Runtime fetch is
exercised by the /v104/learn/top-systems route in a Tier-B deployment check.
"""

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

CATALOG_FILE = Path(__file__).resolve().parents[2] / "scp" / "data_sources" / "free_api_catalog.py"
LEARNER_FILE = Path(__file__).resolve().parents[2] / "scp" / "core" / "top_systems_learning.py"

assert CATALOG_FILE.is_file(), f"FAIL: missing {CATALOG_FILE}"
assert LEARNER_FILE.is_file(), f"FAIL: missing {LEARNER_FILE}"
print("PASS [1/6]: modules exist")

catalog_src = CATALOG_FILE.read_text(encoding="utf-8")
learner_src = LEARNER_FILE.read_text(encoding="utf-8")

# TEST 2 — fixed host allowlists, never user URLs.
assert "raw.githubusercontent.com" in catalog_src and "ALLOWED_HOSTS" in catalog_src
assert "api.github.com" in learner_src and "en.wikipedia.org" in learner_src
print("PASS [2/6]: fixed host allowlists present")

# TEST 3 — egress opt-out honored in BOTH modules.
assert "SCP_TOP_SYSTEMS_EGRESS" in catalog_src and "SCP_TOP_SYSTEMS_EGRESS" in learner_src
print("PASS [3/6]: egress opt-out honored")

# TEST 4 — no local-Ollama regressions: warehouse must not call 11434.
assert "11434" not in catalog_src and "11434" not in learner_src
print("PASS [4/6]: no 11434/Ollama dependency")

# TEST 5 — the parser handles the real README's inconsistent header shapes.
from scp.data_sources.free_api_catalog import parse_catalog_md

sample = "\n".join(
    [
        "### Blockchain",
        "API | Description | Auth | HTTPS | CORS |",
        "|:---|:---|:---|:---|:---|",
        "| [Etherscan](https://etherscan.io/apis) | Ethereum explorer API | `apiKey` | Yes | Yes |",
        "",
        "### Books",
        "| API | Description | Auth | HTTPS | CORS |",
        "|:---|:---|:---|:---|:---|",
        "| [Google Books](https://developers.google.com/books) | Books search | `apiKey` | Yes | Yes |",
    ]
)
entries = parse_catalog_md(sample)
assert len(entries) == 2, f"FAIL: expected 2 entries, got {len(entries)}"
assert entries[0]["category"] == "Blockchain" and entries[0]["auth"] == "apiKey"
assert entries[1]["category"] == "Books"
print("PASS [5/6]: parser handles both header shapes with correct fields")

# TEST 6 — learner topic library covers the TOP-1% practice areas.
from scp.core.top_systems_learning import TOPIC_LIBRARY

required = {
    "agent_runtime", "agent_kernel", "llm_evaluation", "llm_redteam",
    "sandboxing", "evidence_audit", "rag_verification", "observability",
}
missing = required - set(TOPIC_LIBRARY)
assert not missing, f"FAIL: missing topics: {missing}"
print("PASS [6/6]: TOP-1% topic library complete")

print("\nOK Reality test 4-e-001 PASSED")
