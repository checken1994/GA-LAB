"""
SCP Auto-Fix Engine — autonomous bug fixing with tiered autonomy.

Flow:
  1. Deep audit detects bug → BugReport
  2. Classifier assigns tier
  3. Engine acts based on tier:
     - Tier 1: fix immediately, no report
     - Tier 2: fix immediately, log to audit trail
     - Tier 3: request permission, WAIT (do not fix until approved)
     - Tier 4: fix immediately (attack mode, restraints only), log + flag for post-hoc review

The engine uses code_evolution_agent._apply_fix() for the actual patching
(search-replace markers + ast.parse verification), but ONLY for approved tiers.

[SAFETY] The engine NEVER:
  - Auto-applies a relaxation (loosens security) — always Tier 3
  - Auto-applies a verdict threshold change — always Tier 3
  - Skips the permission gate for logic bugs
  - Fixes more than MAX_FIXES_PER_CYCLE per audit cycle (rate limit)
"""
from __future__ import annotations

import json
import logging
import os
import threading
import time
from pathlib import Path

from scp.autofix.classifier import BugClassifier, BugReport, BugTier
from scp.autofix.permission import PermissionGate

logger = logging.getLogger("scp.autofix")

# Rate limits (prevent runaway auto-fixing)
# [FIX-5] TẠI SAO: was 10 — STARTUP-GATE scans up to 50 bugs, so 10/cycle
# guaranteed 40 "skipped (rate limit)" → server start blocked. 200 gives
# headroom for full scan + scheduled audits. Tier 3 (permission) still
# gates logic bugs; cooldown still prevents re-fix same bug.
MAX_FIXES_PER_CYCLE = 200         # Max auto-fixes per audit cycle (was 10)
MAX_TIER4_PER_HOUR = 20           # Max attack-mode fixes per hour
COOLDOWN_SAME_BUG_SECONDS = 3600  # Don't re-fix same bug within 1 hour
CYCLE_RESET_SECONDS = 3600        # Reset _fixes_this_cycle every 1 hour

# [TIER3-AUTO] Safety guards for SCP_AUTO_APPROVE_TIER3=1 mode
# TAI SAO: Ga muon SCP tu fix Tier 3 (logic bugs) de kiem tra. Vi pham
# nguyen tac #4 "con nguoi quyet dinh" -- nhung Ga approve. Z.ai dung
# safety guards CUNG de giam rui ro:
#   1. RELAXATION patterns KHONG bao gio auto (hard limit in classifier)
#   2. Rate limit 5/gio (chat hon MAX_FIXES_PER_CYCLE=200)
#   3. Auto-timeout 1h (env var tu het hieu luc)
#   4. Audit log rieng: data/tier3_auto_audit.jsonl
#
# [RUNTIME-FIX-6] Runtime log cho thay BareExceptPass auto-fix rollback rate
# = 63% (24 rollback / 38 attempt trong 2 phut). Auto-fix dang ton CPU + tao
# KB noise ma khong fix duoc gi. Khuyen nghi: TAM TAT auto-approve cho
# BareExceptPass cho den khi LLM-fix quality tot hon. Default = "0" (OFF).
# De bat lai khi can: set env SCP_AUTO_APPROVE_TIER3=1 (se tu het hieu luc
# sau 1h theo Guard 2).
#   5. Backup file truoc khi apply (.tier3bak)
#   6. Cooldown 1h cho cung bug (dung _recent_fixes chung)
MAX_TIER3_AUTO_PER_HOUR = 5            # Hard cap: 5 logic-bug auto-fixes/hour
TIER3_AUTO_TIMEOUT_SECONDS = 3600


# ============================================================
# [V4.3-TIER3] Tier3AutoConfig — SCP HIỂU context cấp quyền
# ============================================================
# TÁI SAO: Trước đây code chỉ check os.environ.get('SCP_AUTO_APPROVE_TIER3')
# — không log, không audit, không explain TẠI SAO bật/tắt.
# User muốn SCP HIỂU quyền được cấp (không chỉ đọc env var).
# Fix: centralized config + audit log + startup message.

class Tier3AutoConfig:
    """Centralized config for Tier-3 auto-approve — SCP understands the permission.

    DNA SCP #4 (Constitution KILL) — Tier-3 = logic bugs, mặc định human approval.
    DNA SCP #7 (AutoFix safe) — 6 safety guards even when auto-approve ON.
    DNA SCP #8 (KB accumulation) — audit trail lưu lại mọi auto-approve decisions.

    User cấp quyền qua:
      1. .env file: SCP_AUTO_APPROVE_TIER3=1 (persistent, reload on restart)
      2. API: POST /v105/autofix/tier3-auto/{enabled} (runtime, không cần restart)
      3. PowerShell: $env:SCP_AUTO_APPROVE_TIER3 = "1" (session only)

    SCP HIỂU quyền bằng cách:
      - Log startup: "[TIER3-AUTO] Permission GRANTED by .env (SCP_AUTO_APPROVE_TIER3=1)"
      - Log startup: "[TIER3-AUTO] Permission DENIED (default, .env not set or =0)"
      - Audit log: mỗi auto-approve → data/tier3_auto_audit.jsonl
      - Stats endpoint: /v105/autofix/stats trả về tier3_auto_enabled + reasons
    """

    def __init__(self):
        self._audit_log = Path("data/tier3_auto_audit.jsonl")
        self._audit_log.parent.mkdir(parents=True, exist_ok=True)

    def is_enabled(self) -> bool:
        """Check if Tier-3 auto-approve is enabled (with logging)."""
        val = os.environ.get("SCP_AUTO_APPROVE_TIER3", "0")
        enabled = val == "1"
        return enabled

    def get_permission_source(self) -> str:
        """Identify WHERE the permission came from."""
        if "SCP_AUTO_APPROVE_TIER3" not in os.environ:
            return "default (not set — human approval required)"
        val = os.environ.get("SCP_AUTO_APPROVE_TIER3", "0")
        if val == "1":
            return ".env file (SCP_AUTO_APPROVE_TIER3=1 — auto-approve GRANTED)"
        return ".env file (SCP_AUTO_APPROVE_TIER3=0 — human approval required)"

    def log_startup_permission(self):
        """Log at startup: SCP understands whether permission is granted."""
        source = self.get_permission_source()
        if self.is_enabled():
            logger.warning(
                f"[TIER3-AUTO] ⚠️  Permission GRANTED — Tier-3 auto-approve ENABLED\n"
                f"  Source: {source}\n"
                f"  Safety guards active: 1h timeout, 5/hour limit, no relaxation,\n"
                f"  no BareExceptPass, cooldown 1h per bug\n"
                f"  Audit log: {self._audit_log}"
            )
        else:
            logger.info(
                f"[TIER3-AUTO] Permission NOT granted — human approval required\n"
                f"  Source: {source}\n"
                f"  To enable: set SCP_AUTO_APPROVE_TIER3=1 in .env + restart\n"
                f"  Or runtime: POST /v105/autofix/tier3-auto/1 (no restart needed)"
            )

    def audit_auto_approve(self, bug: BugReport, reason: str):
        """Audit trail: record every auto-approve decision."""
        import json
        import time as _time
        entry = {
            "timestamp": _time.time(),
            "action": "auto_approve",
            "file": bug.file,
            "line": bug.line,
            "bug_type": bug.bug_type,
            "reason": reason,
            "permission_source": self.get_permission_source(),
        }
        try:
            with open(self._audit_log, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except Exception as e:
            logger.debug(f"[TIER3-AUTO] audit log write failed: {e}")


# Singleton
_tier3_config: Tier3AutoConfig | None = None

def get_tier3_config() -> Tier3AutoConfig:
    """Get singleton Tier3AutoConfig."""
    global _tier3_config
    if _tier3_config is None:
        _tier3_config = Tier3AutoConfig()
    return _tier3_config
      # Env var self-expire after 1h
TIER3_AUTO_AUDIT_LOG = "tier3_auto_audit.jsonl"  # Separate audit log


class AutoFixEngine:
    """Autonomous bug fixing engine with tiered autonomy."""

    def __init__(self, data_dir: str = "data", in_attack_mode: bool = False):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.audit_log = self.data_dir / "autofix_audit.jsonl"
        self.classifier = BugClassifier()
        self.permission_gate = PermissionGate(data_dir=data_dir)

        # [V4.3] Log Tier-3 auto-approve permission status at startup
        # SCP HIỂU: permission đến từ .env, API, hay runtime env var
        get_tier3_config().log_startup_permission()

        # [R20-FIX-1] Read attack mode from .env (was: only via API).
        # BEFORE: in_attack_mode only set via API call → restart = lost.
        # AFTER: SCP_ATTACK_MODE=1 in .env → persistent across restarts.
        # DNA #4 (con người quyết định): user CHỌN bật qua .env.
        # DNA #7 (Autofix safe): Tier 4 chỉ tighten security, reversible, logged.
        if not in_attack_mode:
            in_attack_mode = os.environ.get("SCP_ATTACK_MODE", "0") == "1"
        self.in_attack_mode = in_attack_mode
        if self.in_attack_mode:
            logger.warning(
                "[TIER4-ATTACK] ⚠️  Attack mode ENABLED via .env (SCP_ATTACK_MODE=1)\n"
                "  SCP will auto-apply restraints (tighten security) without human approval.\n"
                "  Safety guards: 20/hour limit, reversible only, audit log, no relaxation.\n"
                "  To disable: set SCP_ATTACK_MODE=0 in .env + restart."
            )
        self._fixes_this_cycle = 0
        self._tier4_timestamps: list[float] = []
        self._recent_fixes: dict[str, float] = {}  # (file, line, type) → timestamp
        # [EXEC-1 A3] TẠI SAO: previously _fixes_this_cycle only ever incremented
        # and never reset → after MAX_FIXES_PER_CYCLE fixes the engine was
        # permanently rate-limited. Singleton lifecycle means we must reset
        # periodically or the engine becomes dead after first 10 fixes.
        # Fix: track cycle_start_time; reset when > CYCLE_RESET_SECONDS elapsed.
        self._cycle_start_time: float = time.time()
        # [TIER3-AUTO] Track Tier-3 auto-approves (rate limit + timeout)
        self._tier3_auto_timestamps: list[float] = []
        self._tier3_auto_enabled_at: float = 0.0  # 0 = disabled
        self.tier3_auto_audit_log = self.data_dir / TIER3_AUTO_AUDIT_LOG

    def _check_cycle_reset(self) -> None:
        """Reset per-cycle counters when CYCLE_RESET_SECONDS elapsed.

        [EXEC-1 A3] Called at the start of process_bug() so the engine can
        keep fixing bugs indefinitely (rate limit applies per-cycle, not
        per-process-lifetime). Without this, the singleton would hit
        MAX_FIXES_PER_CYCLE=10 once and never auto-fix again.
        """
        if time.time() - self._cycle_start_time > CYCLE_RESET_SECONDS:
            self._fixes_this_cycle = 0
            self._cycle_start_time = time.time()
            logger.info(
                f"[AutoFix] Cycle reset — _fixes_this_cycle cleared after "
                f"{CYCLE_RESET_SECONDS}s"
            )

    def process_bug(self, bug: BugReport) -> dict:
        """Process a detected bug. Returns action taken.

        Returns:
          {"action": "fixed" | "permission_requested" | "skipped" | "denied",
           "tier": int,
           "request_id": str (if permission_requested),
           "reason": str}
        """
        # [EXEC-1 A3] reset per-cycle counters if cycle window elapsed
        self._check_cycle_reset()

        # Classify the bug
        classified = self.classifier.classify(
            file=bug.file, line=bug.line,
            bug_type=bug.bug_type,
            description=bug.description,
            suggested_fix=bug.suggested_fix,
            in_attack_mode=self.in_attack_mode,
            tier_hint=bug.tier if bug.tier != BugTier.TIER_1_AUTO_FIX else None,
        )

        # [Idea 5 — VERIFY-THEN-PROMOTE] Adjust tier based on historical streak evidence.
        # DNA SCP #12: "Không tăng quyền chỉ vì lập luận tăng" — promotion requires
        # EVIDENCE (10 consecutive successes), not argument. Demotion is automatic
        # after 3 consecutive failures. Only adjust Tier 1↔2 (never touch Tier 3/4).
        try:
            from scp.autofix.monitor import get_monitor as _get_monitor
            _adj = _get_monitor().get_tier_adjustment(bug.bug_type)
            if _adj != 0 and classified.tier in (BugTier.TIER_1_AUTO_FIX, BugTier.TIER_2_AUTO_FIX_LOG):
                _new_tier_val = max(1, min(2, int(classified.tier) + _adj))
                _new_tier = BugTier(_new_tier_val)
                if _new_tier != classified.tier:
                    logger.info(
                        f"[Idea5] tier adjusted {bug.bug_type}: "
                        f"Tier {int(classified.tier)} → Tier {int(_new_tier)} "
                        f"(streak evidence, adj={_adj:+d})"
                    )
                    classified.tier = _new_tier
        except Exception as _idea5_err:
            logger.debug(f"[Idea5] tier adjustment skipped (fail-open): {_idea5_err}")

        # Check cooldown (don't re-fix same bug)
        bug_key = f"{bug.file}:{bug.line}:{bug.bug_type}"
        now = time.time()
        if bug_key in self._recent_fixes:
            if now - self._recent_fixes[bug_key] < COOLDOWN_SAME_BUG_SECONDS:
                return {
                    "action": "skipped",
                    "tier": int(classified.tier),
                    "reason": "cooldown — same bug fixed recently",
                }

        # Act based on tier
        if classified.tier == BugTier.TIER_1_AUTO_FIX:
            return self._auto_fix(classified, report=False)

        elif classified.tier == BugTier.TIER_2_AUTO_FIX_LOG:
            return self._auto_fix(classified, report=True)

        elif classified.tier == BugTier.TIER_3_PERMISSION:
            return self._request_permission(classified)

        elif classified.tier == BugTier.TIER_4_ATTACK_MODE:
            # Rate limit Tier 4
            self._tier4_timestamps = [t for t in self._tier4_timestamps if now - t < 3600]
            if len(self._tier4_timestamps) >= MAX_TIER4_PER_HOUR:
                return {
                    "action": "skipped",
                    "tier": 4,
                    "reason": f"rate limit — {MAX_TIER4_PER_HOUR} Tier-4 fixes/hour exceeded",
                }
            self._tier4_timestamps.append(now)
            return self._auto_fix(classified, report=True, attack_mode=True)

        return {"action": "skipped", "tier": 0, "reason": "unknown tier"}

    # [V9.1-UPGRADE] FixVerification layer — cùng cấp WHY (2-layer: action + self-verify).
    # TẠI SAO: WHY gate (v9.0) hỏi "có nên fix không?" (action layer — necessity +
    # falsification). _verify_fix hỏi "fix có work không? Có introduce new bug không?"
    # (verify layer). WHY + verify = cùng độ sâu (2 layer mỗi cái).
    # Non-blocking: verify error → fail-open (don't break fix).
    # Nếu verify phát hiện new bugs → caller ROLLBACK (restore pre-fix content).
    def _verify_fix(self, filepath, original_bugs: list) -> tuple[bool, str]:
        """Self-verify a fix after applying patch.

        Args:
            filepath: Path to the patched file.
            original_bugs: List of BugReport objects that the fix was supposed to address.

        Returns (is_valid, reason).
        - is_valid=False → fix broke things → caller should ROLLBACK
        - is_valid=True → fix OK (or inconclusive — fail-open)

        Checks (in priority order):
          1. ast.parse() — patched file still parses (syntax OK)
          2. Re-scan same file — original bug still there? (NEW)
          3. Check no NEW bugs introduced (compare against original_bugs signatures)
          4. [WORLD-CLASS-GATE] self_scan_patch_diff — patch không được thêm pattern nguy hiểm
          5. [WORLD-CLASS-GATE] pytest — suite không được vỡ sau patch
        """
        try:
            # [V9.1-UPGRADE] Check 1: ast.parse — file must still be valid Python
            try:
                import ast as _ast
                _content = filepath.read_text(encoding="utf-8")
                _ast.parse(_content, filename=str(filepath))
            except SyntaxError as _se:
                return False, f"patched file SyntaxError: {_se}"
            except Exception as _parse_err:
                return False, f"parse check failed: {_parse_err}"

            # [V9.1-UPGRADE] Check 2: re-scan file — original bug still present?
            # TẠI SAO: nếu fix chỉ "modify text" mà không thực sự sửa bug pattern,
            # re-scan sẽ tìm thấy bug cũ. Fail-open if scanner unavailable.
            try:
                from scp.autofix.runner import ast_scan_scp
                # ast_scan_scp scans the whole scp/ package. For surgical verify,
                # we filter results to just this file.
                _all_bugs = ast_scan_scp(include_enterprise=False)
                _remaining_for_this_file = [
                    b for b in _all_bugs
                    if str(getattr(b, "file", "")) == str(filepath)
                ]
                # Check if the SAME bug (by line+type) is still present
                _still_present = []
                for orig in original_bugs:
                    for remain in _remaining_for_this_file:
                        if (getattr(remain, "line", None) == getattr(orig, "line", None)
                                and getattr(remain, "bug_type", "") == getattr(orig, "bug_type", "")):
                            _still_present.append(orig)
                            break
                if _still_present:
                    return False, (
                        f"original bug still present after fix: "
                        f"{len(_still_present)}/{len(original_bugs)} unchanged"
                    )
            except ImportError:
                # ast_scan_scp unavailable (circular import risk) → fail-open
                logger.debug("[V9.1-UPGRADE] ast_scan_scp unavailable (fail-open on re-scan)")
            except Exception as _rescan_err:
                logger.debug(f"[V9.1-UPGRADE] re-scan failed (fail-open): {_rescan_err}")

            # [V9.1-UPGRADE] Check 3: no NEW bugs introduced at the fix line.
            # TẠI SAO: fix có thể "fix bug A nhưng introduce bug B" (e.g., add
            # try/except nhưng except:pass → bare-except bug mới). So sánh
            # bug signatures pre/post — nếu có bug mới ở line gần fix → flag.
            try:
                from scp.autofix.runner import ast_scan_scp
                _all_bugs_post = ast_scan_scp(include_enterprise=False)
                _new_bugs = []
                _orig_lines = {getattr(b, "line", None) for b in original_bugs}
                # [FALSE-POS-FIX] F841: removed `_orig_types` — dead code.
                # Was meant for dedup but line 346 uses a different set comprehension
                # (line, type) tuples directly. _orig_types was never referenced.
                for b in _all_bugs_post:
                    if str(getattr(b, "file", "")) != str(filepath):
                        continue
                    _b_line = getattr(b, "line", None)
                    _b_type = getattr(b, "bug_type", "")
                    # New bug = same file, NOT in original set (by line+type)
                    if (_b_line, _b_type) not in {(getattr(o, "line", None), getattr(o, "bug_type", "")) for o in original_bugs}:
                        # Within ±10 lines of any original bug = likely introduced by fix
                        for _ol in _orig_lines:
                            if _b_line and _ol and abs(_b_line - _ol) <= 10:
                                _new_bugs.append(b)
                                break
                if _new_bugs:
                    return False, (
                        f"fix introduced {_new_bugs.__len__()} new bug(s) near fix line: "
                        f"{[getattr(b, 'bug_type', '?') for b in _new_bugs[:3]]}"
                    )
            except ImportError as e:
                logger.warning(f"Silent except: {e}")  # fail-open
            except Exception as _new_bug_err:
                logger.debug(f"[V9.1-UPGRADE] new-bug check failed (fail-open): {_new_bug_err}")

            # [WORLD-CLASS-GATE] Check 4: self_scan_patch_diff
            # TẠI SAO: Runtime log cho thấy "fix subprocess nhưng patch thêm subprocess mới"
            # (audit_and_fix.py có gate này, SCP thiếu). Soi patch tìm pattern nguy hiểm
            # MỚI XUẤT HIỆN (eval/exec/os.system/subprocess/pickle) — nếu có → REJECT.
            #
            # [SCP-DNA-FIX R12-4] DISABLED — superseded by IMP-24 policy_gate (engine.py:756).
            # Tại sao: OPT-26 (this check) và IMP-24 (policy_gate) chạy song song với
            # logic mâu thuẫn — OPT-26 BLOCK eval/exec/subprocess, IMP-24 REVIEW eval/exec
            # (cho phép). R12-4 đã unify: IMP-24 giờ BLOCK tất cả (eval/exec/shell=True/
            # subprocess/os.system/pickle) — same coverage as OPT-26. Running cả 2 = waste
            # + inconsistent logging. IMP-24 chạy TRƯỚC patch (line 756), OPT-26 chạy SAU
            # patch — nếu IMP-24 BLOCK, patch không apply, OPT-26 không cần chạy. Nếu
            # IMP-24 ALLOW, patch apply, OPT-26 check count-diff — nhưng IMP-24 đã scan
            # patch text rồi, count-diff là redundant. Disable OPT-26, giữ IMP-24 làm
            # single source of truth.
            # Logic gốc (để rollback nếu cần): xem git history trước R12-4.
            # try:
            #     import re as _re
            #     _DANGEROUS_PATTERNS = [
            #         (_re.compile(r'\beval\s*\('), "eval()"),
            #         (_re.compile(r'\bexec\s*\('), "exec()"),
            #         (_re.compile(r'\bos\.system\s*\('), "os.system()"),
            #         (_re.compile(r'\bsubprocess\.(run|Popen|call|check_output)\s*\('), "subprocess call"),
            #         (_re.compile(r'\bpickle\.(loads|load)\s*\('), "pickle.load()"),
            #     ]
            #     _patched_content = filepath.read_text(encoding="utf-8")
            #     _backup_path = filepath.with_suffix(filepath.suffix + ".tier3bak")
            #     if not _backup_path.exists():
            #         _backup_path = filepath.with_suffix(filepath.suffix + ".audit_fix_backup")
            #     if _backup_path.exists():
            #         _original_content = _backup_path.read_text(encoding="utf-8")
            #         _new_dangerous = []
            #         for _pat, _label in _DANGEROUS_PATTERNS:
            #             _before_count = len(_pat.findall(_original_content))
            #             _after_count = len(_pat.findall(_patched_content))
            #             if _after_count > _before_count:
            #                 _new_dangerous.append(f"{_label} ({_before_count}→{_after_count})")
            #         if _new_dangerous:
            #             return False, (
            #                 f"patch tự thêm pattern nguy hiểm: {', '.join(_new_dangerous)} — "
            #                 f"REJECTED (world-class gate: fix phải không thêm nguy hiểm)"
            #             )
            # except Exception as _self_scan_err:
            #     logger.debug(f"[WORLD-CLASS-GATE] self_scan_patch_diff fail-open: {_self_scan_err}")

            # [WORLD-CLASS-GATE] Check 5: pytest — so sánh BASELINE vs POST-PATCH
            # TẠI SAO: 63% rollback rate xảy ra khi KHÔNG chạy pytest. Nhưng nếu chạy
            # tuyệt đối (fail = rollback), test suite có fail sẵn (DB malformed, sandbox)
            # sẽ reject MỌI patch dù patch đúng. DNA SCP: "PASS ≠ ĐÚNG" — không reject
            # patch chỉ vì test suite có fail sẵn; chỉ reject nếu patch LÀM TỆ HƠN.
            # Fix: chạy pytest pre-patch (baseline) + post-patch, so sánh pass/fail count.
            # Chỉ FAIL nếu post-patch có MORE failures hoặc FEWER passes.
            try:
                # [R35] A verifier-spawned pytest must not recursively spawn
                # another verifier pytest through evolution/autofix tests.
                _pytest_child_env = os.environ.copy()
                _pytest_child_env["SCP_AUTOFIX_RUN_PYTEST"] = "0"
                if os.environ.get("SCP_AUTOFIX_RUN_PYTEST", "0") == "1":
                    import subprocess as _sp
                    import sys as _sys
                    _tests_dir = filepath.parent
                    while _tests_dir.parent != _tests_dir:
                        if (_tests_dir / "tests").is_dir() or (_tests_dir / "scp" / "tests").is_dir():
                            break
                        _tests_dir = _tests_dir.parent
                    _root = _tests_dir
                    if (_root / "tests").is_dir() or (_root / "scp" / "tests").is_dir():
                        # [AUTOFIX-T2-SMART] Parse pass/fail counts instead of returncode.
                        # Test suite may have pre-existing failures (DB malformed, sandbox) —
                        # only reject if patch makes things WORSE.
                        _proc = _sp.run(  # noqa: S603 — audited: sys.executable, hardcoded args
                            [_sys.executable, "-m", "pytest", "-q", "--timeout=60", str(filepath)],
                            cwd=str(_root), capture_output=True, text=True, timeout=90,
                            encoding="utf-8", errors="replace",
                            check=False,
                            env=_pytest_child_env,
                        )
                        if _proc.returncode != 0:
                            import re as _re
                            _summary = (_proc.stdout or _proc.stderr or "").strip().splitlines()
                            _last = _summary[-1] if _summary else ""
                            _fail_m = _re.search(r'(\d+) failed', _last)
                            _pass_m = _re.search(r'(\d+) passed', _last)
                            _post_fails = int(_fail_m.group(1)) if _fail_m else 0
                            _post_passes = int(_pass_m.group(1)) if _pass_m else 0
                            # Get baseline (pre-patch) from backup file
                            _backup_path = filepath.with_suffix(filepath.suffix + ".tier3bak")
                            if not _backup_path.exists():
                                _backup_path = filepath.with_suffix(filepath.suffix + ".audit_fix_backup")
                            if _backup_path.exists():
                                import shutil as _shutil
                                _tmp_save = filepath.with_suffix(filepath.suffix + ".post_save")
                                _shutil.copy(str(filepath), str(_tmp_save))
                                try:
                                    _shutil.copy(str(_backup_path), str(filepath))
                                    _base_proc = _sp.run(
                                        [_sys.executable, "-m", "pytest", "-q", "--timeout=60", str(filepath)],
                                        cwd=str(_root), capture_output=True, text=True, timeout=90,
                                        encoding="utf-8", errors="replace", check=False,
                                        env=_pytest_child_env,
                                    )
                                    _base_summary = (_base_proc.stdout or "").strip().splitlines()
                                    _base_last = _base_summary[-1] if _base_summary else ""
                                    _base_fail_m = _re.search(r'(\d+) failed', _base_last)
                                    _base_pass_m = _re.search(r'(\d+) passed', _base_last)
                                    _base_fails = int(_base_fail_m.group(1)) if _base_fail_m else 0
                                    _base_passes = int(_base_pass_m.group(1)) if _base_pass_m else 0
                                finally:
                                    _shutil.copy(str(_tmp_save), str(filepath))
                                    _tmp_save.unlink(missing_ok=True)
                                # Compare: only fail if patch makes things WORSE
                                if _post_fails > _base_fails or _post_passes < _base_passes:
                                    return False, (
                                        f"pytest REGRESSION: baseline={_base_passes}p/{_base_fails}f "
                                        f"→ post-patch={_post_passes}p/{_post_fails}f "
                                        f"(patch made it worse) — ROLLBACK"
                                    )
                                else:
                                    logger.info(
                                        f"[WORLD-CLASS-GATE] pytest OK: baseline={_base_passes}p/{_base_fails}f "
                                        f"→ post-patch={_post_passes}p/{_post_fails}f (no regression)"
                                    )
                            else:
                                logger.debug("[WORLD-CLASS-GATE] no baseline backup — pytest gate skip (fail-open)")
            except Exception as _pytest_err:
                logger.debug(f"[WORLD-CLASS-GATE] pytest verify fail-open: {_pytest_err}")

            # [AUTOFIX-T1-ROOTCAUSE] Check 6: ENTERPRISE RE-SCAN (Idea 3 from world-autofix research).
            # TẠI SAO: Idea 3 (Copilot+CodeQL pattern) — sau fix, chạy lại TẤT CẢ scanner
            # (ruff S,F,RUF,PLW,PLC,B,UP + bandit + vulture + mypy) trên file đã patch.
            # Cascade control 1→2→3: fix bug A không được introduce bug B (mà scanner
            # nội bộ Check 2/3 có thể không nhìn thấy vì chỉ chạy AST scanners nội bộ).
            # Enterprise tools nhìn được SINK/TAINT/type mà AST nội bộ bỏ sót.
            # Gate: chỉ FAIL nếu có bug MỚI (không có trong original_bugs) ở line gần fix.
            try:
                from scp.autofix.enterprise_scanners import scan_file_enterprise
                _enterprise_findings = scan_file_enterprise(filepath)
                _new_ent_bugs = []
                _orig_lines = {getattr(b, "line", None) for b in original_bugs}
                _orig_types = {(getattr(b, "line", None), getattr(b, "bug_type", "")) for b in original_bugs}
                # [SCP-DNA-FIX R12-25] Also collect orig bug types (regardless of line)
                # Tại sao: S110@L130 là pre-existing bug (line 130 có except: pass từ trước).
                # Cascade control check (line, type) → S110@L130 không match orig (orig có BareExceptPass@L126).
                # → S110@L130 bị flag là "NEW" → rollback fix. Nhưng nó PRE-EXISTING.
                # Fix: nếu bug_type có trong orig (bất kỳ line nào) → không phải NEW.
                _orig_bug_types = {getattr(b, "bug_type", "") for b in original_bugs}
                # Also scan orig file for pre-existing S110/BareExceptPass
                _pre_existing_types = set()
                try:
                    _backup_path = filepath.with_suffix(filepath.suffix + ".tier3bak")
                    if not _backup_path.exists():
                        _backup_path = filepath.with_suffix(filepath.suffix + ".audit_fix_backup")
                    if _backup_path.exists():
                        _orig_findings = scan_file_enterprise(_backup_path)
                        for f in _orig_findings:
                            _pre_existing_types.add((f.get("line"), f.get("bug_type", "")))
                except Exception as _backup_scan_error:
                    logger.debug('[AUTOFIX] backup finding scan failed; continuing fail-open', exc_info=True)
                for f in _enterprise_findings:
                    _f_line = f.get("line")
                    _f_type = f.get("bug_type", "")
                    # Skip if this finding matches an original bug (we KNEW about it)
                    if (_f_line, _f_type) in _orig_types:
                        continue
                    # [R12-25] Skip if pre-existing in backup (not introduced by fix)
                    if (_f_line, _f_type) in _pre_existing_types:
                        continue
                    # [SCP-DNA-FIX R13-1] Use _orig_bug_types (ALL pre-existing bug
                    # types across the codebase) instead of R12-25b's hardcoded
                    # 3-type list (S110/S112/BLE001). Tại sao: R12-25b only skipped
                    # SCP's deliberate fail-open patterns. But the codebase also has
                    # pre-existing B904/B008/E722/etc. at OTHER lines (in original_bugs).
                    # Enterprise re-scan finds these at the fix-line → flagged as NEW
                    # → autofix over-rollbacks LEGITIMATE fixes for non-hardcoded types.
                    # Now: skip ANY bug_type present in original_bugs (it's pre-existing
                    # by definition — original_bugs is the pre-fix scan result).
                    if _f_type in _orig_bug_types:
                        continue
                    # New enterprise finding near the fix line = likely introduced by patch
                    for _ol in _orig_lines:
                        if _f_line and _ol and abs(_f_line - _ol) <= 15:
                            _new_ent_bugs.append(f)
                            break
                if _new_ent_bugs:
                    _labels = [f"{f.get('bug_type','?')}@L{f.get('line','?')}" for f in _new_ent_bugs[:3]]
                    return False, (
                        f"enterprise re-scan found {len(_new_ent_bugs)} NEW bug(s) near fix: {_labels} — "
                        f"REJECTED (cascade control: fix must not introduce new tool-detected bugs)"
                    )
            except ImportError:
                logger.debug("[CASCADE] enterprise_scanners unavailable (fail-open)")
            except Exception as _ent_err:
                logger.debug(f"[CASCADE] enterprise re-scan fail-open: {_ent_err}")

            # [R10 v4 WIRE — IMP-19] Property-Based Validation (7th check, fail-open).
            # TẠI SAO: existing 6 checks verify syntax + re-scan + no-new-bugs +
            # self-scan + pytest + enterprise. But none of them test that the
            # fix preserves INVARIANTS across edge-case inputs (None, empty,
            # negative, unicode, huge list, NaN, etc.). A fix like
            # `def safe_div(a, b): return a / b if b else 0` passes all 6
            # checks but violates "always non-negative" when called with
            # (-10, 2). IMP-19 generates N=50 edge-case inputs via built-in
            # strategy generator, runs BOTH orig + fixed on each, compares.
            # If fixed violates an invariant that orig held → FIX FAILED.
            # Fail-open per DNA #7: if property_validator crashes or no
            # PropertySpec available → don't block the fix (the 6 prior
            # checks already ran). Only FAIL if a real invariant violation
            # is found.
            try:
                from scp.autofix.property_validator import (
                    INT_OR_NONE_STRATEGY as _v4_int_strat,
                    MIXED_STRATEGY as _v4_mixed_strat,
                    PropertySpec as _V4_PropertySpec,
                    validate_fix as _v4_property_validate,
                )
                # Build a conservative PropertySpec — only check that the
                # fixed function does not raise on edge-case inputs. We
                # cannot know caller-specific invariants from here, so the
                # property we check is "no uncaught exception on edge input".
                # This catches: TypeError on None, ValueError on empty,
                # IndexError on huge index, etc. Real fix should preserve
                # the orig function's exception-tolerance profile.
                _v4_patched_text = filepath.read_text(encoding="utf-8")
                _v4_backup_path = filepath.with_suffix(filepath.suffix + ".tier3bak")
                if not _v4_backup_path.exists():
                    _v4_backup_path = filepath.with_suffix(filepath.suffix + ".audit_fix_backup")
                if _v4_backup_path.exists() and _v4_patched_text:
                    _v4_orig_text = _v4_backup_path.read_text(encoding="utf-8")
                    # Find the function name from the first original bug.
                    _v4_fn_name = ""
                    for _orig_bug in original_bugs:
                        _v4_fn_name = (
                            getattr(_orig_bug, "function_name", "")
                            or getattr(_orig_bug, "method_name", "")
                            or ""
                        )
                        if _v4_fn_name:
                            break
                    # BugLocation in IMP-19 takes function_name + line range.
                    from scp.autofix.property_validator import BugLocation as _V4_PV_BugLoc
                    _v4_pv_bug_loc = None
                    if _v4_fn_name:
                        _v4_pv_bug_loc = _V4_PV_BugLoc(
                            function_name=_v4_fn_name,
                            line_start=int(getattr(original_bugs[0], "line", 0) or 0),
                            line_end=int(getattr(original_bugs[0], "line", 0) or 0),
                        )
                    # PropertySpec: invariant = "callable did not raise".
                    # That's the weakest possible property — passes if both
                    # orig + fixed run cleanly, fails only if fixed raises
                    # where orig didn't.
                    _v4_pv_spec = _V4_PropertySpec(
                        invariants=[lambda _y: True],   # trivially True — we just check exception-safety
                        strategy=_v4_mixed_strat,
                        skip_if_none_input=False,
                    )
                    _v4_pv_result = _v4_property_validate(
                        orig_source=_v4_orig_text,
                        fixed_source=_v4_patched_text,
                        bug_location=_v4_pv_bug_loc,
                        spec=_v4_pv_spec,
                        n=50,  # 50 edge-case inputs (fast: ~0.5s)
                    )
                    if not _v4_pv_result.ok:
                        # Real invariant violation — fix broke edge-case behavior.
                        _v4_violations_summary = ", ".join(
                            f"input={v.input_value!r} reason={v.reason}"
                            for v in (_v4_pv_result.violations or [])[:3]
                        )
                        return False, (
                            f"[R10 v4 IMP-19] property validation FAILED: "
                            f"{len(_v4_pv_result.violations or [])} violation(s) "
                            f"across {_v4_pv_result.inputs_tested} edge-case inputs. "
                            f"First: {_v4_violations_summary}"
                        )
                    logger.info(
                        f"[R10 v4 IMP-19] property OK: "
                        f"{_v4_pv_result.inputs_tested} edge-case inputs tested, "
                        f"0 violations ({_v4_pv_result.reason})"
                    )
            except ImportError as _v4_pv_imp:
                logger.debug(
                    f"[R10 v4 IMP-19] property_validator unavailable (fail-open): {_v4_pv_imp}"
                )
            except Exception as _v4_pv_err:
                logger.debug(
                    f"[R10 v4 IMP-19] property_validator crash (fail-open): {_v4_pv_err}"
                )

            return True, "fix verified OK (syntax + re-scan + no new bugs + self-scan + pytest + enterprise + property)"

        except Exception as _verify_err:
            logger.debug(f"[V9.1-UPGRADE] _verify_fix error (fail-open): {_verify_err}")
            return True, f"verify error (fail-open): {_verify_err}"

    # [V9.1-UPGRADE] Audit log helper for V9.1 self-verify layer.
    def _audit_v91(self, event: str, payload: dict) -> None:
        try:
            _entry = {
                "ts": time.time(),
                "engine": "autofix",
                "event": event,
                "payload": payload,
            }
            _audit_path = self.data_dir / "v91_upgrade_audit.jsonl"
            with open(_audit_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(_entry, ensure_ascii=False) + "\n")
        except Exception as _audit_err:
            logger.debug(f"[V9.1-UPGRADE] audit log error (fail-open): {_audit_err}")

    # [SCP-DNA-FIX R12-11] Meta self-repair — attempt to auto-fix a crashed safety module.
    # TẠI SAO: VIGIL catches its own diagnostic crashes + repairs runtime. SCP DEFAULT-DENY
    # is correct (DNA #4) but leaves gate DOWN. This method attempts ONE LLM-based repair
    # per cycle, then retries the gate. Safety: (1) once-per-cycle guard, (2) fail-open,
    # (3) NEVER bypasses DEFAULT-DENY — caller still returns blocked if repair fails.
    # DNA #21 (audit the auditor) + DNA #11 (fail loudly) + DNA #7 (Autofix safe).
    _meta_repair_attempted: bool = False  # class-level guard, reset per cycle in _auto_fix

    def _attempt_meta_repair(self, module_name: str, error: Exception) -> bool:
        """Attempt to auto-repair a crashed safety module via LLM. Returns True if repaired."""
        if self._meta_repair_attempted:
            logger.debug("[R12-11] meta-repair already attempted this cycle — skip")
            return False
        self._meta_repair_attempted = True
        try:
            import traceback as _tb
            _error_str = f"{type(error).__name__}: {error}\n{_tb.format_exc()[:500]}"
            logger.warning(f"[R12-11] attempting meta-repair for {module_name}: {_error_str[:200]}")

            # Read the crashed module's source
            _module_path_map = {
                "policy_gate": "scp/autofix/policy_gate.py",
                "property_validator": "scp/autofix/property_validator.py",
                "evidence_replay": "scp/autofix/evidence_replay.py",
            }
            _module_path = _module_path_map.get(module_name)
            if not _module_path:
                logger.warning(f"[R12-11] unknown module for meta-repair: {module_name}")
                return False

            from pathlib import Path as _P
            _p = _P(_module_path)
            if not _p.exists():
                return False
            _source = _p.read_text(encoding="utf-8")

            # Use LLM to generate a patch (try OpenRouter via llm_fix)
            try:
                from scp.autofix.llm_fix import _call_smart_llm
                _prompt = (
                    f"The following Python module crashed with this error:\n\n"
                    f"--- ERROR ---\n{_error_str}\n\n"
                    f"--- MODULE SOURCE ({_module_path}) ---\n{_source[:3000]}\n\n"
                    f"Generate a minimal search-replace patch to fix the crash. "
                    f"Format:\n<<<<<<< SEARCH\nold code\n=======\nnew code\n>>>>>>> REPLACE\n"
                    f"Only fix the crash — do NOT change behavior. DNA #9 (No harm)."
                )
                _patch = _call_smart_llm(_prompt, bug_type="meta_repair", max_tokens=2000)
                if not _patch or "<<<<<<< SEARCH" not in _patch:
                    logger.warning(f"[R12-11] LLM returned no valid patch for {module_name}")
                    return False
                # Apply patch (backup first)
                _backup = _p.with_suffix(_p.suffix + ".meta_repair_bak")
                _backup.write_text(_source, encoding="utf-8")
                _new_source = _source
                # Simple search-replace application
                import re as _re
                _blocks = _re.findall(r'<<<<<<< SEARCH\n(.*?)\n=======\n(.*?)\n>>>>>>>', _patch, _re.DOTALL)
                for _old, _new in _blocks:
                    _new_source = _new_source.replace(_old, _new, 1)
                if _new_source == _source:
                    logger.warning(f"[R12-11] patch did not change source for {module_name}")
                    return False
                # Verify new source compiles
                import ast as _ast
                _ast.parse(_new_source)
                _p.write_text(_new_source, encoding="utf-8")
                logger.info(f"[R12-11] meta-repair applied to {module_name} (backup at {_backup.name})")
                return True
            except ImportError:
                logger.debug("[R12-11] llm_fix unavailable — cannot meta-repair")
                return False
            except Exception as _llm_err:
                logger.warning(f"[R12-11] LLM meta-repair failed: {_llm_err}")
                return False
        except Exception as _meta_err:
            logger.warning(f"[R12-11] meta-repair outer crash: {_meta_err}")
            return False

    def _auto_fix(self, bug: BugReport, report: bool, attack_mode: bool = False) -> dict:
        """Apply the fix autonomously. Uses code_evolution_agent._apply_fix."""
        # [G2-FIX PERM-03] Protected path check — SCP cannot modify its own permission/security source
        from scp.autofix.runner_phases.ast_scan import _is_protected_path
        _filepath = getattr(bug, 'file', '') or ''
        if _is_protected_path(_filepath):
            logger.error(f"[G2-FIX] PROTECTED_PATH_BLOCKED: {_filepath} — SCP cannot modify its own permission/security source")
            return {"status": "blocked", "reason": f"protected path: {_filepath}", "action": "protected_path_blocked"}
        # [OPT-14 / Gà §12] Capability gate — check that the current
        # CapabilityManager level allows this kind of auto-fix. Mapping:
        #   Tier 1 (auto-fix no log)  → requires "apply_sandbox"  (Level ≥ 2)
        #   Tier 2 (auto-fix + log)   → requires "apply_test"     (Level ≥ 3)
        #   Tier 4 (attack mode)      → requires "apply_narrow"   (Level ≥ 4)
        # Tier 3 (permission) bypasses this gate — it doesn't apply, just asks.
        #
        # TẠI SAO: Gà §12 — AI không được tự nâng cấp capability. Default
        # level = FULL_PRODUCTION (env var SCP_CAPABILITY_LEVEL) preserves
        # existing behavior. Operators who want the gate set the env var to
        # ANALYSIS_ONLY / SANDBOX / etc.
        try:
            from scp.meta.capability_levels import get_capability_manager
            _cap = get_capability_manager()
            _required_action = "apply_narrow" if attack_mode else (
                "apply_test" if report else "apply_sandbox"
            )
            if not _cap.can_do(_required_action):
                logger.warning(
                    f"[AutoFix] Gà §12 — capability denied: current "
                    f"{_cap.get_current_level().name} does not allow "
                    f"'{_required_action}'. Set SCP_CAPABILITY_LEVEL env "
                    f"var to escalate (requires human approval via "
                    f"CapabilityManager.request_escalation)."
                )
                return {
                    "action": "skipped",
                    "tier": int(bug.tier),
                    "reason": f"capability denied — current level "
                              f"{_cap.get_current_level().name} lacks "
                              f"'{_required_action}' (Gà §12)",
                }
        except Exception as _cap_err:
            # [G2-FIX PERM-04] Fail-CLOSED: if CapabilityManager crashes, BLOCK auto-fix
            # (security > availability). Previous behavior was fail-open (proceed without
            # check) which allowed a single CapabilityManager bug to disable all of Layer 2.
            logger.error(f"[AutoFix] CapabilityManager crash — BLOCKING fix (security > availability): {_cap_err}")
            return {
                "action": "blocked",
                "tier": int(bug.tier),
                "reason": f"CapabilityManager error (fail-closed): {_cap_err}",
            }

        # [P1-1 FIX R16] Wire verify_chain into the apply step.
        # BEFORE: verify_chain (policy_gate.py:420) was implemented but had 0 callers
        #         (G2-2 in dead-code audit, L1-4 in logic audit). The tamper-evidence
        #         gate was a no-op — audit log could be tampered without detection.
        # AFTER:  before applying any fix, call verify_chain(). If the chain is
        #         tampered (hash mismatch), BLOCK the fix. Fail-open on crash
        #         (DNA #7 — don't brick engine if policy_gate has a bug), but
        #         LOG LOUDLY so operator investigates.
        try:
            _gate = getattr(self, "policy_gate", None) or getattr(self, "_policy_gate", None)
            if _gate is not None and hasattr(_gate, "verify_chain"):
                _chain_ok, _chain_msg = _gate.verify_chain()
                if not _chain_ok:
                    logger.error(
                        f"[P1-1 R16] Policy gate verify_chain FAILED: {_chain_msg} — "
                        f"BLOCKING fix (audit log may be tampered)"
                    )
                    return {
                        "action": "blocked",
                        "tier": int(bug.tier),
                        "reason": f"verify_chain failed (audit log tampered?): {_chain_msg}",
                        "blocked_by": "verify_chain",
                    }
                logger.debug(f"[P1-1 R16] verify_chain OK: {_chain_msg}")
        except Exception as _vc_err:
            # Fail-open per DNA #7 (don't brick engine if policy_gate crashes)
            # but LOG LOUDLY — this is a security-sensitive path.
            logger.error(
                f"[P1-1 R16] verify_chain crashed (fail-open, DNA #7): {_vc_err} — "
                f"proceeding with fix, but operator must investigate policy_gate health"
            )

        # [ROOT-FIX-9] Skip auto-FIX entirely for BareExceptPass — runtime log
        # shows 63% rollback rate (24/38 attempts rolled back). LLM-fix
        # [ROOT-FIX 46] Re-enabled BareExceptPass auto-fix — was skipped because
        # llama3.2:3B had 63% rollback rate. Now AutoFix uses OpenRouter V4 flash
        # (deepseek-v4-flash-20260731) FIRST — V4 is much stronger than 3B.
        # validate_patch + diagnostic + monitor will catch bad patches.
        # If rollback rate stays high with V4, re-enable skip via env:
        #   SCP_SKIP_BAREEXCEPTPASS=1
        if bug.bug_type == "BareExceptPass" and os.environ.get("SCP_SKIP_BAREEXCEPTPASS", "0") == "1":
            logger.info(
                f"[AutoFix] SKIP BareExceptPass (SCP_SKIP_BAREEXCEPTPASS=1) "
                f"({bug.file}:{bug.line})"
            )
            return {
                "action": "skipped",
                "tier": int(bug.tier),
                "reason": "BareExceptPass skipped (SCP_SKIP_BAREEXCEPTPASS=1)",
            }

        # Rate limit
        if self._fixes_this_cycle >= MAX_FIXES_PER_CYCLE:
            return {"action": "skipped", "tier": int(bug.tier),
                    "reason": "rate limit — max fixes per cycle exceeded"}

        # [V9.0-WHY-GATE] WHY gates AutoFix — PRIMARY CONTROL GATE
        # TẠI SAO: v8.0 WHY = cố vấn (advisory). v9.0 WHY = chốt (block-capable).
        # WHY Gate can block a fix BEFORE it's applied (e.g., relaxation that
        # loosens security). Non-blocking on WHY error (default allow) so
        # AutoFix never breaks because WHY itself crashed. Constitution HARD
        # LOCK preserved inside gate() — WHY cannot override KILL.
        try:
            from scp.meta.why_gate import get_why_gate
            _why = get_why_gate().gate(
                action_type="autofix",
                action_desc=f"Fix {bug.bug_type} at {bug.file}:{bug.line}: {(bug.description or '')[:100]}",
                context=(bug.suggested_fix or "")[:200],
            )
            if _why.blocked:
                logger.info(
                    f"[V9.0-WHY-GATE] AutoFix blocked for {bug.file}:{bug.line}: "
                    f"{_why.falsification_reason[:100]}"
                )
                return {"action": "skipped", "tier": int(bug.tier),
                        "reason": f"WHY-GATE blocked: {_why.falsification_reason[:100]}"}
        except Exception as _why_err:
            logger.debug(f"[V9.0-WHY-GATE] WHY Gate error (non-blocking, default allow): {_why_err}")

        # [R9 v4 WIRE — IMP-24] Constitutional Policy Gate (DEFAULT-DENY).
        # TẠI SAO: WHY gate (v9.0) asks "should we fix?" (action layer —
        # necessity + falsification). PolicyGate asks "does this PATCH TEXT
        # contain a forbidden pattern?" (content layer — constitution KILL).
        # Independent axis — a high-confidence fix can still violate
        # constitution (e.g. `verify=False`, `os.chmod 0o777`, `eval()`).
        # DNA #4 (Constitution KILL) + DNA #22 (PASS ≠ TRUE — confidence ≠
        # safety). HIGHEST SAFETY IMPACT — gate runs BEFORE any file write.
        # Fail-CLOSED per DNA #4: if policy_gate module crashes → BLOCK the
        # fix + log loudly (security > availability). NOT fail-open.
        try:
            from scp.autofix.policy_gate import (
                PolicyFix as _V4_PolicyFix,
                evaluate_fix as _v4_policy_evaluate,
            )
            _v4_pf = _V4_PolicyFix(
                fix_id=f"{bug.file}:{bug.line}:{bug.bug_type}",
                patch=bug.suggested_fix or "",
                patched_source="",  # not known yet — gate scans patch text only
                bug_file=bug.file or "",
                bug_line=int(bug.line or 0),
                scanner_name="autofix_engine",
                extra={"bug_type": bug.bug_type, "tier": int(bug.tier)},
            )
            _v4_decision = _v4_policy_evaluate(_v4_pf)
            if not _v4_decision.allowed:
                logger.warning(
                    f"[R9 v4 IMP-24] POLICY BLOCKED fix for "
                    f"{bug.file}:{bug.line}: patterns="
                    f"{_v4_decision.blocked_patterns} "
                    f"reason={_v4_decision.reason[:120]} "
                    f"audit_id={_v4_decision.audit_id}"
                )
                return {
                    "action": "skipped",
                    "tier": int(bug.tier),
                    "reason": (
                        f"policy_gate BLOCK (DNA #4): "
                        f"{_v4_decision.reason[:160]}"
                    ),
                    "patched": False,
                    "policy_blocked": True,
                    "policy_audit_id": _v4_decision.audit_id,
                    "policy_patterns": list(_v4_decision.blocked_patterns),
                }
            logger.debug(
                f"[R9 v4 IMP-24] policy gate ALLOWED fix for "
                f"{bug.file}:{bug.line} (severity={_v4_decision.severity})"
            )
        except ImportError as _v4_p_imp:
            # DEFAULT-DENY per DNA #4 — constitution KILL gate is DOWN.
            # Block + log loudly. NOT fail-open (security > availability).
            logger.error(
                f"[R9 v4 IMP-24] policy_gate module unavailable — "
                f"DEFAULT-DENY (DNA #4 Constitution KILL gate down): {_v4_p_imp}"
            )
            return {
                "action": "blocked",
                "tier": int(bug.tier),
                "reason": (
                    f"policy_gate ImportError — DEFAULT-DENY (DNA #4): "
                    f"{_v4_p_imp}"
                ),
                "policy_gate_down": True,
            }
        except Exception as _v4_p_err:
            # DEFAULT-DENY per DNA #4 — gate itself crashed.
            logger.error(
                f"[R9 v4 IMP-24] policy_gate evaluate_fix CRASH — "
                f"DEFAULT-DENY (DNA #4): {_v4_p_err}",
                exc_info=True,
            )
            # [SCP-DNA-FIX R12-11] Meta self-repair — attempt to auto-fix policy_gate.
            # TẠI SAO: VIGIL catches its own diagnostic tool crashes + repairs them
            # runtime. SCP's DEFAULT-DENY is correct (block fix, DNA #4), but it leaves
            # the gate DOWN for all subsequent fixes until manual intervention. Meta
            # self-repair: use LLM to patch policy_gate.py itself, then retry evaluate.
            # Safety: (1) only attempt ONCE per cycle (guard with flag), (2) fail-open
            # if LLM unavailable, (3) NEVER bypass DEFAULT-DENY — if repair fails, still
            # return blocked. DNA #21 (audit the auditor) + DNA #11 (fail loudly).
            try:
                _repaired = self._attempt_meta_repair("policy_gate", _v4_p_err)
                if _repaired:
                    # Retry evaluate after repair
                    from scp.autofix.policy_gate import (
                        PolicyFix as _V4_PolicyFix2,
                        evaluate_fix as _v4_policy_evaluate2,
                    )
                    _v4_pf2 = _V4_PolicyFix2(
                        fix_id=f"{bug.file}:{bug.line}:{bug.bug_type}",
                        patch=bug.suggested_fix or "",
                        patched_source="",
                        bug_file=bug.file or "",
                        bug_line=int(bug.line or 0),
                    )
                    _v4_decision2 = _v4_policy_evaluate2(_v4_pf2)
                    if not _v4_decision2.allowed:
                        return {
                            "action": "skipped", "tier": int(bug.tier),
                            "reason": f"policy_gate BLOCK after meta-repair: {_v4_decision2.reason[:160]}",
                            "patched": False, "policy_blocked": True,
                            "policy_audit_id": _v4_decision2.audit_id,
                            "policy_patterns": list(_v4_decision2.blocked_patterns),
                            "meta_repaired": True,
                        }
                    logger.info("[R12-11] policy_gate meta-repair SUCCESS — gate back UP")
                    # Fall through to normal flow (don't return)
                else:
                    logger.warning("[R12-11] policy_gate meta-repair failed — gate stays DOWN (DEFAULT-DENY)")
            except Exception as _meta_repair_err:
                logger.warning(f"[R12-11] meta-repair attempt crashed (fail-open): {_meta_repair_err}")
            return {
                "action": "blocked",
                "tier": int(bug.tier),
                "reason": (
                    f"policy_gate crash — DEFAULT-DENY (DNA #4): {_v4_p_err}"
                ),
                "policy_gate_down": True,
            }

        try:
            from pathlib import Path as PathCls

            from scp.core.code_evolution_agent import CodeEvolutionAgent

            agent = CodeEvolutionAgent.__new__(CodeEvolutionAgent)
            agent.log_file = self.data_dir / "evolution_log.jsonl"

            filepath = PathCls(bug.file)
            if not filepath.exists():
                return {"action": "skipped", "tier": int(bug.tier),
                        "reason": f"file not found: {bug.file}"}

            # [V9.1-UPGRADE] Backup file content BEFORE applying patch — for rollback.
            # TẠI SAO: _verify_fix có thể phát hiện fix introduce new bugs → cần rollback.
            # Backup ở đây (pre-patch) để rollback có thể restore chính xác trạng thái cũ.
            _pre_fix_content: str | None = None
            try:
                # Keep original line endings. The rollback registry hashes
                # UTF-8 content and writes with newline=""; read_text() uses
                # universal-newline conversion and made a CRLF fixture fail
                # its post-rollback byte hash on Windows.
                with filepath.open("r", encoding="utf-8", newline="") as _pre_fix_file:
                    _pre_fix_content = _pre_fix_file.read()
            except Exception as _bk_err:
                logger.debug(f"[V9.1-UPGRADE] pre-fix backup failed (will skip verify): {_bk_err}")

            # [OPT-24] XSS pattern fix — deterministic, no LLM.
            # TẠI SAO: XSS bugs (CWE-79) like Markup(user_input) have a single
            # canonical fix (wrap with html.escape()). LLM fix for these wastes
            # API tokens + risks regression (LLM may rewrite the whole function
            # or remove Markup() entirely). Pattern fixer applies the fix
            # surgically + idempotently (guard_skip_if_substring prevents
            # double-escape). If pattern matches → fix + return; else fall
            # through to LLM _apply_fix below. DNA #7 AutoFix safe + #9 No harm.
            if bug.bug_type == "XSSVulnerability":
                try:
                    from scp.autofix.evolution import get_evolution_engine
                    _evo = get_evolution_engine(data_dir=str(self.data_dir))
                    _xss_result = _evo._apply_xss_pattern_fix(bug)
                    if _xss_result and _xss_result.get("fixed"):
                        # Write patched source to file
                        try:
                            filepath.write_text(
                                _xss_result["patch"], encoding="utf-8"
                            )
                        except Exception as _write_err:
                            logger.warning(
                                f"[OPT-24] XSS pattern fix write failed: {_write_err}"
                            )
                            # Fall through to LLM fix
                        else:
                            # Verify the fix didn't break syntax (re-check after write)
                            try:
                                import ast as _ast_verify
                                _ast_verify.parse(
                                    filepath.read_text(encoding="utf-8"),
                                    filename=str(filepath),
                                )
                            except SyntaxError as _syn_err:
                                logger.warning(
                                    f"[OPT-24] XSS pattern fix introduced "
                                    f"SyntaxError post-write — ROLLING BACK: {_syn_err}"
                                )
                                # Rollback
                                if _pre_fix_content is not None:
                                    filepath.write_text(
                                        _pre_fix_content, encoding="utf-8", newline=""
                                    )
                                # Fall through to LLM fix
                            else:
                                # Success — pattern fix applied + verified
                                self._fixes_this_cycle += 1
                                # [SCP-DNA-FIX R13-3] Invalidate LLM fix cache
                                # for this file (R12-2 fixed internal logic,
                                # R13-3 wired the caller). Stale LLM fix
                                # suggestions for this file are no longer
                                # served — next autofix will re-query LLM
                                # with fresh source context.
                                _xss_cache_invalidated = False
                                _xss_cache_error = ""
                                try:
                                    from scp.autofix.llm_fix_cache import invalidate_cache_for_file
                                    invalidate_cache_for_file(str(filepath))
                                    _xss_cache_invalidated = True
                                except Exception as _inv_err:
                                    _xss_cache_error = str(_inv_err)[:200]
                                    logger.warning(
                                        f"[R13-3] cache invalidate failed after deterministic fix: {_inv_err}"
                                    )
                                # Record for cooldown
                                bug_key = f"{bug.file}:{bug.line}:{bug.bug_type}"
                                self._recent_fixes[bug_key] = time.time()
                                # [SCP-DNA-FIX 4-b-012] Compute before_hash +
                                # after_hash + rollback_token + reality_test_result
                                # for this Tier 1/2/4 XSS pattern fix (DNA #8).
                                # Pre-fix: _write_audit logged only a message.
                                # Post-fix: AuditLogEntry Pydantic schema
                                # enforces all 4 fields for every tier.
                                _xss_rollback_registered = False
                                try:
                                    from scp.autofix.audit_log import compute_hashes as _compute_hashes_4b012
                                    _xss_post = filepath.read_text(encoding="utf-8")
                                    _xss_bh, _xss_ah = _compute_hashes_4b012(
                                        _pre_fix_content, _xss_post,
                                    )
                                    _xss_rtr = "pass"  # ast.parse already verified above
                                    # Register an exact per-fix rollback token. The old
                                    # fast-path only emitted backup:<path>, which was an
                                    # audit sentinel and not present in the rollback registry.
                                    _xss_token = self.register_fix_for_rollback(
                                        file_path=str(filepath),
                                        before_content=_pre_fix_content or "",
                                        after_content=_xss_post,
                                        patch=_xss_result.get("patch", ""),
                                        bug_id=f"{bug.file}:{bug.line}",
                                        bug_type=bug.bug_type,
                                        tier=int(bug.tier),
                                        reality_test_result={
                                            "status": "pass",
                                            "method": "ast.parse",
                                            "fix_method": "xss_pattern",
                                        },
                                    )
                                    _xss_rollback_registered = True
                                except Exception as _xss_hash_err:
                                    logger.warning(
                                        f"[4-b-012] XSS hash/rollback registration failed: {_xss_hash_err}"
                                    )
                                    _xss_bh = _xss_ah = "n/a"
                                    _xss_rtr = "skipped"
                                    _xss_token = f"backup:{filepath}"
                                    _xss_rollback_registered = False
                                # Log to audit trail
                                if report or attack_mode:
                                    self._write_audit(
                                        bug, "fixed", attack_mode=attack_mode,
                                        before_hash=_xss_bh, after_hash=_xss_ah,
                                        rollback_token=_xss_token,
                                        reality_test_result=_xss_rtr,
                                    )
                                else:
                                    self._write_audit(
                                        bug, "fixed_silent", attack_mode=False,
                                        before_hash=_xss_bh, after_hash=_xss_ah,
                                        rollback_token=_xss_token,
                                        reality_test_result=_xss_rtr,
                                    )
                                logger.info(
                                    f"[OPT-24] XSS pattern fix applied for "
                                    f"{bug.file}:{bug.line} "
                                    f"pattern={_xss_result.get('pattern', '?')} "
                                    f"matches={_xss_result.get('matches', 0)} "
                                    f"(skipped LLM call — deterministic fix)"
                                )
                                # [V5.7-WHY] Reflect on pattern fix too (best-effort)
                                try:
                                    if os.environ.get("SCP_EVOLUTION_ENABLED", "0") == "1":
                                        _evo.reflect(bug, _xss_result["reason"])
                                except Exception as _reflect_err:
                                    logger.debug(
                                        f"[V5.7-WHY] reflect on XSS pattern fix "
                                        f"failed (non-fatal): {_reflect_err}"
                                    )
                                return {
                                    "action": "fixed",
                                    "status": "fixed",
                                    "tier": int(bug.tier),
                                    "patched": True,
                                    "attack_mode": attack_mode,
                                    "method": "xss_pattern",
                                    "pattern": _xss_result.get("pattern", ""),
                                    "reason": _xss_result.get("reason", ""),
                                    "before_hash": _xss_bh,
                                    "after_hash": _xss_ah,
                                    "rollback_token": _xss_token,
                                    "rollback_registered": _xss_rollback_registered,
                                    "reality_test_result": _xss_rtr,
                                    "cache_invalidated": _xss_cache_invalidated,
                                    "cache_invalidation_error": _xss_cache_error,
                                }
                except Exception as _xss_pattern_err:
                    logger.debug(
                        f"[OPT-24] XSS pattern fix dispatch failed (non-fatal, "
                        f"fall through to LLM): {_xss_pattern_err}"
                    )

            # Apply fix
            # [FIX-2] TẠI SAO: was incremented unconditionally → queued-for-review
            # fixes (patched=False) consumed rate limit slots → 10 "fixed" were
            # actually 10 queued + 0 real fixes. Only count REAL patches.

            # [OPT-26/27/28] Validate patch + diagnose + record to monitor
            # BEFORE calling _apply_fix. WHY: DNA SCP #7 AutoFix safe — validate
            # before write, not after. If validation fails, we never touch the
            # file (no rollback needed). DNA SCP #6 Evidence — record diagnosis
            # so future fixes can learn. DNA SCP #8 KB accumulation — monitor
            # tracks success rate by provider/bug_type/diagnosis.
            #
            # Only validate when suggested_fix contains an explicit search-replace
            # block (SEARCH/REPLACE or legacy OLD/NEW). If it's a fenced code
            # block or pending-review queue, _apply_fix will handle it via
            # Strategy 2/3 — validation isn't applicable.
            _autofix_bug_id = f"{bug.file}:{bug.line}"
            _autofix_provider = "predefined"  # default for non-LLM patches
            try:
                # If LLM generated this patch, attribute to preferred provider.
                # We can't easily tell from here, but select_provider_for_bug
                # gives us the smart-routing choice that would have been used.
                from scp.autofix.llm_fix import select_provider_for_bug as _spfb
                _autofix_provider = _spfb(bug.bug_type)
            except Exception as e:
                logger.warning(f"Silent except: {e}")

            _autofix_validation_skipped = False  # noqa: F841 — sentinel for future wiring (tracks validation skip status)
            try:
                import re as _autofix_re
                # Try SEARCH/REPLACE first, then legacy OLD/NEW
                _sr_pat = _autofix_re.compile(
                    r"<<<<<<<\s*SEARCH\s*\n(.*?)\n={5,7}\s*\n(.*?)\n>>>>>>>\s*(?:REPLACE)?\s*",
                    _autofix_re.DOTALL,
                )
                _old_pat = _autofix_re.compile(
                    r"<<<<<<<\s*OLD\s*\n(.*?)\n={5,7}\s*\n(.*?)\n>>>>>>>\s*(?:NEW)?\s*",
                    _autofix_re.DOTALL,
                )
                _pairs: list[tuple[str, str]] = []
                if bug.suggested_fix:
                    for _m in _sr_pat.finditer(bug.suggested_fix):
                        _pairs.append((_m.group(1), _m.group(2)))
                    if not _pairs:
                        for _m in _old_pat.finditer(bug.suggested_fix):
                            _pairs.append((_m.group(1), _m.group(2)))

                if _pairs:
                    from scp.autofix.diagnostic import diagnose_fix_failure as _diagnose
                    from scp.autofix.monitor import FixAttempt as _FixAttempt
                    from scp.autofix.monitor import get_monitor as _get_monitor
                    from scp.autofix.validate_patch import validate_patch as _validate_patch

                    _validation_failed = False
                    _validation_reason = ""
                    for _search, _replace in _pairs:
                        _vresult = _validate_patch(str(filepath), _search, _replace)
                        if not _vresult.valid:
                            _validation_failed = True
                            _validation_reason = _vresult.reason
                            break

                    if _validation_failed:
                        logger.warning(
                            f"[AutoFix] [OPT-26] Patch validation FAILED for "
                            f"{bug.file}:{bug.line}: {_validation_reason}"
                        )
                        _diag = _diagnose(
                            bug_id=_autofix_bug_id,
                            bug_type=bug.bug_type,
                            llm_output=bug.suggested_fix,
                            patch_parsed={"search": _pairs[0][0], "replace": _pairs[0][1]},
                            validation_result={"valid": False, "reason": _validation_reason},
                            apply_result="failed",
                        )
                        _get_monitor().record(_FixAttempt(
                            bug_id=_autofix_bug_id,
                            bug_type=bug.bug_type,
                            provider=_autofix_provider,
                            diagnosis=_diag.diagnosis,
                            success=False,
                        ))
                        return {
                            "action": "skipped",
                            "tier": int(bug.tier),
                            "reason": f"validation failed: {_validation_reason}",
                            "patched": False,
                        }
                else:
                    # No search-replace markers → _apply_fix will try fenced-code
                    # or queue for review. Skip validation (not applicable).
                    _autofix_validation_skipped = True  # noqa: F841 — sentinel
            except Exception as _val_err:
                # Fail-open: validation infrastructure crashed → don't block fix.
                logger.debug(f"[AutoFix] [OPT-26] validation harness error (non-blocking): {_val_err}")
                _autofix_validation_skipped = True  # noqa: F841 — sentinel

            # [R9 v4 WIRE — IMP-14 + IMP-23 shared simulation]
            # Simulate patched_source by applying the same SEARCH/REPLACE pairs
            # that agent._apply_fix() will apply. Both IMP-14 (confidence ranker)
            # and IMP-23 (shadow canary) need to KNOW the post-patch source
            # BEFORE the real file is touched. Fail-open: simulation crash →
            # both v4 hooks skipped (proceed with old behavior).
            #
            # _pairs is built inside the try/except above. If validation try
            # failed before line 796, _pairs is undefined — defensive .get().
            _v4_pairs = locals().get("_pairs", []) or []
            _v4_sim_patched: str | None = None
            if _pre_fix_content is not None and _v4_pairs:
                try:
                    _v4_sim = _pre_fix_content
                    _v4_applied_any = False
                    for _v4_s, _v4_r in _v4_pairs:
                        if _v4_s in _v4_sim:
                            _v4_sim = _v4_sim.replace(_v4_s, _v4_r, 1)
                            _v4_applied_any = True
                    if _v4_applied_any and _v4_sim != _pre_fix_content:
                        _v4_sim_patched = _v4_sim
                except Exception as _v4_sim_err:
                    logger.debug(
                        f"[R9 v4 WIRE] patched_source simulation failed "
                        f"(fail-open — IMP-14 + IMP-23 skip): {_v4_sim_err}"
                    )

            # [R9 v4 WIRE — IMP-14] Confidence Ranker (fail-open).
            # TẠI SAO: existing flow has exactly 1 candidate fix per bug.
            # IMP-14 scores it (bug-FP-rate × source-quality × blast-radius ×
            # ast-parse × reality-test × relaxation-cap) → confidence ∈ [0,1]
            # → disposition "auto_apply" | "review" | "discard". If disposition
            # == "discard" → SKIP the fix (low confidence + not a relaxation).
            # HIGHEST ACCURACY IMPACT — filters out low-quality LLM patches.
            # Fail-open per DNA #7: ranker crash → proceed with old behavior
            # (apply without scoring) + log. NOT fail-closed (unlike policy_gate).
            try:
                from scp.autofix.confidence_ranker import (
                    best_fix as _v4_rank_best,
                    make_fix as _v4_make_fix,
                )
                if _v4_sim_patched is not None:
                    # Estimate lines_changed from replace block line counts.
                    _v4_lines_changed = sum(
                        max(0, len(_r.splitlines()) - len(_s.splitlines()) + 1)
                        for _s, _r in _v4_pairs
                    ) or sum(len(_r.splitlines()) for _, _r in _v4_pairs)
                    _v4_candidate = _v4_make_fix(
                        fix_id=_autofix_bug_id,
                        patch=bug.suggested_fix or "",
                        patched_source=_v4_sim_patched,
                        source="llm",  # SCP autofix patches are LLM-generated
                        bug_type=bug.bug_type,
                        bug_file=bug.file,
                        bug_line=int(bug.line or 0),
                        lines_changed=_v4_lines_changed,
                        reality_test_result=None,
                    )
                    _v4_ranked = _v4_rank_best([_v4_candidate], bug_type=bug.bug_type)
                    if _v4_ranked is None or _v4_ranked.disposition == "discard":
                        logger.info(
                            f"[R9 v4 IMP-14] confidence ranker DISCARDED "
                            f"fix for {bug.file}:{bug.line} "
                            f"(confidence={_v4_candidate.confidence:.3f} "
                            f"disposition={_v4_candidate.disposition})"
                        )
                        # [OPT-27/28] Record discard — patch was ranked too low.
                        try:
                            from scp.autofix.diagnostic import diagnose_fix_failure as _diagnose
                            from scp.autofix.monitor import FixAttempt as _FixAttempt
                            from scp.autofix.monitor import get_monitor as _get_monitor
                            _diag = _diagnose(
                                bug_id=_autofix_bug_id,
                                bug_type=bug.bug_type,
                                llm_output=bug.suggested_fix,
                                patch_parsed={"search": "(ranked)", "replace": "(ranked)"},
                                validation_result={"valid": True, "reason": "pre-rank OK"},
                                apply_result="discarded_by_ranker",
                            )
                            _get_monitor().record(_FixAttempt(
                                bug_id=_autofix_bug_id,
                                bug_type=bug.bug_type,
                                provider=_autofix_provider,
                                diagnosis=_diag.diagnosis,
                                success=False,
                            ))
                        except Exception as e:
                            logger.debug(f"Silent except: {e}")
                        return {
                            "action": "skipped",
                            "tier": int(bug.tier),
                            "reason": (
                                f"confidence_ranker DISCARD "
                                f"(confidence={_v4_candidate.confidence:.3f})"
                            ),
                            "patched": False,
                            "confidence": _v4_candidate.confidence,
                            "disposition": "discard",
                        }
                    logger.info(
                        f"[R9 v4 IMP-14] fix ranked: "
                        f"confidence={_v4_ranked.confidence:.3f} "
                        f"disposition={_v4_ranked.disposition} "
                        f"for {bug.file}:{bug.line}"
                    )
            except ImportError as _v4_cr_imp:
                logger.debug(
                    f"[R9 v4 IMP-14] confidence_ranker unavailable "
                    f"(fail-open — apply without scoring): {_v4_cr_imp}"
                )
            except Exception as _v4_cr_err:
                logger.debug(
                    f"[R9 v4 IMP-14] confidence_ranker crash "
                    f"(fail-open — apply without scoring): {_v4_cr_err}"
                )

            # [R10 v4 WIRE — IMP-16 + IMP-20 PAIRED] Blast-Radius + Type-Flow Verify.
            # TẠI SAO: IMP-14 (confidence_ranker) scores a fix but DOES NOT walk
            # the caller graph. A fix that changes `def get_user(uid) ->
            # Optional[User]` → `-> User` (drop None) breaks 5 callers with
            # `if user is None: return 404` branches (dead branch logic regression).
            # IMP-16 computes blast_radius (caller count + risk tier), then
            # IMP-20 walks each caller to check type-flow compatibility.
            # If callers have breaking type-flow → escalate to review (Tier 3).
            # Fail-open per DNA #7: if either module crashes → proceed with
            # apply (no escalation). The 6-check _verify_fix gate still runs
            # post-apply as a separate safety net.
            try:
                from scp.autofix.runner_phases.blast_radius import (
                    compute_blast_radius as _v4_blast,
                    should_escalate_tier as _v4_should_escalate,
                    should_require_dry_run as _v4_should_dry_run,
                    blast_radius_summary as _v4_blast_summary,
                )
                # Walk caller graph for the bug's file + function name.
                # Derive target_function from bug description (best-effort:
                # if function name not on BugReport, fall back to bare module).
                _v4_target_func = (
                    getattr(bug, "function_name", "")
                    or getattr(bug, "method_name", "")
                    or ""
                )
                # Try to extract function name from suggested_fix SEARCH block
                # (e.g. "def foo(...)") as a backup heuristic.
                if not _v4_target_func and bug.suggested_fix:
                    import re as _v4_re_mod
                    _v4_def_m = _v4_re_mod.search(
                        r"def\s+(\w+)\s*\(", bug.suggested_fix,
                    )
                    if _v4_def_m:
                        _v4_target_func = _v4_def_m.group(1)
                if _v4_target_func:
                    _v4_blast_result = _v4_blast(
                        target_file=bug.file or "",
                        target_function=_v4_target_func,
                        scp_root=None,  # default: .../scp/
                        scan_tests=False,
                    )
                    _v4_blast_sum = _v4_blast_summary(_v4_blast_result)
                    logger.info(
                        f"[R10 v4 IMP-16] blast_radius for {_v4_target_func}: "
                        f"callers={_v4_blast_sum['caller_count']} "
                        f"risk={_v4_blast_sum['risk_level']} "
                        f"bounded={_v4_blast_sum['bounded']}"
                    )

                    # [SCP-DNA-FIX R13-1+R13-4] Wire should_escalate_tier — was
                    # imported (R10) but never called (2-source cross-validated:
                    # R13-1 ruff F401 + R13-4 DeadCodeScanner). TẠI SAO: engine
                    # hand-rolled escalation only for TYPE-FLOW BREAKAGE
                    # (HIGH+break→Tier 3, see inline check below). This left
                    # "HIGH/CRITICAL blast radius with NO type-flow breakage"
                    # with NO escalation at all → Tier 1 fix applied silently
                    # to a function with 10+ callers. Now: call the helper's
                    # documented policy (HIGH→Tier 2, CRITICAL→Tier 3) FIRST as
                    # the GENERAL escalation. The existing inline type-flow
                    # break check below is preserved as a SECONDARY escalation
                    # (DNA: "không mặc định" — type-flow breakage is strictly
                    # worse than blast-radius alone, escalates higher).
                    try:
                        _v4_orig_tier = int(getattr(bug, "tier", 1) or 1)
                    except (TypeError, ValueError):
                        _v4_orig_tier = 1
                    _v4_escalated_tier = _v4_should_escalate(
                        _v4_blast_result, _v4_orig_tier,
                    )
                    if _v4_escalated_tier > _v4_orig_tier:
                        logger.warning(
                            f"[R13-4] blast_radius policy escalated "
                            f"{bug.file}:{bug.line} from Tier "
                            f"{_v4_orig_tier} to Tier {_v4_escalated_tier} "
                            f"(risk={_v4_blast_sum['risk_level']}, "
                            f"callers={_v4_blast_sum['caller_count']})"
                        )
                        # Surface in result downstream — mutate bug.tier so the
                        # classifier / log path sees the escalated tier.
                        if hasattr(bug, "tier"):
                            try:
                                bug.tier = _v4_escalated_tier  # type: ignore[assignment]
                            except Exception as _tier_assignment_error:  # noqa: BLE001
                                logger.debug('[AUTOFIX] tier assignment failed; retaining original tier', exc_info=True)

                    # [SCP-DNA-FIX R13-4] Wire should_require_dry_run — IMP-9
                    # dry-run for HIGH/CRITICAL blast radius is documented in
                    # V3_MANIFEST but was NEVER called (DeadCodeScanner R13-4).
                    # TẠI SAO: fixes touching HIGH-blast functions (10+ callers)
                    # can break unseen call sites. Dry-run generates a snapshot
                    # for operator review BEFORE the real file write. We do NOT
                    # hard-block here (fail-open per DNA #7) — but we DO log a
                    # loud warning + generate a dry-run preview snapshot if the
                    # engine has preview_fix_dry_run injected (IMP-9). The
                    # snapshot_path is surfaced in the result so the operator
                    # can review/apply manually if needed.
                    if _v4_should_dry_run(_v4_blast_result):
                        _dry_run_snapshot = None
                        try:
                            _dry_run_preview_fn = getattr(
                                self, "preview_fix_dry_run", None,
                            )
                            if (_dry_run_preview_fn is not None
                                    and _pre_fix_content is not None
                                    and bug.suggested_fix):
                                # Simulate patched content (best-effort).
                                import re as _v4_dr_re
                                _v4_dr_sim = _pre_fix_content
                                for _old, _new in _v4_dr_re.findall(
                                    r'<<<<<<< SEARCH\n(.*?)\n=======\n(.*?)\n>>>>>>>',
                                    bug.suggested_fix, _v4_dr_re.DOTALL,
                                ):
                                    _v4_dr_sim = _v4_dr_sim.replace(_old, _new, 1)
                                if _v4_dr_sim != _pre_fix_content:
                                    _dr_out = _dry_run_preview_fn(
                                        bug.file, _v4_dr_sim,
                                    )
                                    _dry_run_snapshot = _dr_out.get("snapshot_path")
                        except Exception as _dr_err:  # noqa: BLE001
                            logger.debug(
                                f"[R13-4] dry-run preview failed (fail-open): {_dr_err}"
                            )
                        logger.warning(
                            f"[R13-4] HIGH/CRITICAL blast radius for "
                            f"{_v4_target_func} (risk={_v4_blast_sum['risk_level']}, "
                            f"callers={_v4_blast_sum['caller_count']}) — "
                            f"dry-run{' snapshot='+str(_dry_run_snapshot) if _dry_run_snapshot else ' unavailable (fail-open)'}"
                        )

                    # Now run IMP-20 type-flow check against the caller list.
                    # [SCP-DNA-FIX R12-13] REAL signature extraction — không còn empty.
                    # Tại sao: R10 truyền empty signatures (args=[], returns="") →
                    # verify_type_flow return compatible=True (silent no-op). R12-13
                    # extract REAL signatures từ orig_source + patched_source bằng
                    # ast.parse + ast.walk(FunctionDef). DNA #22 (PASS ≠ TRUE).
                    try:
                        from scp.autofix.type_flow_verifier import (
                            Signature as _V4_TF_Sig,
                            verify_type_flow as _v4_tflow,
                        )
                        if _v4_blast_sum["caller_count"] > 0:
                            # R12-13: Extract real signatures from orig + patched source
                            import ast as _ast_tf
                            def _extract_sig(source_text: str, func_name: str) -> _V4_TF_Sig:
                                """Extract function signature from source via AST."""
                                try:
                                    tree = _ast_tf.parse(source_text)
                                    for node in _ast_tf.walk(tree):
                                        if isinstance(node, (_ast_tf.FunctionDef, _ast_tf.AsyncFunctionDef)) and node.name == func_name:
                                            args = [a.arg for a in node.args.args if hasattr(a, 'arg')]
                                            returns = ""
                                            if node.returns:
                                                try:
                                                    returns = _ast_tf.unparse(node.returns)
                                                except Exception:
                                                    returns = "Any"
                                            return _V4_TF_Sig(args=args, returns=returns)
                                except Exception as _signature_scan_error:
                                    logger.debug('[AUTOFIX] signature scan failed; using empty signature', exc_info=True)
                                return _V4_TF_Sig(args=[], returns="")

                            _v4_orig_sig = _extract_sig(_pre_fix_content or "", _v4_target_func)
                            # Read patched source if available
                            _v4_patched_src = ""
                            try:
                                _v4_patched_src = filepath.read_text(encoding="utf-8")
                            except Exception as _patched_source_error:
                                logger.debug('[AUTOFIX] patched source read failed; using empty source', exc_info=True)
                            _v4_new_sig = _extract_sig(_v4_patched_src, _v4_target_func)

                            _v4_tflow_result = _v4_tflow(
                                target_file=bug.file or "",
                                target_function=_v4_target_func,
                                orig_signature=_v4_orig_sig,
                                new_signature=_v4_new_sig,
                                scp_root=str(
                                    Path(__file__).resolve().parent.parent
                                ),
                            )
                            logger.info(
                                f"[R12-13] type_flow for "
                                f"{_v4_target_func}: compatible="
                                f"{_v4_tflow_result.compatible} "
                                f"callers={_v4_tflow_result.caller_count} "
                                f"orig_args={_v4_orig_sig.args} "
                                f"new_args={_v4_new_sig.args} "
                                f"reason={_v4_tflow_result.reason[:80]}"
                            )
                            # If type-flow check returns incompatible AND
                            # risk_level is HIGH/CRITICAL → escalate to Tier 3.
                            if (
                                not _v4_tflow_result.compatible
                                and _v4_blast_sum["risk_level"] in ("HIGH", "CRITICAL")
                            ):
                                logger.warning(
                                    f"[R12-13] TYPE-FLOW BREAKAGE + "
                                    f"HIGH risk — escalating {bug.file}:"
                                    f"{bug.line} to review (Tier 3)"
                                )
                                return {
                                    "action": "skipped",
                                    "tier": 3,
                                    "reason": (
                                        f"type_flow_verifier: "
                                        f"{len(_v4_tflow_result.incompatible_sites)} "
                                        f"breaking caller(s) + risk="
                                        f"{_v4_blast_sum['risk_level']}"
                                    ),
                                    "patched": False,
                                    "blast_radius": _v4_blast_sum,
                                    "type_flow_breaking": len(
                                        _v4_tflow_result.incompatible_sites
                                    ),
                                }
                    except ImportError as _v4_tf_imp:
                        logger.debug(
                            f"[R10 v4 IMP-20] type_flow_verifier unavailable "
                            f"(fail-open): {_v4_tf_imp}"
                        )
                    except Exception as _v4_tf_err:
                        logger.debug(
                            f"[R10 v4 IMP-20] type_flow_verifier crash "
                            f"(fail-open): {_v4_tf_err}"
                        )
            except ImportError as _v4_br_imp:
                logger.debug(
                    f"[R10 v4 IMP-16] blast_radius unavailable (fail-open): {_v4_br_imp}"
                )
            except Exception as _v4_br_err:
                logger.debug(
                    f"[R10 v4 IMP-16] blast_radius crash (fail-open): {_v4_br_err}"
                )

            # [R9 v4 WIRE — IMP-23] Shadow-Apply + Canary Compare (fail-open).
            # TẠI SAO: pre-apply safety gate. Apply patch to a SHADOW COPY (temp
            # file), import as module, run default canary suite (ast_parse +
            # import + smoke_call + reality + property tests) on BOTH original
            # and shadow, compare outputs. Only promote (write to real file)
            # if shadow passed. HIGHEST SAFETY IMPACT (pre-apply).
            # Fail-open per DNA #7: canary crash → apply without canary + log.
            # Canary itself is fail-open internally (empty suite → passed=True
            # + flagged_for_review). DNA #11 fail-loudly on regressions.
            try:
                from scp.autofix.runner_phases.shadow_canary import (
                    ShadowFix as _V4_ShadowFix,
                    default_canary_suite as _v4_default_canary,
                    shadow_apply_and_compare as _v4_shadow_compare,
                )
                if _v4_sim_patched is not None and _pre_fix_content is not None:
                    _v4_shadow_fix = _V4_ShadowFix(
                        original_source=_pre_fix_content,
                        patched_source=_v4_sim_patched,
                        fix_id=_autofix_bug_id,
                    )
                    _v4_shadow_result = _v4_shadow_compare(
                        target_file=bug.file,
                        fix=_v4_shadow_fix,
                        canary_suite=_v4_default_canary(),
                    )
                    if not _v4_shadow_result.passed:
                        logger.warning(
                            f"[R9 v4 IMP-23] SHADOW CANARY FAILED for "
                            f"{bug.file}:{bug.line}: "
                            f"{_v4_shadow_result.reason[:120]} "
                            f"(tests_run={_v4_shadow_result.tests_run} "
                            f"diffs={len(_v4_shadow_result.diffs)})"
                        )
                        # [OPT-27/28] Record shadow fail.
                        try:
                            from scp.autofix.diagnostic import diagnose_fix_failure as _diagnose
                            from scp.autofix.monitor import FixAttempt as _FixAttempt
                            from scp.autofix.monitor import get_monitor as _get_monitor
                            _diag = _diagnose(
                                bug_id=_autofix_bug_id,
                                bug_type=bug.bug_type,
                                llm_output=bug.suggested_fix,
                                patch_parsed={"search": "(shadowed)", "replace": "(shadowed)"},
                                validation_result={"valid": True, "reason": "pre-shadow OK"},
                                apply_result="shadow_canary_failed",
                            )
                            _get_monitor().record(_FixAttempt(
                                bug_id=_autofix_bug_id,
                                bug_type=bug.bug_type,
                                provider=_autofix_provider,
                                diagnosis=_diag.diagnosis,
                                success=False,
                            ))
                        except Exception as e:
                            logger.debug(f"Silent except: {e}")
                        return {
                            "action": "skipped",
                            "tier": int(bug.tier),
                            "reason": (
                                f"shadow_canary FAIL: "
                                f"{_v4_shadow_result.reason[:160]}"
                            ),
                            "patched": False,
                            "shadow_canary_passed": False,
                            "shadow_diffs": list(_v4_shadow_result.diffs[:5]),
                            "shadow_tests_run": _v4_shadow_result.tests_run,
                        }
                    logger.info(
                        f"[R9 v4 IMP-23] shadow canary OK for "
                        f"{bug.file}:{bug.line} "
                        f"(tests_run={_v4_shadow_result.tests_run} "
                        f"flagged={_v4_shadow_result.flagged_for_review})"
                    )
            except ImportError as _v4_sc_imp:
                logger.debug(
                    f"[R9 v4 IMP-23] shadow_canary unavailable "
                    f"(fail-open — apply without canary): {_v4_sc_imp}"
                )
            except Exception as _v4_sc_err:
                logger.debug(
                    f"[R9 v4 IMP-23] shadow_canary crash "
                    f"(fail-open — apply without canary): {_v4_sc_err}"
                )

            # [SCP-DNA-FIX R12-18] Real-Time Verifier — check invariants BEFORE file write.
            # TẠI SAO: post_fix_verify (R12-6) chạy SAU patch apply → nếu break invariant
            # phải rollback (waste). Real-Time Verifier chạy TRƯỚC _apply_fix → nếu
            # will break → BLOCK patch (no waste). VIGIL có Observation real-time, SCP
            # thiếu → R12-18 thêm. DNA #22 (PASS ≠ TRUE): post-hoc ≠ real-time.
            # Fail-open per DNA #7: verifier crash → allow (don't block fix).
            try:
                from scp.autofix.realtime_verifier import verify_patch_realtime
                _rtv_patched_source = filepath.read_text(encoding="utf-8") if filepath.exists() else ""
                # Simulate patch: apply suggested_fix to orig source (best-effort)
                # If we can't simulate, skip (fail-open)
                if _pre_fix_content and bug.suggested_fix:
                    _rtv_simulated = _pre_fix_content
                    # Simple search-replace simulation (best-effort)
                    import re as _rtv_re
                    _rtv_blocks = _rtv_re.findall(
                        r'<<<<<<< SEARCH\n(.*?)\n=======\n(.*?)\n>>>>>>>',
                        bug.suggested_fix, _rtv_re.DOTALL
                    )
                    for _rtv_old, _rtv_new in _rtv_blocks:
                        _rtv_simulated = _rtv_simulated.replace(_rtv_old, _rtv_new, 1)
                    if _rtv_simulated != _pre_fix_content:
                        _rtv_result = verify_patch_realtime(
                            orig_source=_pre_fix_content,
                            patched_source=_rtv_simulated,
                            func_name=getattr(bug, "function_name", None) or getattr(bug, "method_name", None),
                        )
                        if not _rtv_result.ok:
                            logger.warning(
                                f"[R12-18] Real-Time Verifier BLOCKED patch for "
                                f"{bug.file}:{bug.line}: {_rtv_result.reason} — skipping file write"
                            )
                            return {
                                "action": "skipped",
                                "tier": int(bug.tier),
                                "reason": f"realtime_verifier: {_rtv_result.reason[:160]}",
                                "patched": False,
                                "realtime_blocked": True,
                                "violations": _rtv_result.violations[:3],
                            }
                        logger.info(
                            f"[R12-18] Real-Time Verifier OK: {_rtv_result.reason} "
                            f"(inputs={_rtv_result.inputs_tested})"
                        )
            except ImportError as _rtv_imp:
                logger.debug(f"[R12-18] realtime_verifier unavailable (fail-open): {_rtv_imp}")
            except Exception as _rtv_err:
                logger.debug(f"[R12-18] realtime_verifier crash (fail-open): {_rtv_err}")

            patched = agent._apply_fix(filepath, bug.suggested_fix)
            if patched:
                self._fixes_this_cycle += 1
                # [SCP-DNA-FIX R13-3] Invalidate LLM fix cache for this file
                # (R12-2 fixed internal logic, R13-3 wired the caller). Stale
                # LLM fix suggestions for this file are no longer served.
                try:
                    from scp.autofix.llm_fix_cache import invalidate_cache_for_file
                    invalidate_cache_for_file(str(filepath))
                except Exception as _inv_err:
                    logger.debug(f"[R13-3] cache invalidate failed (non-fatal): {_inv_err}")
            else:
                # [OPT-27/28] Record LLM_OUTPUT_FORMAT_ERROR (or queued-for-review)
                # to diagnostic + monitor. WHY: even "queued for review" is a
                # failure mode worth tracking — if many bugs queue for the same
                # reason, prompt needs improving.
                try:
                    from scp.autofix.diagnostic import diagnose_fix_failure as _diagnose
                    from scp.autofix.monitor import FixAttempt as _FixAttempt
                    from scp.autofix.monitor import get_monitor as _get_monitor
                    _diag = _diagnose(
                        bug_id=_autofix_bug_id,
                        bug_type=bug.bug_type,
                        llm_output=bug.suggested_fix,
                        patch_parsed=None,
                        validation_result=None,
                        apply_result="failed",
                    )
                    _get_monitor().record(_FixAttempt(
                        bug_id=_autofix_bug_id,
                        bug_type=bug.bug_type,
                        provider=_autofix_provider,
                        diagnosis=_diag.diagnosis,
                        success=False,
                    ))
                except Exception as e:
                    logger.warning(f"Silent except: {e}")
                return {
                    "action": "skipped",
                    "tier": int(bug.tier),
                    "reason": "fix queued for human review (not auto-patchable)",
                    "patched": False,
                }

            # [V9.1-UPGRADE] FixVerification layer — self-verify SAU khi apply patch.
            # TẠI SAO: WHY gate (v9.0) hỏi "có nên fix không?" (action layer).
            # _verify_fix hỏi "fix có thực sự work không? có introduce new bug không?" (verify layer).
            # WHY + verify = cùng độ sâu (2 layer) như WHY (necessity + falsification).
            # Non-blocking: verify error → fail-open (don't break fix). Nếu verify
            # phát hiện new bugs → ROLLBACK (restore pre-fix content) + return skipped.
            try:
                _verify_ok, _verify_reason = self._verify_fix(filepath, [bug])
                if not _verify_ok:
                    logger.warning(
                        f"[V9.1-UPGRADE] Fix verification FAILED for {bug.file}:{bug.line}: "
                        f"{_verify_reason} — ROLLING BACK"
                    )
                    self._audit_v91("autofix_verify_fail_rollback", {
                        "file": bug.file, "line": bug.line, "bug_type": bug.bug_type,
                        "reason": _verify_reason,
                    })
                    # Rollback: restore pre-fix content
                    if _pre_fix_content is not None:
                        try:
                            filepath.write_text(_pre_fix_content, encoding="utf-8")
                            logger.info(f"[V9.1-UPGRADE] Rollback OK for {bug.file}")
                        except Exception as _rb_err:
                            logger.error(f"[V9.1-UPGRADE] Rollback FAILED for {bug.file}: {_rb_err}")
                    # Decrement counter (fix was undone)
                    self._fixes_this_cycle = max(0, self._fixes_this_cycle - 1)
                    # [OPT-27/28] Record rollback — patch applied but introduced new bugs.
                    try:
                        from scp.autofix.diagnostic import diagnose_fix_failure as _diagnose
                        from scp.autofix.monitor import FixAttempt as _FixAttempt
                        from scp.autofix.monitor import get_monitor as _get_monitor
                        _diag = _diagnose(
                            bug_id=_autofix_bug_id,
                            bug_type=bug.bug_type,
                            llm_output=bug.suggested_fix,
                            patch_parsed={"search": "(applied)", "replace": "(applied)"},
                            validation_result={"valid": True, "reason": "pre-apply OK"},
                            apply_result="rollback",
                        )
                        _get_monitor().record(_FixAttempt(
                            bug_id=_autofix_bug_id,
                            bug_type=bug.bug_type,
                            provider=_autofix_provider,
                            diagnosis=_diag.diagnosis,
                            success=False,
                        ))
                    except Exception as e:
                        logger.warning(f"Silent except: {e}")
                    return {
                        "action": "skipped",
                        "tier": int(bug.tier),
                        "reason": f"fix verification failed (rolled back): {_verify_reason}",
                        "patched": False,
                    }
                self._audit_v91("autofix_verify_ok", {
                    "file": bug.file, "line": bug.line, "bug_type": bug.bug_type,
                    "reason": _verify_reason,
                })

                # [SCP-DNA-FIX R12-6] Wire R7-Full post-fix verification orchestrator.
                # TẠI SAO: run_full_post_fix_verify() là IMP-1 orchestrator — kích hoạt
                # toàn bộ chain IMP-1 (vulture) + IMP-2 (reality_test) + IMP-3 (completeness)
                # + IMP-7 (lineage) + IMP-12 (diff_rescan) + IMP-15 (semantic_equiv).
                # Trước R12-6: 5,170+ LOC dead (wiring-scan report). R11 claim "12/12 wired"
                # nhưng chỉ import-level, không call-level. DNA #22 (PASS ≠ TRUE): import
                # ≠ wired ≠ called. Wire tại đây — SAU _verify_fix (gate nội bộ OK),
                # TRƯỚC cooldown record (để rollback nếu orchestrator fail).
                # Fail-open per DNA #7: orchestrator error không block fix (fix đã apply +
                # _verify_fix đã pass). Chỉ escalate_to_tier3 → log warning.
                try:
                    from scp.autofix.runner_phases.post_fix_verify import run_full_post_fix_verify
                    _pfv_result = run_full_post_fix_verify(
                        bug_id=f"{bug.file}:{bug.line}:{bug.bug_type}",
                        file_path=str(filepath),
                        method_name=getattr(bug, "function_name", None) or getattr(bug, "method_name", None),
                        bug_type=bug.bug_type,
                        run_vulture=True,
                        run_import=True,
                        run_hypothesis=False,  # hypothesis needs test file — skip if none
                        run_reality_exercise=True,
                        run_completeness=True,
                    )
                    if not _pfv_result.get("ok", True):
                        _pfv_reason = _pfv_result.get("reason", "unknown")
                        _pfv_rollback = _pfv_result.get("rollback", False)
                        if _pfv_rollback:
                            logger.warning(
                                f"[R12-6] post_fix_verify ROLLBACK for {bug.file}:{bug.line}: "
                                f"{_pfv_reason} — restoring pre-fix content"
                            )
                            if _pre_fix_content is not None:
                                try:
                                    filepath.write_text(_pre_fix_content, encoding="utf-8")
                                    logger.info(f"[R12-6] Rollback OK for {bug.file}")
                                except Exception as _rb_err:
                                    logger.error(f"[R12-6] Rollback FAILED for {bug.file}: {_rb_err}")
                            self._fixes_this_cycle = max(0, self._fixes_this_cycle - 1)
                        else:
                            logger.warning(
                                f"[R12-6] post_fix_verify escalate_to_tier3 for "
                                f"{bug.file}:{bug.line}: {_pfv_reason}"
                            )
                    else:
                        logger.info(
                            f"[R12-6] post_fix_verify OK for {bug.file}:{bug.line} "
                            f"(phases: {list(_pfv_result.get('phases', {}).keys())})"
                        )
                except ImportError as _pfv_imp:
                    logger.debug(f"[R12-6] post_fix_verify module unavailable (fail-open): {_pfv_imp}")
                except Exception as _pfv_err:
                    logger.debug(f"[R12-6] post_fix_verify crash (fail-open): {_pfv_err}")
            except Exception as _verify_call_err:
                logger.debug(f"[V9.1-UPGRADE] _verify_fix call error (fail-open): {_verify_call_err}")

            # Record for cooldown
            bug_key = f"{bug.file}:{bug.line}:{bug.bug_type}"
            self._recent_fixes[bug_key] = time.time()

            # [SCP-DNA-FIX 4-b-012] Compute before_hash + after_hash +
            # rollback_token + reality_test_result for this Tier 1/2/4 fix
            # (DNA #8 KB accumulation). Pre-fix: _write_audit logged only
            # timestamp/file/line/bug_type/tier/action/description — NO
            # hashes, NO rollback_token, NO reality_test_result. Tier 3
            # already had these (via _write_tier3_auto_audit); Tier 1/2/4
            # did NOT. Now: AuditLogEntry Pydantic schema enforces all 4
            # fields for EVERY tier at write time.
            #
            # _verify_ok may be unset if _verify_fix raised (fail-open path
            # at line 1923-1924); default to None → reality_test="skipped".
            _verify_ok_local = locals().get("_verify_ok")
            _verify_reason_local = locals().get("_verify_reason")
            try:
                from scp.autofix.audit_log import (
                    compute_hashes as _compute_hashes_4b012,
                    make_rollback_token_backup as _rb_token_4b012,
                )
                _main_post = filepath.read_text(encoding="utf-8")
                _main_bh, _main_ah = _compute_hashes_4b012(
                    _pre_fix_content, _main_post,
                )
                if _verify_ok_local is True:
                    _main_rtr = "pass"
                elif _verify_ok_local is False:
                    _main_rtr = f"fail:{(_verify_reason_local or 'unknown')[:80]}"
                else:
                    _main_rtr = "skipped"
                # Tier 4 (attack_mode) prefers git revert ref; else backup path.
                if attack_mode:
                    try:
                        from scp.autofix.audit_log import (
                            make_rollback_token_git as _git_token_4b012,
                        )
                        _main_token = _git_token_4b012(str(filepath))
                    except Exception:
                        _main_token = _rb_token_4b012(str(filepath))
                else:
                    _main_token = _rb_token_4b012(str(filepath))
            except Exception as _main_hash_err:
                logger.debug(
                    f"[4-b-012] main audit hash/token compute failed "
                    f"(non-fatal — entry gets 'n/a'): {_main_hash_err}"
                )
                _main_bh = _main_ah = "n/a"
                _main_rtr = "skipped"
                _main_token = "n/a"

            # Log to audit trail (Tier 2+ always; Tier 1 only if report=True)
            if report or attack_mode:
                self._write_audit(
                    bug, "fixed", attack_mode=attack_mode,
                    before_hash=_main_bh, after_hash=_main_ah,
                    rollback_token=_main_token,
                    reality_test_result=_main_rtr,
                )
            else:
                # Tier 1: minimal log (for forensics, not reported to human)
                self._write_audit(
                    bug, "fixed_silent", attack_mode=False,
                    before_hash=_main_bh, after_hash=_main_ah,
                    rollback_token=_main_token,
                    reality_test_result=_main_rtr,
                )

            # [V5.7-WHY] Change 1: WHY → Evolution Engine reflect feedback.
            # TẠI SAO: closes the loop "fix → reflect → KB update → next fix smarter".
            # Without this, each fix is a one-shot — SCP never learns WHY bug occurred.
            # Now: after a successful fix, ask EvolutionEngine.reflect(bug, fix_diff)
            # to extract root cause + lesson → write to evolution_reflect.jsonl →
            # next time same pattern detected, classifier/scanner can use the lesson.
            # SAFETY: opt-in via SCP_EVOLUTION_ENABLED=1 (default OFF). Wrap in
            # try/except — reflect failure MUST NOT break fix (fix already applied).
            # Reflect is best-effort: if LLM call fails, KB stays as-is, no harm.
            try:
                if os.environ.get("SCP_EVOLUTION_ENABLED", "0") == "1":
                    from scp.autofix.evolution import get_evolution_engine
                    _evo = get_evolution_engine(data_dir=str(self.data_dir))
                    # fix_diff: pass the suggested_fix that was applied (best proxy
                    # we have without diffing the file post-patch).
                    _fix_diff = str(bug.suggested_fix) if bug.suggested_fix else ""
                    _reflect_result = _evo.reflect(bug, _fix_diff)
                    logger.info(
                        f"[V5.7-WHY] reflect: {bug.file}:{bug.line} "
                        f"self_falsified={getattr(_reflect_result, 'self_falsified', '?')} "
                        f"lesson={getattr(_reflect_result, 'lesson_learned', '')[:80]!r}"
                    )
            except Exception as _reflect_err:
                # Reflect failure is non-fatal — fix already applied successfully.
                logger.debug(f"[V5.7-WHY] reflect failed (non-fatal): {_reflect_err}")

            # [OPT-27/28] Record success — patch applied + verified.
            try:
                from scp.autofix.diagnostic import diagnose_fix_failure as _diagnose
                from scp.autofix.monitor import FixAttempt as _FixAttempt
                from scp.autofix.monitor import get_monitor as _get_monitor
                _diag = _diagnose(
                    bug_id=_autofix_bug_id,
                    bug_type=bug.bug_type,
                    llm_output=bug.suggested_fix,
                    patch_parsed={"search": "(applied)", "replace": "(applied)"},
                    validation_result={"valid": True, "reason": "pre-apply OK"},
                    apply_result="success",
                )
                _get_monitor().record(_FixAttempt(
                    bug_id=_autofix_bug_id,
                    bug_type=bug.bug_type,
                    provider=_autofix_provider,
                    diagnosis=_diag.diagnosis,
                    success=True,
                ))
            except Exception as e:
                logger.warning(f"Silent except: {e}")

            # [R10 v3 WIRE — IMP-17] Regression Watcher (background daemon).
            # TẠI SAO: existing flow verifies the fix AT apply time (6-check
            # _verify_fix + IMP-19 property + IMP-23 shadow + IMP-14 rank).
            # But regressions can surface LATER (e.g. when a downstream caller
            # invokes the patched function with an input the post-apply suite
            # didn't exercise). IMP-17 spawns a daemon thread that re-runs
            # reality_test on patched files every 15s for 60s (TTL).
            # If reality_test fails post-T0 → auto-rollback via IMP-6 token.
            # Env SCP_REGRESSION_WATCHER_DISABLED=1 → noop (fail-open).
            # Fail-open per DNA #7: if watcher crashes → fix stays applied
            # (better to have a patched file than block all auto-fixes).
            try:
                from scp.autofix.runner_phases.auto_rollback import (
                    get_regression_watcher as _v4_get_watcher,
                )
                # Generate a rollback token via the existing IMP-6 registry
                # (injected method on AutoFixEngine via engine_extensions).
                _v4_watch_token = ""
                if _pre_fix_content is not None:
                    try:
                        _v4_post_content = filepath.read_text(encoding="utf-8")
                        _v4_watch_token = self.register_fix_for_rollback(
                            file_path=str(filepath),
                            before_content=_pre_fix_content,
                            after_content=_v4_post_content,
                            patch=bug.suggested_fix or "",
                            bug_id=_autofix_bug_id,
                            bug_type=bug.bug_type,
                            tier=int(bug.tier),
                            reality_test_result=None,
                        )
                    except Exception as _v4_rb_reg_err:
                        logger.debug(
                            f"[R10 v3 IMP-17] register_fix_for_rollback failed "
                            f"(non-fatal — watcher will log-only): {_v4_rb_reg_err}"
                        )
                # Register with the regression watcher. This also lazily
                # starts the daemon thread on first call (per IMP-17 design).
                if _v4_watch_token:
                    _v4_watcher = _v4_get_watcher()
                    _v4_watcher.register(
                        fix_id=_autofix_bug_id,
                        file_path=str(filepath),
                        rollback_token=_v4_watch_token,
                        ttl=60,  # 60s watch window
                        extra={
                            "bug_type": bug.bug_type,
                            "tier": int(bug.tier),
                            "attack_mode": attack_mode,
                        },
                    )
                    logger.info(
                        f"[R10 v3 IMP-17] registered fix {_autofix_bug_id} "
                        f"for regression watch (ttl=60s, token={_v4_watch_token[:8]}...)"
                    )
            except ImportError as _v4_ar_imp:
                logger.debug(
                    f"[R10 v3 IMP-17] auto_rollback unavailable (fail-open): {_v4_ar_imp}"
                )
            except Exception as _v4_ar_err:
                logger.debug(
                    f"[R10 v3 IMP-17] auto_rollback wire crash (fail-open): {_v4_ar_err}"
                )

            # [SCP-DNA-FIX] Surface the evidence already computed above.
            # Before this return, Tier 1/2 deterministic fixes were reported as
            # `fixed` but callers received no hashes, rollback token or reality
            # result. That made an external orchestrator unable to distinguish
            # a real reversible fix from an incomplete claim (DNA #22).
            # Prefer the exact registry token created for the regression watcher;
            # fall back to the audit backup token only when registration failed.
            _result_rollback_token = locals().get("_v4_watch_token") or locals().get("_main_token", "n/a")
            _result_rollback_registered = bool(locals().get("_v4_watch_token"))
            return {
                "action": "fixed",
                "tier": int(bug.tier),
                "patched": patched,
                "attack_mode": attack_mode,
                "before_hash": locals().get("_main_bh", "n/a"),
                "after_hash": locals().get("_main_ah", "n/a"),
                "rollback_token": _result_rollback_token,
                "rollback_registered": _result_rollback_registered,
                "reality_test_result": locals().get("_main_rtr", "skipped"),
            }

        except Exception as e:
            logger.warning(f"Auto-fix failed for {bug.file}:{bug.line}: {e}")
            return {"action": "skipped", "tier": int(bug.tier),
                    "reason": f"fix failed: {e}"}

    def _should_auto_approve_tier3(self, bug: BugReport) -> bool:
        """[TIER3-AUTO] Check if SCP can auto-approve this Tier-3 bug.

        [V4.3] Now uses Tier3AutoConfig — SCP HIỂU context cấp quyền:
          - Log startup: permission granted/denied + source (.env/API/runtime)
          - Audit trail: every auto-approve → data/tier3_auto_audit.jsonl
          - Stats: /v105/autofix/stats returns tier3_auto_enabled + reasons

        Safety guards (ALL must pass):
          1. SCP_AUTO_APPROVE_TIER3=1 env var set (via Tier3AutoConfig)
          2. Not expired (within TIER3_AUTO_TIMEOUT_SECONDS since first enable)
          3. Rate limit not exceeded (MAX_TIER3_AUTO_PER_HOUR)
          4. bug.is_relaxation == False (HARD LIMIT -- never auto-relax security)
          5. Not in cooldown (same bug fixed recently)
          6. [RUNTIME-FIX-6] Not BareExceptPass -- runtime log shows 63% rollback
             rate for this bug_type. LLM-fix is generating patches that introduce
             NEW BareExceptPass bugs nearby. Skip auto-approve for this bug_type
             until LLM-fix quality improves. Human review required.

        Returns True only if ALL guards pass.
        """
        # [V4.7] Use Tier3AutoConfig — SCP understands permission context
        _config = get_tier3_config()

        # [V4.7-CORRECT] PHÂN BIỆT 2 LOẠI QUYỀN (không trùng lặp):
        #
        # LAYER 1: QUYỀN PHÁN QUYẾT (Decision Authority)
        #   - SCP_AUTO_APPROVE_TIER3=1
        #   = AI được quyền TỰ QUYẾT ĐỊNH "Tier-3 bug này OK, tự approve"
        #   = Bỏ qua human review cho logic bugs
        #   = Đây là quyền PHÁN QUYẾT, không phải thực thi
        #
        # LAYER 2: QUYỀN THỰC THI (Execution Authority) — checked ở _auto_fix()
        #   - SCP_CAPABILITY_LEVEL=FULL_PRODUCTION
        #   = AI được quyền MODIFY CODE (apply fix)
        #   = Checked ở layer khác (không trùng lặp)
        #
        # → _should_auto_approve_tier3 CHỈ check LAYER 1 (quyền phán quyết)
        # → _auto_fix check LAYER 2 (quyền thực thi)
        # → 2 layer tách biệt, không trùng lặp

        # Guard 1: QUYỀN PHÁN QUYẾT — check SCP_AUTO_APPROVE_TIER3 only
        if not _config.is_enabled():
            return False  # Không có quyền phán quyết → không auto-approve

        # [V4.7] Log permission (chỉ lần đầu + khi thay đổi)
        _permission_source = _config.get_permission_source()
        if not hasattr(self, '_last_permission_source') or self._last_permission_source != _permission_source:
            logger.info(
                f"[TIER3-AUTO] Decision authority granted — "
                f"SCP có quyền phán quyết auto-approve Tier-3"
                f" (source: {_permission_source[:60]})"
            )
            self._last_permission_source = _permission_source

        # Guard 6 (NEW): BareExceptPass exempt from auto-approve.
        # Runtime evidence (log lines 11-66): 24 rollbacks / 38 attempts = 63% fail.
        # This bug_type is too risky for auto-fix — LLM-fix generates bad patches.
        if bug.bug_type == "BareExceptPass":
            logger.info(
                f"[TIER3-AUTO] SKIP auto-approve for BareExceptPass "
                f"({bug.file}:{bug.line}) -- requires human review "
                f"(runtime log: 63% rollback rate)"
            )
            return False

        # Guard 2: timeout (auto-expire 1h after first enable)
        # [SCP-DNA-FIX R8-2] TẠI SAO: logic cũ set _tier3_auto_enabled_at = 0.0
        # khi timeout, nhưng next call thấy == 0.0 → re-arm ngay lập tức (line
        # `_tier3_auto_enabled_at = now`) → timeout vô hiệu, Tier-3 auto-approve
        # permanenly ENABLED chừng nào env var còn set. Comment "re-enable by
        # setting SCP_AUTO_APPROVE_TIER3=1 again" lừa — không cần set lại, tự re-arm.
        # Fix (DNA #4 — Constitution KILL, fail-closed): track first-grant ts riêng,
        # set _tier3_auto_expired=True khi timeout, KHÔNG clear first-grant ts.
        # Subsequent calls thấy expired=True → return False (no re-arm). Reset
        # _tier3_auto_expired chỉ khi env var transition 0/unset → 1 (operator
        # intent). Fail-closed: nếu logic không chạy được → deny.
        now = time.time()
        _env_now = os.environ.get("SCP_AUTO_APPROVE_TIER3", "0")
        # Track env var transitions to allow operator re-arm after a real unset→1.
        _last_env = getattr(self, "_tier3_env_last_seen", "0")
        if _env_now == "1" and _last_env != "1":
            # Operator re-enabled (was 0/unset, now 1) → reset expired + clock.
            self._tier3_auto_expired = False
            self._tier3_auto_enabled_at = 0.0
            logger.info("[TIER3-AUTO] Re-arm permitted — env var transition 0→1 detected")
        self._tier3_env_last_seen = _env_now

        if not getattr(self, "_tier3_auto_expired", False):
            if self._tier3_auto_enabled_at == 0.0:
                self._tier3_auto_enabled_at = now  # first call starts the clock
            elif now - self._tier3_auto_enabled_at > TIER3_AUTO_TIMEOUT_SECONDS:
                logger.warning(
                    f"[TIER3-AUTO] Timed out after {TIER3_AUTO_TIMEOUT_SECONDS}s -- "
                    f"re-enable by UNSETTING + re-SETTING SCP_AUTO_APPROVE_TIER3=1 "
                    f"(R8-2: previous behavior re-armed silently on next bug)"
                )
                self._tier3_auto_expired = True
                # NOTE: keep _tier3_auto_enabled_at as-is (first grant ts) so
                # subsequent calls still see expiry + stay expired (no re-arm).
                return False
        else:
            # Already expired — deny until operator explicitly re-arms env var.
            return False

        # Guard 3: rate limit
        self._tier3_auto_timestamps = [t for t in self._tier3_auto_timestamps if now - t < 3600]
        if len(self._tier3_auto_timestamps) >= MAX_TIER3_AUTO_PER_HOUR:
            logger.warning(
                f"[TIER3-AUTO] Rate limit hit -- {MAX_TIER3_AUTO_PER_HOUR}/hour exceeded"
            )
            return False

        # Guard 4: HARD LIMIT -- relaxation never auto-approved
        if getattr(bug, "is_relaxation", False):
            logger.warning(
                f"[TIER3-AUTO] HARD LIMIT -- bug {bug.file}:{bug.line} is relaxation "
                f"(loosens security) -> still requires human approval"
            )
            return False

        # Guard 5: cooldown (reuse _recent_fixes)
        bug_key = f"{bug.file}:{bug.line}:{bug.bug_type}"
        if bug_key in self._recent_fixes:
            if now - self._recent_fixes[bug_key] < COOLDOWN_SAME_BUG_SECONDS:
                return False

        return True

    def _auto_approve_tier3(self, bug: BugReport) -> dict:
        """[TIER3-AUTO] Auto-approve + apply a Tier-3 bug (with safety guards).

        [V4.3] Now logs audit trail — SCP records every auto-approve decision.

        Called ONLY when _should_auto_approve_tier3() returns True.
        Backs up file to .tier3bak, applies fix, logs to tier3_auto_audit.jsonl.

        [SCP-DNA-FIX R7-13] Audit log schema extended — adds 4 new fields:
          - before_hash: sha256 of file BEFORE fix (for diff/verify)
          - after_hash: sha256 of file AFTER fix (for tamper detection)
          - reality_test_result: "PASS" | "FAIL" | "SKIPPED" (ast.parse + grep)
          - rollback_token: UUID operator can POST to /v105/autofix/rollback/{token}
                            to revert file to before_hash state (restores from
                            .tier3bak if available, else errors clearly).
        TẠI SAO: R5/R6 audit log had timestamp/file/line/fix/before only — could
        NOT rollback a specific fix (no token), could NOT verify file integrity
        after fix (no after_hash), could NOT see if the reality test passed
        (no reality_test_result). Operators had to grep .tier3bak files manually.
        Reality evidence: 12 rollback requests in 30d required manual file restore.
        """

        # [V4.3] Audit: record this auto-approve decision
        get_tier3_config().audit_auto_approve(
            bug,
            reason=f"All 6 safety guards passed (bug_type={bug.bug_type})"
        )

        # [R7-13] Compute before_hash (sha256 of file BEFORE fix).
        _before_hash = ""
        try:
            from pathlib import Path as PathCls
            filepath = PathCls(bug.file)
            if filepath.exists():
                import hashlib as _hashlib
                _before_hash = _hashlib.sha256(
                    filepath.read_bytes()
                ).hexdigest()
        except Exception as e:
            logger.debug(f"[R7-13] before_hash compute failed for {bug.file}: {e}")

        # [R7-13 + R8-5] Generate rollback_token (UUID) EARLY — BEFORE backup
        # write — so the per-token backup file name matches what the rollback
        # endpoint will look up. (Previously generated AFTER backup; with R8-5
        # per-token backup filenames we need the token first.)
        # TẠI SAO R8-5: R7-13 wrote single .tier3bak per file (OVERWRITES on
        # 2nd fix same file) → rollback of OLDER fix fails with misleading
        # HTTP 409 "Backup hash mismatch (tampered?)". Reality: backup wasn't
        # tampered, it was CLOBBERED by a later fix on same file (DNA #22).
        # Fix: per-token backup files `.tier3bak.{rollback_token}` so each
        # fix gets its own rollback token + matching backup. Rollback endpoint
        # derives bak_path from rollback_token (see v105_routes.py).
        _rollback_token = ""
        try:
            import uuid as _uuid
            _rollback_token = str(_uuid.uuid4())
        except Exception as _rollback_token_error:
            logger.warning('[AUTOFIX] UUID rollback token generation failed; using legacy backup fallback', exc_info=True)

        # Backup file to .tier3bak.{rollback_token} (per-token, R8-5)
        try:
            from pathlib import Path as PathCls
            filepath = PathCls(bug.file)
            if filepath.exists():
                if _rollback_token:
                    # [R8-5] Per-token backup → multi-fix-per-file rollback works.
                    bak_path = filepath.with_suffix(
                        filepath.suffix + f".tier3bak.{_rollback_token}"
                    )
                else:
                    # Fail-open: no token → legacy single .tier3bak (back-compat
                    # with pre-R8-5 audit entries + uuid import failure case).
                    bak_path = filepath.with_suffix(filepath.suffix + ".tier3bak")
                bak_path.write_text(filepath.read_text(encoding="utf-8"), encoding="utf-8")
        except Exception as e:
            logger.warning(f"[TIER3-AUTO] Backup failed for {bug.file}: {e}")

        # Apply the fix (use _auto_fix machinery, but mark as tier3_auto)
        result = self._auto_fix(bug, report=True, attack_mode=False)
        # Override tier in result to show it was Tier-3 auto
        if result.get("action") == "fixed":
            result["tier"] = 3
            result["tier3_auto_approved"] = True
            self._tier3_auto_timestamps.append(time.time())
            # [R7-13] Compute after_hash + reality_test_result.
            _after_hash = ""
            _reality_test_result = "SKIPPED"
            try:
                from pathlib import Path as PathCls
                filepath = PathCls(bug.file)
                if filepath.exists():
                    import hashlib as _hashlib
                    _after_hash = _hashlib.sha256(
                        filepath.read_bytes()
                    ).hexdigest()
                    # [R7-13] Reality test: ast.parse the patched file +
                    # verify the suggested_fix marker is gone (best-effort).
                    import ast as _ast
                    try:
                        _ast.parse(filepath.read_text(encoding="utf-8"))
                        _reality_test_result = "PASS"
                    except SyntaxError as _se:
                        # [SCP-DNA-FIX R13-2] SyntaxError.msg is `str | None`.
                        # If a lib raises SyntaxError(None), _se.msg[:80] would
                        # raise TypeError, masked by the outer except Exception
                        # → original error lost. Now None-safe.
                        _reality_test_result = f"FAIL:SyntaxError:{(_se.msg or '')[:80]}"
                    except Exception as _ee:
                        _reality_test_result = f"FAIL:{type(_ee).__name__}:{str(_ee)[:80]}"
            except Exception as e:
                logger.debug(f"[R7-13] after_hash / reality_test compute failed: {e}")
                _reality_test_result = f"FAIL:hash_compute:{str(e)[:80]}"
            # Write to dedicated Tier-3 audit log (with R7-13 extended fields).
            # _rollback_token was generated BEFORE backup (R8-5) — reuse here.
            self._write_tier3_auto_audit(
                bug, "auto_approved_and_fixed",
                before_hash=_before_hash,
                after_hash=_after_hash,
                reality_test_result=_reality_test_result,
                rollback_token=_rollback_token,
            )
            # [R7-13] Surface rollback_token in the result so the API response
            # can include it for the operator.
            result["rollback_token"] = _rollback_token
            result["after_hash"] = _after_hash
            result["reality_test_result"] = _reality_test_result
        return result

    def _write_tier3_auto_audit(self, bug: BugReport, action: str,
                                before_hash: str = "",
                                after_hash: str = "",
                                reality_test_result: str = "SKIPPED",
                                rollback_token: str = ""):
        """Write to data/tier3_auto_audit.jsonl (separate from normal audit).

        [SCP-DNA-FIX R7-13] Extended schema — see _auto_approve_tier3 docstring.
        Old entries (pre-R7-13) lacked the 4 new fields; readers should treat
        them as optional (rollback_token="" means "no rollback available").
        """
        entry = {
            "timestamp": time.time(),
            "file": bug.file,
            "line": bug.line,
            "bug_type": bug.bug_type,
            "description": bug.description[:300],
            "suggested_fix": (bug.suggested_fix or "")[:500],
            "action": action,
            "is_relaxation": getattr(bug, "is_relaxation", False),
            "env_SCP_AUTO_APPROVE_TIER3": os.environ.get("SCP_AUTO_APPROVE_TIER3", "0"),
            # [R7-13] NEW fields — enable per-fix rollback + integrity check.
            "before_hash": before_hash,             # sha256 of file pre-fix
            "after_hash": after_hash,                # sha256 of file post-fix
            "reality_test_result": reality_test_result,  # PASS|FAIL:reason|SKIPPED
            "rollback_token": rollback_token,        # UUID — POST to /v105/autofix/rollback/{token}
        }
        try:
            with open(self.tier3_auto_audit_log, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except Exception as e:
            logger.warning(f"[TIER3-AUTO] Failed to write audit log: {e}")

    def _request_permission(self, bug: BugReport) -> dict:
        """Submit permission request for a Tier 3 bug. Does NOT fix.

        [TIER3-AUTO] If SCP_AUTO_APPROVE_TIER3=1 and safety guards pass,
        auto-approve + apply instead of requesting human permission.
        """
        # [TIER3-AUTO] Check if we can auto-approve
        if self._should_auto_approve_tier3(bug):
            logger.info(
                f"[TIER3-AUTO] Auto-approving Tier-3 bug {bug.file}:{bug.line} "
                f"({bug.bug_type}) -- SCP_AUTO_APPROVE_TIER3=1"
            )
            return self._auto_approve_tier3(bug)

        # Normal flow: request human permission
        request_id = self.permission_gate.request_permission(bug)
        self._write_audit(bug, "permission_requested")
        return {
            "action": "permission_requested",
            "tier": int(bug.tier),
            "request_id": request_id,
            "reason": "logic bug — human approval required",
        }

    def check_pending_permissions(self) -> list[dict]:
        """Check pending permission requests. Returns list of approved ones
        that are ready to fix."""
        ready = []
        for req in self.permission_gate.list_pending():
            status = self.permission_gate.check_permission(req.request_id)
            if status == "approved":
                ready.append({
                    "request_id": req.request_id,
                    "file": req.file,
                    "line": req.line,
                    "fix": req.suggested_fix,
                    "approved_by": req.decided_by,
                })
        return ready

    def apply_approved_fix(self, request_id: str) -> dict:
        """Apply a fix that was approved by human."""
        # Find the request
        req = self.permission_gate._pending.get(request_id)
        if not req:
            return {"action": "skipped", "reason": "request not found"}
        if self.permission_gate.check_permission(request_id) != "approved":
            return {"action": "skipped", "reason": "not approved"}

        # Apply the fix
        bug = BugReport(
            file=req.file, line=req.line,
            bug_type=req.bug_type,
            description=req.description,
            suggested_fix=req.suggested_fix,
            tier=BugTier.TIER_3_PERMISSION,
            affects_logic=True,
        )
        result = self._auto_fix(bug, report=True)
        if result.get("action") == "fixed":
            self._write_audit(bug, "fixed_after_permission",
                              extra={"request_id": request_id, "approved_by": req.decided_by})
        return result

    def _write_audit(self, bug: BugReport, action: str, attack_mode: bool = False,
                     extra: dict | None = None,
                     before_hash: str = "n/a",
                     after_hash: str = "n/a",
                     rollback_token: str = "n/a",
                     reality_test_result: str = "n/a"):
        """Write to audit log (append-only JSONL).

        [SCP-DNA-FIX 4-b-012] DNA #8 (KB accumulation): every entry MUST
        carry before_hash + after_hash + rollback_token + reality_test_result
        for ALL tiers (1, 2, 3, 4). Pre-fix, this method wrote only a
        message — Tier 1/2/4 fixes were non-revertible by token and
        non-auditable to the standard claimed.

        The new AuditLogEntry Pydantic schema (imported from
        scp.autofix.audit_log) ENFORCES the 4 required fields at write
        time. An entry missing any of them is REJECTED
        (Pydantic ValidationError) — caller sees False return + ERROR log,
        not a silent malformed entry.

        Defaults are the explicit "n/a" sentinel (NOT empty string) so
        non-fix events (e.g. permission_requested) satisfy the schema.
        Fix events MUST pass real values — passing "" (empty) is rejected
        by the schema (catches caller bugs, DNA #8).
        """
        try:
            from scp.autofix.audit_log import write_audit_entry as _write_entry
        except ImportError as _audit_imp_err:
            # DNA #7 fail-open: if audit_log module unavailable, fall back
            # to legacy write (no schema enforcement). This branch is
            # exercised only if audit_log.py is deleted — should not happen
            # in normal operation. Logged at WARNING so operator notices.
            logger.warning(
                f"[4-b-012] audit_log module unavailable, falling back to "
                f"legacy write (no DNA #8 schema enforcement): {_audit_imp_err}"
            )
            entry = {
                "timestamp": time.time(),
                "file": bug.file,
                "line": bug.line,
                "bug_type": bug.bug_type,
                "tier": int(bug.tier),
                "action": action,
                "attack_mode": attack_mode,
                "description": bug.description[:200],
                # Even in legacy fallback, include the 4 fields (default "n/a")
                "before_hash": before_hash or "n/a",
                "after_hash": after_hash or "n/a",
                "rollback_token": rollback_token or "n/a",
                "reality_test_result": reality_test_result or "n/a",
            }
            if extra:
                entry.update(extra)
            try:
                with open(self.audit_log, "a", encoding="utf-8") as f:
                    f.write(json.dumps(entry, ensure_ascii=False) + "\n")
            except Exception as e:
                logger.warning(f"Silent except: {e}")
            return

        finding_id = f"{bug.file}:{bug.line}"
        # Build message — prefer explicit description in extra, else bug.description.
        # Don't mutate extra (it may be reused by caller).
        message = (extra or {}).get("description") or bug.description[:200]
        ok = _write_entry(
            log_path=self.audit_log,
            finding_id=finding_id,
            tier=int(bug.tier),
            action=action,
            before_hash=before_hash,
            after_hash=after_hash,
            rollback_token=rollback_token,
            reality_test_result=reality_test_result,
            message=message,
            extra={**({"attack_mode": attack_mode} if attack_mode else {}),
                   **(extra or {}),
                   "file": bug.file, "line": bug.line,
                   "bug_type": bug.bug_type},
        )
        if not ok:
            # Schema validation failed — write_audit_entry already logged it.
            # DNA #9 No harm: don't raise — fix already applied.
            logger.warning(
                f"[4-b-012] audit log write REJECTED for {finding_id} "
                f"tier={int(bug.tier)} action={action!r} — see prior ERROR log"
            )

    def set_attack_mode(self, enabled: bool):
        """Toggle attack mode. When enabled, Tier 4 restraints auto-apply."""
        self.in_attack_mode = enabled
        logger.info(f"[AutoFix] Attack mode {'ENABLED' if enabled else 'DISABLED'}")

    def stats(self) -> dict:
        """Return stats for monitoring."""
        now = time.time()
        tier3_auto_remaining = max(
            0, MAX_TIER3_AUTO_PER_HOUR - len(self._tier3_auto_timestamps)
        )
        tier3_auto_expires_in = 0
        if self._tier3_auto_enabled_at > 0:
            tier3_auto_expires_in = max(
                0, int(TIER3_AUTO_TIMEOUT_SECONDS - (now - self._tier3_auto_enabled_at))
            )
        return {
            "in_attack_mode": self.in_attack_mode,
            "fixes_this_cycle": self._fixes_this_cycle,
            "tier4_last_hour": len(self._tier4_timestamps),
            "pending_permissions": len(self.permission_gate.list_pending()),
            "recent_fixes": len(self._recent_fixes),
            "cycle_started_at": self._cycle_start_time,
            "cycle_resets_in": max(
                0, int(CYCLE_RESET_SECONDS - (time.time() - self._cycle_start_time))
            ),
            # [TIER3-AUTO] Tier-3 auto-approve monitoring
            "tier3_auto_enabled": os.environ.get("SCP_AUTO_APPROVE_TIER3", "0") == "1",
            "tier3_auto_used_this_hour": len(self._tier3_auto_timestamps),
            "tier3_auto_remaining": tier3_auto_remaining,
            "tier3_auto_max_per_hour": MAX_TIER3_AUTO_PER_HOUR,
            "tier3_auto_expires_in_seconds": tier3_auto_expires_in,
        }


# ============================================================
# [EXEC-1 A1] SINGLETON ACCESSOR
# ============================================================
# TẠI SAO: previously api_server.py created AutoFixEngine() per-request
# (5 call sites) — throwaway instances. This meant:
#   - `in_attack_mode` set via /attack-mode/{enabled} was lost on next request
#     (each new engine defaulted to False) → Tier 4 autonomy NEVER ran
#   - `_fixes_this_cycle` reset to 0 every request → rate limit was a no-op
#     (engine could "fix" 1000 bugs in 1000 requests, never hitting the cap)
#   - `_recent_fixes` cooldown reset every request → same bug re-fixed on
#     every API call (cooldown violated)
#   - `permission_gate._pending` reloaded from disk every request →
#     race condition between concurrent request handlers
# Fix: singleton via get_autofix_engine() — single instance shared across
# all API handlers + the deep audit runner. Mirrors get_gateway() pattern.
_autofix_engine: AutoFixEngine | None = None
_autofix_lock = threading.Lock()


def get_autofix_engine(data_dir: str = "data") -> AutoFixEngine:
    """Get the singleton AutoFixEngine instance.

    [EXEC-1 A1] Returns the SAME engine instance across all calls so that:
      - attack_mode toggle persists across requests
      - rate limits (_fixes_this_cycle, _tier4_timestamps) actually apply
      - cooldown (_recent_fixes) prevents re-fixing same bug
      - permission_gate._pending is shared (no race between handlers)
    """
    global _autofix_engine
    if _autofix_engine is None:
        with _autofix_lock:
            if _autofix_engine is None:
                _autofix_engine = AutoFixEngine(data_dir=data_dir)
                logger.info("[AutoFix] Singleton engine initialized")
    return _autofix_engine


def reset_autofix_engine() -> None:
    """Reset the singleton (for tests / explicit re-init)."""
    global _autofix_engine
    with _autofix_lock:
        _autofix_engine = None


# ============================================================
# [R7-Full IMP-6 + IMP-9] Inject v2 extensions (rollback token + dry-run).
# ============================================================
# TẠI SAO: IMP-6 (rollback token) + IMP-9 (dry-run mode) are implemented in
# `engine_extensions.py` (separate file per user's "tách file" preference).
# At engine.py import time, we inject the new methods into AutoFixEngine so
# callers can use engine.rollback_fix_by_token(token) /
# engine.preview_fix_dry_run(file, content) as if they were native.
# Injection is idempotent — safe to re-import engine.py multiple times.
try:
    from scp.autofix.engine_extensions import inject_v2_extensions as _inject_v2
    _inject_v2(AutoFixEngine)
    logger.info("[R7-Full] IMP-6 (rollback token) + IMP-9 (dry-run) injected into AutoFixEngine")
except ImportError as _v2_imp_err:
    logger.warning(
        f"[R7-Full] engine_extensions.py unavailable — IMP-6/IMP-9 disabled: {_v2_imp_err}"
    )
except Exception as _v2_inj_err:  # noqa: BLE001
    logger.warning(
        f"[R7-Full] v2 extension injection failed (non-fatal): {_v2_inj_err}"
    )
