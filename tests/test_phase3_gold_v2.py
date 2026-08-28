from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "benchmark" / "gold_anchor_50_v2_candidates.jsonl"


def rows() -> list[dict]:
    return [json.loads(line) for line in DATA.read_text(encoding="utf-8").splitlines() if line.strip()]


def test_gold_v2_has_exactly_50_unique_ids() -> None:
    records = rows()
    assert len(records) == 50
    assert len({record["question_id"] for record in records}) == 50


def test_every_row_is_candidate_and_fail_closed() -> None:
    for record in rows():
        assert record["candidate_only"] is True
        assert record["human_review_required"] is True
        assert record["gold_promotion"] == "BLOCKED_PENDING_HUMAN_REVIEW"
        assert record["eligible_for_ragas"] is False
        assert record["reviewer_id"] != "HUMAN"


def test_machine_quotes_are_source_contained_and_never_answer_prefix() -> None:
    for record in rows():
        if record["review_status"] == "CANDIDATE_SOURCE_FETCH_VERIFIED":
            assert record["gold_evidence_quote"]
            assert record["quote_contained_in_fetched_source"] is True
            assert record["gold_evidence_quote"] in record["gold_chunk_text"]
            assert record["gold_evidence_quote"] not in record["candidate_answer"][:1]


def test_known_corrupt_mappings_are_not_promoted() -> None:
    by_id = {record["question_id"]: record for record in rows()}
    for qid in ("CH-0036", "CH-0042", "CH-0049", "CH-0050"):
        record = by_id[qid]
        assert record["review_status"] == "SOURCE_MISMATCH_NEEDS_REBUILD"
        assert record["gold_evidence_quote"] == ""
        assert record["eligible_for_ragas"] is False
        assert record["alignment_status"] == "MISMATCH_OBSERVED"


def test_schema_has_provenance_fields() -> None:
    required = {
        "source_fetch_timestamp", "source_http_status", "source_content_sha256", "source_cache_path",
        "source_canonical_url_observed", "gold_chunk_id", "gold_chunk_sha256", "gold_evidence_quote",
        "review_status", "reviewer_provenance", "temporal_scope", "alignment_status",
    }
    for record in rows():
        assert required <= record.keys()
