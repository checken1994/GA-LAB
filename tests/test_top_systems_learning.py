"""Hermetic tests for the TOP-1% systems learning loop."""
from __future__ import annotations

import json

import pytest

from scp.core.top_systems_learning import ALLOWED_HOSTS, TOPIC_LIBRARY, TopSystemsLearner


def _fake_fetcher_factory():
    def fetcher(url: str, headers: dict[str, str]) -> dict:
        if "api.github.com" in url:
            return {
                "items": [
                    {
                        "full_name": "example/top-agent-runtime",
                        "html_url": "https://github.com/example/top-agent-runtime",
                        "stargazers_count": 4242,
                        "description": "A top-1% agent runtime",
                    }
                ]
            }
        if "en.wikipedia.org" in url:
            return {
                "query": {
                    "search": [
                        {
                            "title": "Intelligent agent",
                            "snippet": "An <b>agent</b> acts on an environment.",
                        }
                    ]
                }
            }
        raise AssertionError(f"unexpected host: {url}")

    def raw_fetcher(url: str, headers: dict[str, str]) -> str:
        if "/readme" in url and "example/top-agent-runtime" in url:
            return (
                "# top-agent-runtime\n\n## Architecture\n\nSingle static binary. "
                "Cold start 13ms via lazy import table and zero-allocation "
                "state machine. Ledger is an append-only hash chain."
            )
        raise AssertionError(f"unexpected raw host: {url}")

    return fetcher, raw_fetcher


def _make_learner(tmp_path):
    fetcher, raw_fetcher = _fake_fetcher_factory()
    return TopSystemsLearner(data_dir=str(tmp_path), fetcher=fetcher, raw_fetcher=raw_fetcher)


def test_learn_topic_writes_ledger_with_provenance(tmp_path):
    learner = _make_learner(tmp_path)
    result = learner.learn_topic("agent_runtime")
    # 1 repo + 1 wiki + 1 DEEP README = 3 records
    assert result["ok"] is True and result["records"] == 3
    assert result["deep_readmes"] == 1
    lines = (tmp_path / "top_systems_knowledge.jsonl").read_text(encoding="utf-8").splitlines()
    records = [json.loads(line) for line in lines]
    assert {r["source"] for r in records} == {"github", "wikipedia", "github_readme"}
    assert all(r["topic"] == "agent_runtime" and r["collected_at"] for r in records)
    gh = next(r for r in records if r["source"] == "github")
    assert gh["stars"] == 4242 and gh["name"] == "example/top-agent-runtime"


def test_deep_readme_content_is_queryable_via_advise(tmp_path):
    learner = _make_learner(tmp_path)
    learner.learn_topic("agent_runtime")
    hits = learner.advise("13ms cold start", limit=3)
    assert hits and hits[0]["source"] == "github_readme"
    assert "13ms" in hits[0]["description"]


def test_source_failure_is_isolated_per_topic(tmp_path):
    def half_broken(url: str, headers: dict[str, str]) -> dict:
        if "api.github.com" in url:
            raise ConnectionError("github down")
        return {
            "query": {"search": [{"title": "Hash chain", "snippet": "chain of hashes"}]}
        }

    learner = TopSystemsLearner(
        data_dir=str(tmp_path), fetcher=half_broken, raw_fetcher=lambda url, headers: "x"
    )
    result = learner.learn_topic("evidence_audit")
    assert result["ok"] is False
    assert result["records"] == 1  # wikipedia still collected
    assert "github" in result["errors"][0]


def test_unknown_topic_fail_closed(tmp_path):
    learner = _make_learner(tmp_path)
    result = learner.learn_topic("does_not_exist")
    assert result["ok"] is False and result["reason"] == "unknown_topic"


def test_advise_returns_relevant_records(tmp_path):
    learner = _make_learner(tmp_path)
    learner.learn_all(topics=["agent_runtime", "evidence_audit"])
    hits = learner.advise("agent runtime", limit=5)
    assert hits and all("agent" in (r["topic"] + r["name"]).lower() for r in hits)
    assert learner.advise("zzz-no-match") == []


def test_host_allowlist_blocks_everything_else():
    assert ALLOWED_HOSTS == frozenset({"api.github.com", "en.wikipedia.org"})
    with pytest.raises(ValueError):
        TopSystemsLearner._http_get_json("https://evil.example.com/search?q=x")
    with pytest.raises(ValueError):
        TopSystemsLearner._http_get_json("http://api.github.com/search?q=x")


def test_topic_library_covers_top_1_practice_areas():
    expected = {
        "agent_runtime", "agent_kernel", "llm_evaluation", "llm_redteam",
        "sandboxing", "evidence_audit", "rag_verification", "observability",
    }
    assert expected.issubset(set(TOPIC_LIBRARY))
