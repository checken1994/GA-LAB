from __future__ import annotations

from pathlib import Path

from benchmark.review_workflow import (
    build_queue,
    decision_hash,
    decision_signature,
    finalize_decisions_csv,
    validate_decisions,
    write_csv,
    write_html,
)


def candidate() -> dict[str, str]:
    return {
        "question_id": "CH-TEST-1",
        "question": "Một câu hỏi cần kiểm chứng?",
        "candidate_answer": "Câu trả lời có thể đúng.",
        "proposed_canonical_source_url": "https://example.test/source",
        "proposed_source_title": "Nguồn kiểm chứng",
        "gold_evidence_quote": "Đoạn nguồn có thể kiểm tra.",
        "temporal_scope": "CURRENT_OR_HIGH_STAKES",
    }


def signed_decision() -> dict[str, str]:
    row = {
        "question_id": "CH-TEST-1",
        "decision": "VERIFIED",
        "evidence_quote": "Đoạn nguồn có thể kiểm tra.",
        "source_url": "https://example.test/source",
        "reviewer_id": "reviewer@example.org",
        "reviewed_at_utc": "2026-08-26T05:00:00+00:00",
        "reviewer_note": "Đã mở nguồn và đối chiếu trực tiếp.",
    }
    row["decision_hash"] = decision_hash(row)
    row["review_signature"] = decision_signature(row, "test-review-key")
    return row


def test_queue_forces_human_review_and_writes_csv_html(tmp_path: Path) -> None:
    queue = build_queue([candidate()])
    assert queue[0]["human_review_required"] == "true"
    assert queue[0]["decision"] == ""
    assert queue[0]["current_or_high_stakes"] == "true"
    csv_path = tmp_path / "queue.csv"
    html_path = tmp_path / "queue.html"
    write_csv(csv_path, queue)
    write_html(html_path, queue)
    assert "CH-TEST-1" in csv_path.read_text(encoding="utf-8-sig")
    html_text = html_path.read_text(encoding="utf-8")
    assert "Không chọn VERIFIED" in html_text
    assert "example.test/source" in html_text
    for field in ("question_id", "question", "candidate_answer", "source_url", "source_title", "source_excerpt", "source_excerpt_sha256", "current_or_high_stakes", "human_review_required"):
        assert f'name="{field}"' in html_text


def test_finalize_adds_integrity_fields_only_to_reviewed_rows(tmp_path: Path) -> None:
    input_path = tmp_path / "decisions.csv"
    output_path = tmp_path / "finalized.csv"
    rows = [signed_decision(), {"question_id": "CH-TEST-1", "decision": ""}]
    write_csv(input_path, rows)
    assert finalize_decisions_csv(input_path, output_path, "test-review-key") == 1
    import csv
    with output_path.open(encoding="utf-8-sig", newline="") as handle:
        finalized = list(csv.DictReader(handle))
    assert finalized[0]["decision_hash"].startswith("sha256:")
    assert finalized[0]["review_signature"].startswith("hmac-sha256:")
    assert finalized[1]["decision_hash"] == ""
    assert finalized[1]["review_signature"] == ""


def test_verified_decision_requires_valid_hash_and_signature() -> None:
    decision = signed_decision()
    report = validate_decisions([candidate()], [decision], signing_key="test-review-key")
    assert report["status"] == "PASS_WITHIN_SCOPE"
    assert report["eligible_for_gold"] == 1
    assert report["results"][0]["signature_status"] == "VALID"

    no_key = validate_decisions([candidate()], [decision], signing_key=None)
    assert no_key["status"] == "BLOCKED"
    assert "signing_key_required_for_verified" in no_key["results"][0]["errors"]


def test_source_mismatch_or_tampered_hash_is_blocked() -> None:
    decision = signed_decision()
    decision["source_url"] = "https://example.test/wrong"
    report = validate_decisions([candidate()], [decision], signing_key="test-review-key")
    errors = report["results"][0]["errors"]
    assert report["status"] == "BLOCKED"
    assert "source_url_mismatch" in errors
    assert "decision_hash_mismatch" in errors


def test_invalid_review_time_is_blocked() -> None:
    decision = signed_decision()
    decision["reviewed_at_utc"] = "2026-08-26T05:00:00"
    decision["decision_hash"] = decision_hash(decision)
    decision["review_signature"] = decision_signature(decision, "test-review-key")
    report = validate_decisions([candidate()], [decision], signing_key="test-review-key")
    assert report["status"] == "BLOCKED"
    assert "reviewed_at_must_have_timezone" in report["results"][0]["errors"]
