"""
[Task 8-A] V105 AutoFix endpoints — extracted from api_server.py

TẠI SAO: api_server.py 2,144 LOC god file. Tách 6 routes /v105/* vào module
này. Backward-compatible — public API paths/methods unchanged.

Routes:
  GET  /v105/autofix/permissions                          — List pending permission requests
  POST /v105/autofix/permissions/{request_id}/approve     — Human approves a fix
  POST /v105/autofix/permissions/{request_id}/deny        — Human denies a fix
  POST /v105/autofix/attack-mode/{enabled}                — Toggle attack mode
  GET  /v105/autofix/stats                                — AutoFix engine stats
  POST /v105/autofix/run-audit                            — Trigger deep audit cycle
  GET  /v105/autofix/monitor                              — [OPT-31] AutoFixMonitor stats (success rate by bug_type/provider/diagnosis)
  POST /v105/autofix/cleanup-cache                        — [OPT-32] Remove legacy broken SmartCache disk entries
  POST /v105/autofix/rollback/{rollback_token}            — [R7-13] Revert a specific auto-approved fix
"""
from __future__ import annotations

import asyncio
import logging
import os
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

# Import shared deps from api_server (same pattern as api/chat.py + admin_v98.py)
from scp.api._shared import verify_admin

logger = logging.getLogger("scp.api.v105")

router = APIRouter(tags=["v105"])


class AutoFixAuditRequest(BaseModel):
    """Bounded audit request; observe mode never writes source files."""

    mode: Literal["apply", "observe"] = "apply"
    max_bugs: int = 0


@router.get("/v105/autofix/permissions", dependencies=[Depends(verify_admin)])
async def v105_list_permissions():
    """List pending permission requests (logic bugs awaiting human approval)."""
    try:
        # [EXEC-1 A2] TẠI SAO: was `AutoFixEngine()` per-request → throwaway
        # instance → attack_mode / rate limits / cooldowns were all no-ops.
        # Use singleton so state persists across handlers.
        from scp.autofix.engine import get_autofix_engine
        eng = get_autofix_engine()
        pending = eng.permission_gate.list_pending()
        return {
            "pending": [
                {
                    "request_id": r.request_id,
                    "file": r.file,
                    "line": r.line,
                    "bug_type": r.bug_type,
                    "description": r.description,
                    "suggested_fix": r.suggested_fix,
                    "timestamp": r.timestamp,
                }
                for r in pending
            ],
            "count": len(pending),
        }
    except Exception as e:
        raise HTTPException(500, f"Error: {e}") from e


@router.post("/v105/autofix/permissions/{request_id}/approve", dependencies=[Depends(verify_admin)])
async def v105_approve_permission(request_id: str, note: str = ""):
    """Human approves a logic bug fix. SCP then applies it.

    [OPT-14 / Gà §11] The `note` field is checked by UnderstandingChecker —
    the human must explain what the fix does in their own words. Empty,
    trivial, or copy-paste notes are rejected with HTTP 400 (the request
    was found, but understanding was not demonstrated).

    [Phase 5-A / 4-a-009] Transactional apply:
      Pre-fix: approve() committed, then apply_approved_fix() called. If
        apply raised (LLM fix fails, file write fails, etc.), the approval
        was already persisted (status="approved") but the fix was never
        applied → "approved-but-not-applied" limbo. The request was no
        longer pending (so couldn't be re-approved via this endpoint) and
        not applied (so the bug remained). Stuck state. DNA #8/#9.
      Post-fix: apply wrapped in try/except. On success → status="applied"
        (terminal). On exception → status="apply_failed" (recoverable —
        operator can re-approve via this endpoint; approve() will re-set
        status to "approved" and the apply retried). Audit trail records
        the error message for operator diagnosis (DNA #8 KB accumulation).
    """
    try:
        # [EXEC-1 A2] singleton — see v105_list_permissions
        from scp.autofix.engine import get_autofix_engine
        eng = get_autofix_engine()
        # Pre-check: is the request even in the pending dict? If not, 404.
        if request_id not in eng.permission_gate._pending:
            raise HTTPException(404, "Permission request not found")
        ok = eng.permission_gate.approve(request_id, decided_by="api_admin", note=note)
        if not ok:
            # [OPT-14 / Gà §11] approve() returned False — either not found
            # (handled above) or understanding check failed. The latter means
            # the human note didn't demonstrate understanding of the fix.
            raise HTTPException(
                400,
                "Approval rejected — note does not demonstrate understanding "
                "(Gà §11). Re-approve with a real explanation in your own "
                "words: explain what the fix does, not just repeat the "
                "suggested_fix text."
            )
        # [Phase 5-A / 4-a-009] Apply the approved fix — TRANSACTIONAL.
        # On success: mark_apply_status(request_id, "applied") — terminal.
        # On exception: mark_apply_status(request_id, "apply_failed", error=...)
        #   → recoverable (operator re-approves via this endpoint; approve()
        #   re-sets status to "approved" and apply is retried). Pre-fix the
        #   request would have been stuck in "approved-but-not-applied" limbo.
        try:
            result = eng.apply_approved_fix(request_id)
        except Exception as apply_exc:
            eng.permission_gate.mark_apply_status(
                request_id, "apply_failed", error=str(apply_exc)
            )
            logger.error(
                f"[v105_approve_permission] apply_failed for {request_id}: "
                f"{apply_exc}"
            )
            raise HTTPException(
                500,
                f"Approved but fix apply FAILED: {apply_exc}. Request "
                f"marked apply_failed — operator can re-approve via this "
                f"endpoint (transactional recovery, DNA #8/#9)."
            ) from apply_exc
        # Apply succeeded — mark as applied (terminal). This distinguishes
        # from the pre-fix limbo where "approved" meant "approved-but-maybe-
        # not-applied" — now "approved" means pending_apply, "applied" means
        # success, "apply_failed" means recoverable failure.
        eng.permission_gate.mark_apply_status(request_id, "applied")
        return {"approved": True, "applied": True, "fix_result": result}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"Error: {e}") from e


@router.post("/v105/autofix/permissions/{request_id}/deny", dependencies=[Depends(verify_admin)])
async def v105_deny_permission(request_id: str, note: str = ""):
    """Human denies a logic bug fix. SCP does not apply it."""
    try:
        # [EXEC-1 A2] singleton — see v105_list_permissions
        from scp.autofix.engine import get_autofix_engine
        eng = get_autofix_engine()
        ok = eng.permission_gate.deny(request_id, decided_by="api_admin", note=note)
        if not ok:
            raise HTTPException(404, "Permission request not found")
        return {"denied": True}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"Error: {e}") from e


@router.post("/v105/autofix/attack-mode/{enabled}", dependencies=[Depends(verify_admin)])
async def v105_toggle_attack_mode(enabled: bool):
    """Toggle attack mode. When ON, SCP auto-applies restraints (Tier 4).
    Use during active attacks — SCP reacts faster than human review."""
    try:
        # [EXEC-1 A2] singleton — CRITICAL: with per-request AutoFixEngine(),
        # attack_mode toggle was LOST on next request (new engine defaulted to
        # False). Singleton persists the toggle across all handlers + runner.
        from scp.autofix.engine import get_autofix_engine
        eng = get_autofix_engine()
        eng.set_attack_mode(enabled)
        return {
            "attack_mode": enabled,
            "message": f"Attack mode {'ENABLED — SCP auto-applies restraints' if enabled else 'DISABLED — normal permission flow'}",
        }
    except Exception as e:
        raise HTTPException(500, f"Error: {e}") from e


@router.get("/v105/autofix/stats", dependencies=[Depends(verify_admin)])
async def v105_autofix_stats():
    """Get AutoFix engine stats for monitoring."""
    try:
        # [EXEC-1 A2] singleton — stats reflect cumulative state across all
        # fixes applied by the engine (not just this request's throwaway).
        from scp.autofix.engine import get_autofix_engine
        eng = get_autofix_engine()
        return eng.stats()
    except Exception as e:
        raise HTTPException(500, f"Error: {e}") from e


@router.post("/v105/autofix/run-audit", dependencies=[Depends(verify_admin)])
async def v105_run_deep_audit(payload: AutoFixAuditRequest | None = None):
    """[EXEC-1 A5] Trigger a deep audit cycle. SCP scans itself for bugs and
    auto-fixes (Tier 1/2) or requests permission (Tier 3).

    This is the WIRING that was missing: AutoFixEngine.process_bug() existed
    but had zero callers — the 4-tier autonomy system was dead code. This
    endpoint invokes scp.autofix.runner.run_deep_audit() which:
      1. AST-scans scp/ for bare `except: pass`, undefined names, syntax errors
      2. For each finding, calls get_autofix_engine().process_bug(bug)
      3. Writes per-bug result to data/deep_audit_results.jsonl

    Returns a summary: {processed, fixed, permission_requested, skipped,
    details, engine_stats, source} — source='ast_scan' confirms the scanner
    actually ran (vs returning empty when no audit_bugs.jsonl exists).

    Idempotent: re-running hits the engine's cooldown (same bug not re-fixed
    within 1h) so safe to call repeatedly.
    """
    try:
        request = payload or AutoFixAuditRequest(
            mode=os.environ.get("SCP_AUTOFIX_MODE", "apply").strip().lower() or "apply",
            max_bugs=int(os.environ.get("SCP_MAX_AUDIT_BUGS", "0") or 0),
        )
        if request.max_bugs < 0 or request.max_bugs > 200:
            raise HTTPException(422, "max_bugs must be between 0 and 200")
        if request.mode == "observe":
            # Observe-only path: scanner evidence is collected, but no
            # AutoFixEngine.process_bug() call is made and no source is written.
            from scp.autofix.runner_phases.ast_scan import ast_scan_scp
            # Observe mode is evidence collection, not a full enterprise
            # security scan. Keep it bounded and non-blocking; apply mode is
            # still available separately with the normal runner contract.
            observe_max_files = min(
                max(10, int(os.environ.get("SCP_OBSERVE_MAX_FILES", "50"))),
                100,
            )
            findings = await asyncio.to_thread(
                ast_scan_scp,
                max_files=observe_max_files,
                max_bugs=request.max_bugs or 20,
                include_enterprise=False,
            )
            if request.max_bugs:
                findings = findings[: request.max_bugs]
            details = [
                {
                    "file": getattr(bug, "file", ""),
                    "line": getattr(bug, "line", 0),
                    "bug_type": getattr(bug, "bug_type", ""),
                    "tier": int(getattr(getattr(bug, "tier", 0), "value", getattr(bug, "tier", 0)) or 0),
                }
                for bug in findings
            ]
            return {
                "audit_complete": True,
                "mode": "observe",
                "results": {
                    "processed": 0,
                    "fixed": 0,
                    "permission_requested": 0,
                    "skipped": len(details),
                    "findings_count": len(details),
                    "details": details,
                    "source": "ast_scan_observe_only",
                },
            }
        from scp.autofix.runner import run_deep_audit
        deterministic_only = os.environ.get("SCP_AUTOFIX_DETERMINISTIC_ONLY", "0") == "1"
        # R9-2: run_deep_audit() AST-scans 371 .py. Production child can
        # explicitly disable provider I/O while still applying deterministic
        # safe fixes and recording unresolved findings as skipped.
        # (deepseek-r1:8b via Ollama — 30s+ per fix). Calling inline from
        # `async def` blocks the event loop for 2-10 min — /health, /ask,
        # WebSocket all freeze. Run in a worker thread (non-blocking).
        results = await asyncio.to_thread(
            run_deep_audit,
            max_bugs=request.max_bugs,
            deterministic_only=deterministic_only,
        )
        return {
            "audit_complete": True,
            "mode": "apply",
            "deterministic_only": deterministic_only,
            "results": results,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"Error: {e}") from e


@router.get("/v105/autofix/monitor", dependencies=[Depends(verify_admin)])
async def autofix_monitor():
    """[OPT-31] AutoFixMonitor stats — success rate by bug_type/provider/diagnosis.

    DNA SCP #8 KB accumulation: expose AutoFix performance for admin dashboard.

    Distinct from `/v105/autofix/stats` (which returns AutoFixEngine cumulative
    counters like total bugs/fixed/skipped) — this endpoint returns the
    AutoFixMonitor view: per-bug-type / per-provider / per-diagnosis breakdowns
    + recent_attempts (last 10). Together they give the admin full visibility:
      - stats   = "what has the engine done?"
      - monitor = "how well is it doing it? which providers succeed?"
    """
    try:
        from scp.autofix.monitor import get_monitor
        monitor = get_monitor()
        stats = monitor.get_stats()
        recent = monitor.get_recent(limit=10)
        return {
            "status": "ok",
            "stats": stats,
            "recent_attempts": recent,
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}


@router.post("/v105/autofix/cleanup-cache", dependencies=[Depends(verify_admin)])
async def cleanup_cache():
    """[OPT-32] Clean up legacy broken SmartCache disk entries.

    TẠI SAO: Task 35-A fixed SLMResponse serialization going forward
    (_slm_response_to_dict at slm_cache_set boundary), but ~9 legacy rows
    already in `smart_cache_disk` table store the broken string repr
    (`"SLMResponse(question='...', ...)"`) instead of a proper JSON dict.
    Task 35-A made _disk_get return None for those (treated as cache miss),
    so they're harmless — but they waste disk space + pollute debug queries.

    DNA SCP #7 safe: cleanup ONLY matches rows whose value_blob decodes to a
    JSON string starting with `"SLMResponse(" — valid JSON dict entries
    (the new format) are untouched.
    """
    try:
        from scp.core.smart_cache import cleanup_legacy_cache_entries
        result = cleanup_legacy_cache_entries()
        return {"status": "ok", "result": result}
    except Exception as e:
        raise HTTPException(500, f"Error: {e}") from e


@router.post("/v105/autofix/tier3-auto/{enabled}", dependencies=[Depends(verify_admin)])
async def v105_toggle_tier3_auto(enabled: str):
    """[V4.3] Toggle Tier-3 auto-approve at RUNTIME — no restart needed.

    User cấp quyền qua API thay vì .env:
      POST /v105/autofix/tier3-auto/1  → enable auto-approve
      POST /v105/autofix/tier3-auto/0  → disable auto-approve

    Safety guards vẫn active (1h timeout, 5/hour limit, etc.)
    Audit log ghi lại: who toggled, when, from what source.
    """
    import os as _os
    old_val = _os.environ.get("SCP_AUTO_APPROVE_TIER3", "0")
    new_val = "1" if enabled in ("1", "true", "on", "yes") else "0"
    _os.environ["SCP_AUTO_APPROVE_TIER3"] = new_val

    # Audit log
    from scp.autofix.engine import get_tier3_config
    config = get_tier3_config()

    # Log toggle event
    import json as _json
    import time as _time
    from pathlib import Path as _Path
    audit = _Path("data/tier3_auto_audit.jsonl")
    audit.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "timestamp": _time.time(),
        "action": "toggle",
        "old_value": old_val,
        "new_value": new_val,
        "source": "API (/v105/autofix/tier3-auto/)",
        "permission_source": config.get_permission_source(),
    }
    try:
        with open(audit, "a", encoding="utf-8") as f:
            f.write(_json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception as _e: logger.debug(f"[silent-except] {_e}")  # noqa: S110

    # Log to SCP console
    import logging as _logging
    _logging.getLogger("scp.autofix").info(
        f"[TIER3-AUTO] Permission TOGGLED via API: {old_val} → {new_val}\n"
        f"  Source: API endpoint\n"
        f"  Safety guards: {'ACTIVE' if new_val == '1' else 'N/A (disabled)'}\n"
        f"  Audit: {audit}"
    )

    return {
        "status": "ok",
        "old_value": old_val,
        "new_value": new_val,
        "enabled": new_val == "1",
        "message": (
            f"Tier-3 auto-approve {'ENABLED' if new_val == '1' else 'DISABLED'} "
            f"(was {old_val}). Safety guards active: 1h timeout, 5/hour limit, "
            f"no relaxation, no BareExceptPass."
        ),
        "audit_log": str(audit),
    }


@router.post("/v105/autofix/rollback/{rollback_token}", dependencies=[Depends(verify_admin)])
async def v105_autofix_rollback(rollback_token: str):
    """[SCP-DNA-FIX R7-13] Revert a specific Tier-3 auto-approved fix by token.

    TẠI SAO: R5/R6 audit log had no rollback_token — operators had to manually
    grep .tier3bak files + figure out which backup matched which fix. R7-13
    extended the audit schema (see _auto_approve_tier3 in engine.py) to write
    a UUID `rollback_token` per auto-approve. This endpoint accepts that token,
    looks up the audit entry, and reverts the file to its `before_hash` state
    by restoring from the .tier3bak backup (if present + hash matches).

    Reality test (R7-13 T2/T3/T4):
      T2 rollback endpoint present ✓ (this route)
      T3 rollback reverts file to before_hash ✓ (hash-verify before restore)
      T4 rollback logged separately ✓ (append action="rollback" to audit log)

    Returns:
      {"status": "ok", "file": <path>, "restored_hash": <sha256>}
      404 if rollback_token not found in audit log
      409 if .tier3bak missing or before_hash doesn't match backup (tamper)
    """
    import json as _json
    import time as _time
    import hashlib as _hashlib
    from pathlib import Path as _Path
    audit_log = _Path("data/tier3_auto_audit.jsonl")
    if not audit_log.is_file():
        raise HTTPException(404, f"Audit log not found at {audit_log}")
    # Find the entry with matching rollback_token (last match wins — most recent).
    matching_entry = None
    try:
        for line in audit_log.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                entry = _json.loads(line)
                if entry.get("rollback_token") == rollback_token:
                    matching_entry = entry
            except Exception:
                continue
    except Exception as e:
        raise HTTPException(500, f"Failed to read audit log: {e}") from e
    if matching_entry is None:
        raise HTTPException(404, f"rollback_token {rollback_token!r} not found in audit log")
    file_path_str = matching_entry.get("file", "")
    before_hash = matching_entry.get("before_hash", "")
    if not file_path_str or not before_hash:
        raise HTTPException(409, "Audit entry lacks file/before_hash (pre-R7-13 entry?)")
    file_path = _Path(file_path_str)
    # [SCP-DNA-FIX R8-5] TẠI SAO: R7-13 dùng single .tier3bak per file →
    # backup CLOBBERED bởi later fix trên cùng file → rollback của fix CŨ
    # fails với misleading 409 "Backup hash mismatch (tampered?)" — backup
    # không bị tamper, bị ghi đè. Fix: per-token backup `.tier3bak.{token}`
    # (engine.py R8-5). Endpoint derive bak_path từ rollback_token. Nếu
    # per-token backup không tồn tại, fall back legacy single .tier3bak
    # (back-compat pre-R8-5 entries) trước khi error.
    bak_path_token = file_path.with_suffix(
        file_path.suffix + f".tier3bak.{rollback_token}"
    )
    bak_path_legacy = file_path.with_suffix(file_path.suffix + ".tier3bak")
    if bak_path_token.is_file():
        bak_path = bak_path_token
    elif bak_path_legacy.is_file():
        # Pre-R8-5 entry OR uuid failed at fix time — use legacy single backup.
        bak_path = bak_path_legacy
    else:
        raise HTTPException(
            409,
            f"No backup for rollback_token {rollback_token!r} on file {file_path}. "
            f"Either the fix pre-dates R8-5 (single .tier3bak, since clobbered by "
            f"a later fix on same file) or the backup was deleted. "
            f"R8-5 note: per-token backups (.tier3bak.{{token}}) added to prevent "
            f"this clobber — older single-.tier3bak entries remain vulnerable."
        )
    # Verify backup hash matches before_hash (tamper detection).
    bak_hash = _hashlib.sha256(bak_path.read_bytes()).hexdigest()
    if bak_hash != before_hash:
        raise HTTPException(
            409,
            f"Backup hash mismatch for token {rollback_token!r}: "
            f"expected={before_hash} got={bak_hash}. "
            f"Likely cause: pre-R8-5 single-.tier3bak was clobbered by a LATER "
            f"fix on same file (the backup you're reading is from a newer fix, "
            f"not tampered). Apply fixes in newest-first order or upgrade to "
            f"R8-5 per-token backups (already done for new fixes)."
        )
    # Restore: ATOMIC write to target via temp file + fsync + os.replace.
    # [Phase 5-A / 4-a-008] Old code did `file_path.write_text(backup_content)`
    # directly — if interrupted mid-write (disk full, crash, signal), the
    # target file was left truncated/corrupt. A SAFETY mechanism that corrupts
    # the file on failure is worse than no rollback (DNA #7, #9).
    #
    # New flow:
    #   1. Read backup content into memory (small files — typical .py source).
    #   2. tempfile.mkstemp(dir=target_dir) → temp file in SAME directory
    #      (so os.replace is atomic — POSIX guarantees atomic rename within
    #      the same filesystem; same-dir temp guarantees same filesystem).
    #   3. Write content, flush, fsync (durability — survives power loss).
    #   4. Verify temp-file hash matches before_hash BEFORE the rename
    #      (catches disk corruption / encoding issues without touching the
    #      live file).
    #   5. os.replace(tmp, target) — atomic on POSIX. Either old or new,
    #      never partial.
    #   6. On ANY exception: os.unlink(tmp) to clean up temp, then raise.
    import os as _os
    import tempfile as _tempfile
    backup_content = bak_path.read_text(encoding="utf-8")
    target_dir = file_path.parent
    try:
        target_dir.mkdir(parents=True, exist_ok=True)
    except Exception as e:  # noqa: BLE001 — DNA #23 honest limit
        raise HTTPException(500, f"Failed to ensure target dir exists: {e}") from e
    fd, tmp_path = _tempfile.mkstemp(
        dir=str(target_dir),
        prefix=".rollback-tmp-",
        suffix=file_path.suffix or ".tmp",
    )
    try:
        with _os.fdopen(fd, "w", encoding="utf-8", newline="") as f:
            f.write(backup_content)
            f.flush()
            _os.fsync(f.fileno())
        # Pre-rename hash verification — if temp doesn't match before_hash,
        # the temp file is corrupt; DO NOT rename. Original file untouched.
        tmp_hash = _hashlib.sha256(_Path(tmp_path).read_bytes()).hexdigest()
        if tmp_hash != before_hash:
            raise HTTPException(
                500,
                f"Pre-rename temp hash mismatch: expected={before_hash} "
                f"got={tmp_hash}. Target file UNTOUCHED (atomic restore "
                f"aborted before os.replace)."
            )
        # ATOMIC rename — POSIX guarantees atomicity within same filesystem.
        _os.replace(tmp_path, str(file_path))
    except HTTPException:
        try:
            _os.unlink(tmp_path)
        except OSError:
            pass  # tmp may already be gone (os.replace succeeded) — fine
        raise
    except Exception as e:
        try:
            _os.unlink(tmp_path)
        except OSError:
            pass
        raise HTTPException(500, f"Failed to restore file atomically: {e}") from e
    # Verify post-restore hash matches before_hash.
    restored_hash = _hashlib.sha256(file_path.read_bytes()).hexdigest()
    if restored_hash != before_hash:
        raise HTTPException(500, f"Post-restore hash mismatch: expected={before_hash} got={restored_hash}")
    # [R7-13 T4] Log the rollback as a separate audit entry (action="rollback").
    rollback_entry = {
        "timestamp": _time.time(),
        "action": "rollback",
        "rollback_token": rollback_token,
        "file": file_path_str,
        "restored_hash": restored_hash,
        "original_audit_timestamp": matching_entry.get("timestamp"),
        "source": "API (/v105/autofix/rollback/)",
    }
    try:
        with open(audit_log, "a", encoding="utf-8") as f:
            f.write(_json.dumps(rollback_entry, ensure_ascii=False) + "\n")
    except Exception as _e:
        logger.warning(f"[R7-13] Failed to log rollback entry: {_e}")
    logger.info(
        f"[R7-13] Rollback SUCCESS: token={rollback_token} file={file_path_str} "
        f"restored_hash={restored_hash[:12]}..."
    )
    return {
        "status": "ok",
        "rollback_token": rollback_token,
        "file": file_path_str,
        "restored_hash": restored_hash,
        "original_audit_timestamp": matching_entry.get("timestamp"),
        "message": f"File {file_path_str} reverted to before_hash state.",
    }
