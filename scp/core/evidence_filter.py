"""Entity/value consistency filtering for SCP evidence.

The filter is deliberately conservative: it removes a record only when the
question has an identifiable entity and the record contains strong, unrelated
proper-name/value anchors. Records without enough structure are retained and
reported as uncertain rather than silently discarded.
"""
from __future__ import annotations

import re
import unicodedata
from typing import Any, Iterable

_STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "can", "có", "cua",
    "của", "do", "does", "for", "from", "how", "in", "is", "it", "là", "la",
    "most", "of", "on", "or", "the", "to", "what", "when", "where", "which",
    "who", "with", "about", "bao", "nhiêu", "nào", "này", "năm", "nước", "thành",
    "phố", "thủ", "đô", "hãy", "cho", "biết", "được", "một", "hai", "từ",
}


def fold_text(value: Any) -> str:
    """Normalize accents/case for robust entity matching."""
    text = str(value or "")
    return "".join(
        char for char in unicodedata.normalize("NFKD", text)
        if not unicodedata.combining(char)
    ).lower()


def _tokens(value: Any) -> list[str]:
    return re.findall(r"[a-z0-9À-ỹ][a-z0-9À-ỹ_-]{2,}", str(value or ""), flags=re.IGNORECASE)


def _query_terms(question: str) -> list[str]:
    terms: list[str] = []
    for raw in _tokens(question):
        token = fold_text(raw).strip("_-")
        if token and token not in _STOPWORDS and token not in terms:
            terms.append(token)
    return terms


def _record_text(record: Any) -> str:
    if isinstance(record, dict):
        preferred = (
            record.get("title"), record.get("snippet"), record.get("answer"),
            record.get("value"), record.get("entity"), record.get("source"),
            record.get("url"), record.get("evidence"),
        )
        return " ".join(str(value) for value in preferred if value not in (None, ""))
    return str(record or "")


def _strong_terms(text: str) -> set[str]:
    """Return likely proper-name/value anchors, excluding generic sentence words."""
    raw = _tokens(text)
    folded = {fold_text(token) for token in raw}
    return {
        token for token in folded
        if len(token) >= 4 and token not in _STOPWORDS
        and not token.isdigit()
    }


def _matches_query(question_terms: Iterable[str], record_text: str) -> set[str]:
    record_terms = set(_tokens(fold_text(record_text)))
    return {term for term in question_terms if term in record_terms}


def filter_evidence_records(
    question: str,
    records: Iterable[dict[str, Any]],
    *,
    strict: bool = False,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Filter retrieved records and return ``(kept, audit_report)``.

    A record is dropped only if it has no query-entity overlap and has at least
    two strong anchors that are absent from the question. This catches entity
    drift such as a Brazil question receiving Saab/Gripen data, while avoiding
    false drops for terse snippets like ``Brasília — capital``.
    """
    question_terms = _query_terms(question)
    question_set = set(question_terms)
    kept: list[dict[str, Any]] = []
    dropped: list[dict[str, Any]] = []
    uncertain: list[dict[str, Any]] = []

    for record in records:
        item = dict(record) if isinstance(record, dict) else {"text": str(record)}
        text = _record_text(item)
        overlap = _matches_query(question_terms, text)
        strong = _strong_terms(text)
        unrelated = {term for term in strong if term not in question_set}

        should_drop = not overlap and len(unrelated) >= (1 if strict else 2)
        if should_drop:
            dropped.append({
                "record": item,
                "reason": "no_query_entity_overlap",
                "unrelatedAnchors": sorted(unrelated)[:12],
            })
        else:
            kept.append(item)
            if not overlap:
                uncertain.append({
                    "record": item,
                    "reason": "retained_without_direct_entity_overlap",
                    "unrelatedAnchors": sorted(unrelated)[:12],
                })

    report = {
        "questionTerms": question_terms,
        "inputCount": len(kept) + len(dropped),
        "keptCount": len(kept),
        "droppedCount": len(dropped),
        "uncertainCount": len(uncertain),
        "dropped": dropped[:20],
        "uncertain": uncertain[:20],
        "filter": "entity-value-consistency-v1",
    }
    return kept, report


def filter_slm_responses(
    question: str,
    responses: Iterable[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Filter only structured SLM evidence; preserve ordinary answer records."""
    response_list = list(responses or [])
    output: list[dict[str, Any]] = []
    structured: list[dict[str, Any]] = []
    for response in response_list:
        item = dict(response) if isinstance(response, dict) else {"answer": str(response)}
        evidence = item.get("evidence")
        if isinstance(evidence, dict) and any(
            evidence.get(key) not in (None, "") for key in ("entity", "value", "source", "unit")
        ):
            structured.append(item)
        else:
            output.append(item)

    kept_structured, report = filter_evidence_records(question, structured)
    output.extend(kept_structured)
    # Keep the source order deterministic; equal dictionaries are rare but valid.
    output.sort(key=lambda item: response_list.index(item) if item in response_list else len(response_list))
    report["structuredResponseCount"] = len(structured)
    report["originalResponseCount"] = len(response_list)
    return output, report


__all__ = ["fold_text", "filter_evidence_records", "filter_slm_responses"]
