"""
TOP-1% Systems Learning Loop — SCP học từ kho tri thức free của thế giới.

TẠI SAO module này tồn tại:
  Người vận hành SCP không có ngân sách để chạy so sánh trực tiếp với các hệ
  thống TOP 1%. Thay thế trung thực nhất: dùng các nguồn tri thức free (GitHub
  search API, Wikipedia API) để thu thập liên tục các hệ thống/thực hành tốt
  nhất theo chủ đề (agent kernel, evaluation harness, sandboxing, red-teaming,
  evidence journal...), lưu vào ledger durable có provenance, để các tầng
  WHY/autofix/learning của SCP tra cứu (`advise`) khi cần cải tiến code và logic.

Fail-closed:
  - Chỉ fetch 2 host cố định trong ALLOWED_HOSTS (SSRF-safe by construction).
  - Lỗi mạng của MỘT chủ đề không làm chết vòng học (per-topic isolation).
  - Mất mạng → trả {"ok": False} và phục vụ từ ledger cũ; không bịa records.
  - Egress opt-out: SCP_TOP_SYSTEMS_EGRESS=0 → chỉ đọc ledger.

Rate-limit trung thực: GitHub unauthenticated = 60 req/hour. Mỗi topic tốn
2 request (GitHub + Wikipedia) → learn_all() mặc định 8 topic = 16 request.
"""
from __future__ import annotations

import json
import logging
import os
import re
import threading
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Callable

logger = logging.getLogger("scp.core.top_systems_learning")

ALLOWED_HOSTS = frozenset({"api.github.com", "en.wikipedia.org"})
_USER_AGENT = "SCP-TopSystemsLearner/1.0 (+https://github.com/checken1994/GA-LAB)"

# The TOP-1% practice areas SCP is built around. Each entry maps to one GitHub
# search query + one Wikipedia query. Kept explicit and reviewable on purpose.
TOPIC_LIBRARY: dict[str, dict[str, str]] = {
    "agent_runtime": {"github_query": "AI agent runtime framework", "wiki_query": "Intelligent agent"},
    "agent_kernel": {"github_query": "agent orchestration state machine", "wiki_query": "Finite-state machine"},
    "llm_evaluation": {"github_query": "LLM evaluation benchmark harness", "wiki_query": "Automatic evaluation of language models"},
    "llm_redteam": {"github_query": "LLM red teaming prompt injection", "wiki_query": "Adversarial machine learning"},
    "sandboxing": {"github_query": "code execution sandbox isolation", "wiki_query": "Sandbox (computer security)"},
    "evidence_audit": {"github_query": "audit log hash chain tamper evidence", "wiki_query": "Hash chain"},
    "rag_verification": {"github_query": "retrieval augmented generation verification", "wiki_query": "Retrieval-augmented generation"},
    "observability": {"github_query": "LLM observability tracing", "wiki_query": "Observability"},
}

_TAG_RE = re.compile(r"<[^>]+>")


def egress_disabled() -> bool:
    return os.environ.get("SCP_TOP_SYSTEMS_EGRESS", "1").strip().lower() in {"0", "false", "off"}


class TopSystemsLearner:
    """Collects knowledge about top-tier systems from free internet sources."""

    def __init__(self, data_dir: str = "data", fetcher: Callable[[str, dict[str, str]], dict[str, Any]] | None = None):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.ledger_path = self.data_dir / "top_systems_knowledge.jsonl"
        # Injectable fetcher(url, headers) -> decoded JSON for hermetic tests.
        self._fetcher = fetcher

    # ------------------------------------------------------------------
    # Network (fixed allowlisted hosts only)
    # ------------------------------------------------------------------
    @staticmethod
    def _http_get_json(url: str, headers: dict[str, str] | None = None) -> dict[str, Any]:
        parsed = urllib.parse.urlparse(url)
        if parsed.scheme != "https" or parsed.hostname not in ALLOWED_HOSTS:
            raise ValueError(f"host not in learning allowlist: {parsed.hostname!r}")
        if egress_disabled():
            raise RuntimeError("egress disabled by SCP_TOP_SYSTEMS_EGRESS=0")
        merged = {"User-Agent": _USER_AGENT, **(headers or {})}
        req = urllib.request.Request(url, headers=merged)  # noqa: S310 — scheme+host allowlisted above
        with urllib.request.urlopen(req, timeout=20) as resp:  # nosec B310 — fixed https host from ALLOWED_HOSTS
            return json.loads(resp.read(2_000_000).decode("utf-8", errors="replace"))

    def _get_json(self, url: str, headers: dict[str, str] | None = None) -> dict[str, Any]:
        if self._fetcher is not None:
            return self._fetcher(url, headers or {})
        return self._http_get_json(url, headers)

    # ------------------------------------------------------------------
    # Sources
    # ------------------------------------------------------------------
    def _fetch_github(self, query: str, per_source: int) -> list[dict[str, Any]]:
        url = (
            "https://api.github.com/search/repositories?q="
            + urllib.parse.quote(query)
            + f"&sort=stars&order=desc&per_page={int(per_source)}"
        )
        data = self._get_json(url, headers={"Accept": "application/vnd.github+json"})
        out: list[dict[str, Any]] = []
        for item in data.get("items", [])[: per_source]:
            out.append(
                {
                    "source": "github",
                    "kind": "repository",
                    "name": str(item.get("full_name", ""))[:200],
                    "url": str(item.get("html_url", ""))[:300],
                    "stars": int(item.get("stargazers_count", 0)),
                    "description": str(item.get("description") or "")[:400],
                }
            )
        return out

    def _fetch_wikipedia(self, query: str, per_source: int) -> list[dict[str, Any]]:
        url = (
            "https://en.wikipedia.org/w/api.php?action=query&list=search&format=json&srlimit="
            + str(int(per_source))
            + "&srsearch="
            + urllib.parse.quote(query)
        )
        data = self._get_json(url)
        out: list[dict[str, Any]] = []
        for item in data.get("query", {}).get("search", [])[:per_source]:
            title = str(item.get("title", ""))
            snippet = _TAG_RE.sub("", str(item.get("snippet", "")))
            out.append(
                {
                    "source": "wikipedia",
                    "kind": "article",
                    "name": title[:200],
                    "url": "https://en.wikipedia.org/wiki/" + urllib.parse.quote(title.replace(" ", "_")),
                    "description": snippet[:400],
                }
            )
        return out

    # ------------------------------------------------------------------
    # Learning cycles
    # ------------------------------------------------------------------
    def _append_ledger(self, records: list[dict[str, Any]]) -> int:
        if not records:
            return 0
        with self.ledger_path.open("a", encoding="utf-8") as handle:
            for record in records:
                handle.write(json.dumps(record, ensure_ascii=False) + "\n")
        return len(records)

    def learn_topic(self, topic_key: str, per_source: int = 5) -> dict[str, Any]:
        spec = TOPIC_LIBRARY.get(topic_key)
        if not spec:
            return {"ok": False, "topic": topic_key, "reason": "unknown_topic", "known": sorted(TOPIC_LIBRARY)}
        errors: list[str] = []
        records: list[dict[str, Any]] = []
        for fetch in (self._fetch_github, self._fetch_wikipedia):
            try:
                records.extend(fetch(spec["github_query"] if fetch is self._fetch_github else spec["wiki_query"], per_source))
            except Exception as exc:
                errors.append(f"{fetch.__name__}: {type(exc).__name__}: {str(exc)[:120]}")
        for record in records:
            record["topic"] = topic_key
            record["collected_at"] = time.time()
        written = self._append_ledger(records)
        return {
            "ok": len(errors) == 0,
            "topic": topic_key,
            "records": written,
            "errors": errors,
        }

    def learn_all(self, topics: list[str] | None = None, per_source: int = 5) -> dict[str, Any]:
        keys = [k for k in (topics or TOPIC_LIBRARY.keys()) if k in TOPIC_LIBRARY]
        unknown = [k for k in (topics or []) if k not in TOPIC_LIBRARY]
        results = [self.learn_topic(k, per_source=per_source) for k in keys]
        return {
            "ok": all(r.get("ok") for r in results) if results else False,
            "topics_run": keys,
            "unknown_topics": unknown,
            "records": sum(r.get("records", 0) for r in results),
            "results": results,
            "ledger": str(self.ledger_path),
        }

    # ------------------------------------------------------------------
    # Consumption — what WHY/autofix/learning will consult
    # ------------------------------------------------------------------
    def advise(self, query: str, limit: int = 10) -> list[dict[str, Any]]:
        tokens = [t for t in query.lower().split() if t]
        scored: list[tuple[int, dict[str, Any]]] = []
        if self.ledger_path.exists():
            lines = self.ledger_path.read_text(encoding="utf-8").splitlines()
            for line in reversed(lines[-2000:]):
                try:
                    record = json.loads(line)
                except (TypeError, ValueError):
                    continue
                haystack = " ".join(
                    [record.get("topic", ""), record.get("name", ""), record.get("description", "")]
                ).lower()
                score = sum(1 for t in tokens if t in haystack)
                if score:
                    scored.append((score, record))
        scored.sort(key=lambda pair: -pair[0])
        return [record for _, record in scored[: max(1, int(limit))]]

    def stats(self) -> dict[str, Any]:
        count = 0
        topics: set[str] = set()
        if self.ledger_path.exists():
            for line in self.ledger_path.read_text(encoding="utf-8").splitlines():
                try:
                    record = json.loads(line)
                except (TypeError, ValueError):
                    continue
                count += 1
                if record.get("topic"):
                    topics.add(str(record["topic"]))
        return {
            "records": count,
            "topics_covered": sorted(topics),
            "topic_library": sorted(TOPIC_LIBRARY),
            "ledger": str(self.ledger_path),
            "egress": "disabled" if egress_disabled() else "enabled",
        }


_LEARNER: TopSystemsLearner | None = None
_LEARNER_LOCK = threading.Lock()


def get_learner(data_dir: str = "data") -> TopSystemsLearner:
    global _LEARNER
    if _LEARNER is None:
        with _LEARNER_LOCK:
            if _LEARNER is None:
                _LEARNER = TopSystemsLearner(data_dir=data_dir)
    return _LEARNER
