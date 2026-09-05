"""[M1] Evidence Replay — commit-leg evidence for the AutoFix pipeline.

TẠI SAO file này tồn tại?
  Trước M1: replay_evidence() trả về {"status": "seeded"} — fake evidence
  (DNA #22: PASS ≠ TRUE). Commit-leg cần một primitive THẬT: so sánh bug đã
  ghi nhận (bug_signature) với trạng thái post-fix scan. Nếu bug pattern vẫn
  còn → fix KHÔNG có evidence → ok=False. Nếu bug đã biến mất → ok=True.

Contract (mission M1):
  compute_bug_signature(bug_type, file_path, line)
      → sha256 của canonical tuple (bug_type, file_path, line). Signature
        cũng được đăng ký nội bộ để verify() có thể đối chiếu finding dù
        line đã dịch sau patch (cùng ngữ nghĩa completeness_check: line
        KHÔNG được so sánh — bug class + file mới là điều kiện "vẫn còn").
  verify(bug_signature, post_fix_scan_results)
      → bug pattern vẫn còn → {"ok": False, "reason": "bug still present"}
      → bug đã gone        → {"ok": True}
      → không có post-fix scan evidence / signature không rõ nguồn
                           → ok=False, status=UNVERIFIED (fail-closed)

post_fix_scan_results chấp nhận:
  - list finding (dict hoặc object có .bug_type/.file/.line) — scanner output
  - dict có "findings" / "remaining" / "bugs" (list)
  - dict kết quả completeness_check ("complete" / "remaining_count" /
    "remaining_lines" / "scanner_used")
"""
from __future__ import annotations

import hashlib
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger("scp.autofix.evidence_replay")

# bug_signature → record it was computed from (module-local, process-scoped).
# verify() dùng record này để match finding theo (bug_type, file) dù line dịch.
_RECORDS: dict[str, dict[str, Any]] = {}


def compute_bug_signature(bug_type: str, file_path: str, line: int | None = None) -> str:
    """sha256 of the canonical (bug_type, file_path, line) tuple.

    Canonical form: the three fields joined by the ASCII unit separator
    (\\x1f) — unambiguous even when fields contain "|" or spaces; file_path
    backslashes normalized to "/" so Windows/POSIX spellings hash identically.
    Registers the signature → record mapping for verify() (process-scoped).
    """
    line_int: int | None
    try:
        line_int = int(line) if line is not None else None
    except (TypeError, ValueError):
        line_int = None
    canonical = "\x1f".join(
        [
            str(bug_type or "").strip(),
            str(file_path or "").replace("\\", "/").strip(),
            str(line_int) if line_int is not None else "",
        ]
    )
    signature = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    _RECORDS[signature] = {
        "bug_type": str(bug_type or "").strip(),
        "file_path": str(file_path or ""),
        "line": line_int,
    }
    return signature


def _finding_fields(finding: Any) -> dict[str, Any]:
    """Extract (bug_type, file, line) from a finding dict or object."""
    if isinstance(finding, dict):
        return {
            "bug_type": str(finding.get("bug_type", "") or ""),
            "file": str(finding.get("file", finding.get("file_path", "")) or ""),
            "line": finding.get("line", finding.get("line_number")),
        }
    return {
        "bug_type": str(getattr(finding, "bug_type", "") or ""),
        "file": str(getattr(finding, "file", getattr(finding, "file_path", "")) or ""),
        "line": getattr(finding, "line", None),
    }


def _normalize_findings(post_fix_scan_results: Any) -> list[dict[str, Any]]:
    """Normalize list / envelope post-fix scan shapes into finding fields.

    Raises ValueError for unrecognized shapes (caller converts to UNVERIFIED).
    """
    if isinstance(post_fix_scan_results, list):
        return [_finding_fields(f) for f in post_fix_scan_results]

    if isinstance(post_fix_scan_results, dict):
        # Generic scan-result envelope with a findings list.
        for key in ("findings", "remaining", "bugs"):
            if key in post_fix_scan_results and isinstance(post_fix_scan_results[key], list):
                return [_finding_fields(f) for f in post_fix_scan_results[key]]

    raise ValueError(
        f"unrecognized post_fix_scan_results shape: {type(post_fix_scan_results).__name__}"
    )


def _resolve(path_str: str) -> str:
    """Best-effort resolved path string for cross-platform comparison."""
    try:
        return str(Path(path_str).resolve()) if path_str else ""
    except Exception:  # noqa: BLE001 — unresolvable path → compare raw string
        return path_str


def verify(bug_signature: str, post_fix_scan_results: Any) -> dict:
    """Compare the recorded bug against the post-fix scan state.

    Returns:
        {"ok": True, "status": "VERIFIED", "reason": "bug pattern gone post-fix", ...}
          — the recorded bug class is no longer present in post-fix findings.
        {"ok": False, "reason": "bug still present", ...}
          — a post-fix finding matches the recorded bug (same bug_type + file;
            line intentionally ignored, the bug may have shifted), or the
            completeness re-scan reports the bug class still in the file.
        {"ok": False, "status": "UNVERIFIED", "reason": "..."}
          — no usable post-fix evidence, or the signature was not computed via
            compute_bug_signature in this process (fail-closed, never fake-pass).
    """
    record = _RECORDS.get(bug_signature)
    if record is None:
        return {
            "ok": False,
            "status": "UNVERIFIED",
            "reason": (
                "unknown bug_signature (not computed via compute_bug_signature "
                "in this process) — cannot match against post-fix state"
            ),
            "bug_signature": bug_signature,
        }

    def _still_present(matched: dict[str, Any] | None = None) -> dict:
        result = {
            "ok": False,
            "reason": "bug still present",
            "status": "UNVERIFIED",
            "bug_signature": bug_signature,
        }
        if matched is not None:
            result["matched_finding"] = matched
        return result

    def _gone() -> dict:
        return {
            "ok": True,
            "status": "VERIFIED",
            "reason": "bug pattern gone post-fix",
            "bug_signature": bug_signature,
        }

    # completeness_check result shape — direct comparison, no finding parsing
    # (its remaining_count/complete fields ARE the post-fix verdict for the
    # recorded bug class in the recorded file).
    if isinstance(post_fix_scan_results, dict) and (
        "complete" in post_fix_scan_results or "remaining_count" in post_fix_scan_results
    ):
        if str(post_fix_scan_results.get("scanner_used", "")) == "none":
            # "Assume complete" without running a scanner is NOT evidence.
            return {
                "ok": False,
                "status": "UNVERIFIED",
                "reason": (
                    "post-fix scan never ran the bug's scanner "
                    "(scanner_used='none') — completeness is assumed, not proven"
                ),
                "bug_signature": bug_signature,
            }
        remaining_count = int(post_fix_scan_results.get("remaining_count") or 0)
        is_complete = bool(
            post_fix_scan_results.get("complete", remaining_count == 0)
        )
        if not is_complete or remaining_count > 0:
            return _still_present({
                "remaining_count": remaining_count,
                "remaining_lines": list(post_fix_scan_results.get("remaining_lines") or []),
            })
        return _gone()

    # List / envelope shapes → match findings against the recorded bug.
    try:
        findings = _normalize_findings(post_fix_scan_results)
    except ValueError as exc:
        return {
            "ok": False,
            "status": "UNVERIFIED",
            "reason": f"post-fix scan evidence unusable: {exc}",
            "bug_signature": bug_signature,
        }

    rec_type = record["bug_type"]
    rec_file = _resolve(record["file_path"])
    for finding in findings:
        f_type = finding["bug_type"]
        same_type = bool(f_type) and (
            f_type == rec_type or f_type.startswith(rec_type) or rec_type.startswith(f_type)
        )
        if not same_type:
            continue
        f_file = finding["file"]
        same_file = _resolve(f_file) == rec_file if (f_file and rec_file) else (
            f_file == record["file_path"]
        )
        if same_file:
            return _still_present({
                "bug_type": f_type,
                "file": f_file,
                "line": finding["line"],
            })

    return _gone()


def replay_evidence(bug_signature: str, post_fix_scan_results: Any = None) -> dict:
    """Replay the recorded bug evidence against post-fix scan results.

    Back-compat entry point (was: returned fake {"status": "seeded"}).
    Without post-fix scan results there is no evidence → UNVERIFIED.
    """
    if post_fix_scan_results is None:
        return {
            "ok": False,
            "status": "UNVERIFIED",
            "reason": "no post-fix scan results to replay against",
            "bug_signature": bug_signature,
        }
    return verify(bug_signature, post_fix_scan_results)


__all__ = ["compute_bug_signature", "verify", "replay_evidence"]
