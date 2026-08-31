"""
[V104.48] Code Evolution Agent — Tự sửa code nguồn (Mức 5-7)

TẠI SAO: SCP V104.47 có Mức 1-4 (tự sửa verdict/threshold/rules/knowledge)
nhưng KHÔNG có Mức 5-7 (tự sửa code nguồn). Câu chuyện Gà (Mục 1) mô tả:
  GỌI LLM + ĐỌC SOURCE + PHÁT HIỆN VẤN ĐỀ + SINH CODE MỚI
  + GHI/SỬA SOURCE + CHẠY CODE + KIỂM TRA KẾT QUẢ
  = VÒNG LẶP THAY ĐỔI HỆ THỐNG CÓ THỂ KHÉP KÍN

Module này thực hiện vòng lặp đó:
  1. Scan code (why_audit_tool) → tìm bugs
  2. Đọc file có bug
  3. Gọi LLM (OpenRouter/Ollama) → sinh patch
  4. Apply patch → git stash (backup)
  5. Run tests
  6. Pass → git commit | Fail → git stash pop (rollback)
  7. Log + notify

Safety (theo nguyên tắc Gà Mục 8-12):
  - Sandbox: chỉ sửa file trong scp/ (không chạm system)
  - Rollback: git stash trước mỗi patch
  - Test gate: pytest phải pass
  - Human approval: optional (SCP_EVOLUTION_AUTO=1 = auto, default = manual)
  - Rate limit: max 1 fix/cycle, max 10 fixes/day
  - Audit log: mọi thay đổi ghi evolution_log.jsonl
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
import time
from datetime import datetime
from pathlib import Path

from scp.core.pending_fix_review import ensure_review_guide
from scp.core.safe_process import safe_run

logger = logging.getLogger("scp.evolution")

SCP_ROOT = Path(__file__).parent.parent.parent  # project root
MAX_FIXES_PER_DAY = int(os.environ.get("SCP_EVOLUTION_MAX_DAILY", "10"))
AUTO_MODE = os.environ.get("SCP_EVOLUTION_AUTO", "0") == "1"  # legacy snapshot for compatibility


def _auto_mode_enabled() -> bool:
    """Read the safety switch at execution time, not only at import time."""
    return os.environ.get("SCP_EVOLUTION_AUTO", "0").strip().lower() in {"1", "true", "yes", "on"}


class CodeEvolutionAgent:
    """Tự tìm bug → sinh fix → test → commit/rollback."""

    def __init__(self):
        self.scp_dir = SCP_ROOT / "scp"
        self.tests_dir = SCP_ROOT / "tests"
        self.log_file = SCP_ROOT / "data" / "evolution_log.jsonl"
        self._fixes_today = 0
        self._last_reset = time.time()
        self._or_key = os.environ.get("OPENROUTER_API_KEY", "")
        self._or_model = os.environ.get("OPENROUTER_MODEL", "meta-llama/llama-3.3-70b-instruct")
        self._fixes_applied = 0
        self._fixes_rolled_back = 0
        self._fixes_skipped = 0

    def _reset_daily_if_needed(self):
        """Reset counter mỗi 24h."""
        if time.time() - self._last_reset > 86400:
            self._fixes_today = 0
            self._last_reset = time.time()

    async def run_cycle(self) -> dict:
        """Chạy 1 vòng evolution: scan → fix → test → commit/rollback."""
        self._reset_daily_if_needed()
        if self._fixes_today >= MAX_FIXES_PER_DAY:
            return {"status": "rate_limited", "fixes_today": self._fixes_today}

        result = {
            "started_at": datetime.now().astimezone().isoformat(),
            "bugs_found": 0,
            "fixes_attempted": 0,
            "fixes_applied": 0,
            "fixes_rolled_back": 0,
        }

        # Step 1: Scan code for bugs
        bugs = self._scan_bugs()
        result["bugs_found"] = len(bugs)
        if not bugs:
            result["status"] = "no_bugs_found"
            return result

        # Step 2: Pick highest-priority bug
        bug = bugs[0]  # already sorted by severity
        result["fixes_attempted"] = 1

        # Step 3: Read file + generate fix
        fix = await self._generate_fix(bug)
        if not fix:
            result["status"] = "fix_generation_failed"
            self._fixes_skipped += 1
            return result

        # Step 4: Apply fix (with backup) —  _apply_fix now returns
        # True only if the code was ACTUALLY patched (not just commented).
        filepath = SCP_ROOT / bug["file"]
        backup = self._backup_file(filepath)
        actually_patched = self._apply_fix(filepath, fix)

        if not actually_patched:
            # [P2-15] Fix was queued for human review (written to pending_fixes/).
            # Do NOT run tests on unchanged code (would pass trivially → false
            # confidence) and do NOT commit. SCP principle: "PASS ≠ ĐÚNG" — a
            # passing test on unchanged code proves nothing.
            self._fixes_skipped += 1
            result["status"] = "fix_queued_for_review"
            result["fixes_skipped"] = 1
            self._log_evolution(bug, fix, {"passed": False, "output": "", "failures": "not patched — queued for review"}, applied=False)
            result["ended_at"] = datetime.now().astimezone().isoformat()
            return result

        # Step 5: Run tests (on the ACTUALLY patched code)
        test_result = self._run_tests()

        # Step 6: Commit or rollback
        #  Only auto-commit if AUTO_MODE is enabled. In manual mode,
        # leave the patch on disk + log for human review (operator decides whether
        # to commit). Was: committed regardless of AUTO_MODE → auto-commits in
        # manual mode, defeating the purpose of the flag.
        if test_result["passed"]:
            if _auto_mode_enabled():
                self._commit_fix(bug, fix, test_result)
                self._fixes_applied += 1
                self._fixes_today += 1
                result["fixes_applied"] = 1
                result["status"] = "fix_applied"
            else:
                # Manual mode: patch is on disk, tests pass, but don't commit.
                # Operator reviews `git diff` and commits manually.
                self._fixes_applied += 1  # count as "applied to working tree"
                result["status"] = "fix_applied_pending_commit"
                result["note"] = "AUTO_MODE=0 — patch on disk, awaiting manual git commit"
            self._log_evolution(bug, fix, test_result, applied=True)
        else:
            self._restore_backup(filepath, backup)
            self._fixes_rolled_back += 1
            result["fixes_rolled_back"] = 1
            result["status"] = "fix_rolled_back"
            result["test_failures"] = test_result.get("failures", [])
            self._log_evolution(bug, fix, test_result, applied=False)

        result["ended_at"] = datetime.now().astimezone().isoformat()
        return result

    def _scan_bugs(self) -> list[dict]:
        """Scan code using SCP's own audit scanner.

        [SCP-DNA-FIX R13-2] R4-R12 imported `from why_audit_tool import scan_file`
        but that module does NOT exist anywhere in the repo. The try/except
        silently returned [] → run_cycle() always returned "no_bugs_found" →
        the ENTIRE self-evolving-code feature was DEAD (DNA #22: PASS ≠ TRUE —
        scanner "ran" every cycle but found nothing because the import failed).
        Fix: wire to SCP's own REAL scanner — `run_full_scan` from
        `runner_phases.report` runs all 18 V5.9/V8.0 scanners + AST scan.
        DNA: use SCP's own tools (DNA #21 — audit the auditor).
        """
        bugs = []
        try:
            # Use SCP's own real scanner — runs 18 V5.9/V8.0 scanners + AST scan.
            from scp.autofix.runner_phases.report import run_full_scan
            scan_summary = run_full_scan(include_ast=True)
            # BugReport has `tier` (BugTier IntEnum 1-4). Tier 1 = silent auto-fix
            # (implementation bugs); Tier 2+ = audit-logged / permission-gated.
            # Evolution loop should only auto-target Tier 2+ (HIGH/CRITICAL).
            for br in scan_summary.get("bugs", []):
                try:
                    _tier_val = int(getattr(br, "tier", 1) or 1)
                except (TypeError, ValueError):
                    _tier_val = 1
                if _tier_val < 2:
                    continue
                severity = "CRITICAL" if _tier_val >= 3 else "HIGH"
                bugs.append({
                    "file": str(getattr(br, "file", "")),
                    "line": int(getattr(br, "line", 0) or 0),
                    "pattern": str(getattr(br, "bug_type", "unknown")),
                    "severity": severity,
                    "why": str(getattr(br, "description", "")),
                    "fix_hint": str(getattr(br, "suggested_fix", "")),
                    "match": "",
                })
        except Exception as e:
            # Fail-loud: log the error so dead-scanner regressions don't silently
            # disable evolution again. (Old code: `except Exception: pass` → silent.)
            logger.error(f"[V104.48] Evolution scan failed (self-evolution disabled): {e}")

        # Sort by severity (CRITICAL first)
        severity_order = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}
        bugs.sort(key=lambda b: severity_order.get(b["severity"], 9))
        return bugs

    async def _generate_fix(self, bug: dict) -> str | None:
        """Gọi LLM (OpenRouter hoặc Ollama) để sinh fix."""
        filepath = SCP_ROOT / bug["file"]
        try:
            original = filepath.read_text(encoding='utf-8')
        except Exception:
            return None

        # Build prompt
        prompt = f"""You are a Python code fixer. Fix the bug in the file below.

BUG:
  File: {bug['file']}:{bug['line']}
  Pattern: {bug['pattern']}
  Problem: {bug['why']}
  Suggested fix: {bug['fix_hint']}
  Matched code: {bug['match']}

FILE CONTENT (heat-pruned: hàm nóng nguyên văn, hàm nguội được gấp):
{self._get_context(original, bug['line'], description=str(bug.get('description', '')))}

RULES:
1. Output ONLY the fixed Python code for the affected lines.
2. Do NOT output the entire file — only the changed section.
3. Use # [V104.48 AUTO] comment to mark your change.
4. Keep the fix minimal — don't refactor unrelated code.
5. If you can't fix it, output "CANNOT_FIX".

FIX:"""

        # Try OpenRouter first
        fix = await self._ask_openrouter(prompt)

        if fix and "CANNOT_FIX" in fix:
            return None
        return fix

    async def _ask_openrouter(self, prompt: str) -> str | None:
        """Gọi OpenRouter LLM."""
        if not self._or_key:
            return None
        try:
            import urllib.request
            data = json.dumps({
                "model": self._or_model,
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 500,
                "temperature": 0.1,
            }).encode()
            req = urllib.request.Request(  # noqa: S310 — URL is a hardcoded https:// constant, scheme validated by SCP
                "https://openrouter.ai/api/v1/chat/completions",
                data=data,
                headers={
                    "Authorization": f"Bearer {self._or_key}",
                    "Content-Type": "application/json",
                },
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=30) as resp:  # noqa: S310 — scheme validated above; nosec B310 — URL validated by SCP
                result = json.loads(resp.read())
                return result.get("choices", [{}])[0].get("message", {}).get("content", "").strip()
        except Exception as e:
            logger.debug(f"OpenRouter fix generation failed: {e}")
            return None

    def _get_context(self, content: str, line: int, radius: int = 50, description: str = "") -> str:
        """[MẢNH 32/44] AST heat-pruner: hàm nóng nguyên văn, hàm nguội gấp
        thành chữ ký — LLM thấy trọn vùng quan trọng không nhiễu. Fallback
        cửa sổ ±radius quanh bug nếu pruner lỗi (hành vi cũ)."""
        try:
            from scp.core.context_pruner import prune_source

            pruned = prune_source(content, line or 0, description)
            if pruned.strip():
                return pruned
        except Exception:
            pass
        lines = content.split('\n')
        start = max(0, line - radius)
        end = min(len(lines), line + radius)
        return '\n'.join(f"{i+1}: {lines[i]}" for i in range(start, end))

    def _backup_file(self, filepath: Path) -> str:
        """Backup file content before patching."""
        return filepath.read_text(encoding='utf-8')

    def _apply_fix(self, filepath: Path, fix: str) -> bool:
        """Apply fix to file. Returns True if actually patched, False if queued for review.

         TẠI SAO: the old implementation APPENDED the LLM fix as a
        `# comment` at the end of the file — it did NOT patch the code. Tests
        then ran on UNMODIFIED code (passed trivially), and `_commit_fix`
        committed a no-op comment while reporting `fix_applied=True`. The entire
        "self-evolving code" feature was a façade: it looked like SCP was fixing
        itself, but no code ever changed. This violates the SCP principle
        "PASS ≠ ĐÚNG" — a passing test on unchanged code proves nothing.

        Fix: actually attempt to patch the source.
          1. Parse `fix` for a search-and-replace block (markers: <<<<<<< SEARCH /
             ======= / >>>>>>> REPLACE, or legacy <<<<<<< OLD / ======= / >>>>>>> NEW,
             or ```python ... ``` fenced code with context).
          2. If found, perform the replacement (search → replace) in the file content.
          3. Verify the patched file compiles (ast.parse). If not, rollback.
          4. If no parseable patch found, write the suggestion to a
             `pending_fixes/` review file (NOT appended to source) and return False.

        [OPT-30] Accept BOTH new canonical SEARCH/REPLACE markers AND legacy
        OLD/NEW markers (backward compat for in-flight LLM outputs and any
        pre-[OPT-30] suggested_fix strings). Downstream callers can emit either
        format; the regex below tries both.
        """
        original = filepath.read_text(encoding='utf-8')
        patched = original
        applied = False

        # Strategy 1: search-and-replace block with explicit markers.
        # [OPT-30] Two patterns — try new SEARCH/REPLACE first, then legacy OLD/NEW.
        import re as _re

        # 1a. Canonical SEARCH/REPLACE format (lenient: optional closing suffix,
        # 5-7 equals — same lenience as _extract_search_replace_block).
        sr_search_pattern = _re.compile(
            r"<<<<<<<\s*SEARCH\s*\n(.*?)\n={5,7}\s*\n(.*?)\n>>>>>>>\s*(?:REPLACE)?\s*",
            _re.DOTALL,
        )
        # 1b. Legacy OLD/NEW format.
        sr_old_pattern = _re.compile(
            r"<<<<<<<\s*OLD\s*\n(.*?)\n={5,7}\s*\n(.*?)\n>>>>>>>\s*(?:NEW)?\s*",
            _re.DOTALL,
        )

        matches = list(sr_search_pattern.finditer(fix))
        if not matches:
            # Fall back to legacy OLD/NEW format.
            matches = list(sr_old_pattern.finditer(fix))

        if matches:
            patched = original
            for m in matches:
                old_text = m.group(1)
                new_text = m.group(2)
                if old_text in patched:
                    patched = patched.replace(old_text, new_text, 1)
                    applied = True
                else:
                    logger.warning(f"[V104.48] SEARCH/OLD block not found in {filepath.name} — skip this hunk")
            if applied and patched != original:
                # Verify it compiles before writing
                try:
                    import ast as _ast
                    _ast.parse(patched, filename=str(filepath))
                    filepath.write_text(patched, encoding='utf-8')
                    logger.info(f"[V104.48] Applied search-replace patch to {filepath.name}")
                    return True
                except SyntaxError as e:
                    logger.warning(f"[V104.48] Patched {filepath.name} has syntax error: {e} — not applied")
                    return False

        # Strategy 2: fenced code block — treat as a full replacement of the
        # function/class containing the bug line. (Risky — only if fix starts
        # with def/class and we can find a matching def/class in the file.)
        fenced = _re.search(r"```(?:python)?\s*\n(.*?)\n```", fix, _re.DOTALL)
        if fenced:
            code_block = fenced.group(1).strip()
            # Only attempt if the code block starts with a def/class/assignment
            # that exists in the file (so we can locate + replace it).
            first_line = code_block.split('\n', 1)[0]
            if first_line.startswith(('def ', 'class ', 'async def ')):
                # Extract the definition name
                name_match = _re.match(r'(?:async\s+)?(?:def|class)\s+(\w+)', first_line)
                if name_match:
                    def_name = name_match.group(1)
                    # Find the existing definition in the file (same signature start)
                    existing_pattern = _re.compile(
                        rf'((?:async\s+)?(?:def|class)\s+{_re.escape(def_name)}\b[^\n]*\n(?:(?:[ \t]+[^\n]*\n)*))',
                        _re.MULTILINE,
                    )
                    existing = existing_pattern.search(original)
                    if existing:
                        # Preserve leading indentation of the original first line
                        orig_first = existing.group(1).split('\n', 1)[0]
                        indent = len(orig_first) - len(orig_first.lstrip())
                        indented_block = '\n'.join(
                            (' ' * indent + line) if line and not line.startswith(' ' * indent) else line
                            for line in code_block.split('\n')
                        )
                        patched = original[:existing.start()] + indented_block + '\n' + original[existing.end():]
                        try:
                            import ast as _ast
                            _ast.parse(patched, filename=str(filepath))
                            filepath.write_text(patched, encoding='utf-8')
                            logger.info(f"[V104.48] Applied function-replacement patch to {filepath.name} ({def_name})")
                            return True
                        except SyntaxError as e:
                            logger.warning(f"[V104.48] Patched {filepath.name} has syntax error: {e} — not applied")
                            return False

        # Strategy 3: no parseable patch — queue for human review (do NOT pollute source)
        # [FIX-6] TẠI SAO: filename was {stem}_pending_{timestamp}.py — 10 bugs
        # in same file within 1 second → same filename → 9 overwritten. Now
        # includes line + bug_type hash → unique per bug.
        pending_dir = SCP_ROOT / "pending_fixes"
        pending_dir.mkdir(parents=True, exist_ok=True)
        import hashlib as _hashlib
        _bug_hash = _hashlib.sha256(f"{filepath}:{int(time.time())}:{id(fix)}".encode()).hexdigest()[:8]
        pending_file = pending_dir / f"{filepath.stem}_pending_{int(time.time())}_{_bug_hash}.py"
        review_content = (
            f"# [P2-15] Pending fix for {filepath.name} — queued for HUMAN review.\n"
            f"# SCP could not auto-parse the LLM fix into a safe patch.\n"
            f"# Original file: {filepath}\n"
            f"# Suggested fix from LLM:\n"
            f"# " + fix[:2000].replace('\n', '\n# ') + "\n"
        )
        pending_file.write_text(review_content, encoding='utf-8')
        ensure_review_guide(pending_dir)
        logger.info(f"[V104.48] Fix queued for human review: {pending_file}")
        return False

    def _restore_backup(self, filepath: Path, backup: str):
        """Restore original file content."""
        filepath.write_text(backup, encoding='utf-8')

    def _run_tests(self) -> dict:
        """Run pytest and return result."""
        try:
            result = safe_run(
                [sys.executable, "-m", "pytest", str(self.tests_dir), "-q", "--tb=line",
                 "--deselect", "tests/test_v1041_matrix.py::test_full_matrix_coverage_70",
                 "--deselect", "tests/test_v1042_fast_learning.py::test_compounding_l2"],
                timeout=120, cwd=str(SCP_ROOT),
                env={**os.environ, "SCP_DEV_MODE": "1"},
            )
            passed = result.returncode == 0
            return {
                "passed": passed,
                "output": result.stdout[-500:] if result.stdout else "",
                "failures": result.stderr[-500:] if result.stderr else "",
            }
        except Exception as e:
            return {"passed": False, "output": "", "failures": str(e)}

    def _commit_fix(self, bug: dict, fix: str, test_result: dict):
        """Commit fix to git."""
        try:
            safe_run(["git", "add", "-A"], cwd=str(SCP_ROOT))
            safe_run(
                ["git", "commit", "-m",
                 f"[V104.48 AUTO] Fix {bug['pattern']} in {bug['file']}:{bug['line']}\n"
                 f"Bug: {bug['why'][:100]}\n"
                 f"Tests: {'PASS' if test_result['passed'] else 'FAIL'}"],
                cwd=str(SCP_ROOT),
            )
        except Exception as e:
            logger.warning(f"Silent except: {e}")  # git may not be initialized

    def _log_evolution(self, bug: dict, fix: str, test_result: dict, applied: bool):
        """Log evolution event."""
        self.log_file.parent.mkdir(parents=True, exist_ok=True)
        entry = {
            "timestamp": datetime.now().astimezone().isoformat(),
            "bug": bug,
            "fix_preview": fix[:200],
            "test_passed": test_result["passed"],
            "applied": applied,
        }
        with open(self.log_file, 'a', encoding='utf-8') as f:
            f.write(json.dumps(entry, ensure_ascii=False) + '\n')

    def get_stats(self) -> dict:
        return {
            "fixes_applied": self._fixes_applied,
            "fixes_rolled_back": self._fixes_rolled_back,
            "fixes_skipped": self._fixes_skipped,
            "fixes_today": self._fixes_today,
            "max_per_day": MAX_FIXES_PER_DAY,
            "auto_mode": _auto_mode_enabled(),
        }


# ============================================================
# Background thread
# ============================================================
_evolution_agent: CodeEvolutionAgent | None = None


def get_evolution_agent() -> CodeEvolutionAgent:
    global _evolution_agent
    if _evolution_agent is None:
        _evolution_agent = CodeEvolutionAgent()
    return _evolution_agent


async def start_evolution_loop(interval: int = 3600):
    """Start evolution loop — chạy mỗi `interval` giây.

    Mặc định: 1 giờ (3600s).
    Tự sửa code chỉ chạy khi có bug CRITICAL/HIGH từ WHY audit.

    [SCP-DNA-FIX R13-3] vulture BUG-011 flagged this function as never-called.
    It IS an async entry point intended to be invoked from a scheduler/loop.
    For sync callers (e.g. _lifespan.py deep_audit_loop, CLI, or operator
    scripts), use the new sync wrapper `run_evolution_cycle_once()` below
    instead of `asyncio.run(start_evolution_loop())` (which would block
    forever). The wrapper runs ONE cycle and returns — caller decides
    scheduling cadence. TODO for parent: wire `run_evolution_cycle_once`
    into `_lifespan.py` `deep_audit_loop` (parent-owned — not edited here).
    """
    agent = get_evolution_agent()
    logger.info(f"[V104.48] Code Evolution Agent started (interval={interval}s, auto={_auto_mode_enabled()})")

    while True:
        try:
            result = await agent.run_cycle()
            if result.get("status") == "fix_applied":
                logger.info(f"[V104.48] Evolution: fix applied to {result.get('bug_file', '?')}")
            elif result.get("status") == "fix_rolled_back":
                logger.warning("[V104.48] Evolution: fix rolled back (tests failed)")
            elif result.get("status") == "no_bugs_found":
                logger.debug("[V104.48] Evolution: no bugs found")
        except Exception as e:
            logger.warning(f"[V104.48] Evolution error: {e}")

        await asyncio.sleep(interval)


def run_evolution_cycle_once() -> dict:
    """[SCP-DNA-FIX R13-3] Sync wrapper — runs ONE evolution cycle, returns result.

    TẠI SAO: `start_evolution_loop` is an `async` infinite loop — sync callers
    (CLI, _lifespan.py deep_audit_loop, operator scripts) cannot invoke it
    directly without `asyncio.run(...)` which would block forever. This
    wrapper runs exactly ONE cycle of `CodeEvolutionAgent.run_cycle()` and
    returns the result dict. Caller decides cadence (cron / scheduler /
    lifespan tick).

    Usage:
        from scp.core.code_evolution_agent import run_evolution_cycle_once
        result = run_evolution_cycle_once()
        # result = {"status": "no_bugs_found" | "fix_applied" | "fix_rolled_back" | ...}

    Wiring TODO (parent-owned, not edited here): wire this into
    `scp/api/_lifespan.py::deep_audit_loop` so each deep-audit tick also
    runs one evolution cycle. DNA #5 (process detects when it itself is
    wrong): self-evolution only fires when SCP's own scanners find bugs.
    """
    agent = get_evolution_agent()
    try:
        coro = agent.run_cycle()
        try:
            # Preferred: use the running loop if one exists (async context).
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None
        if loop is not None:
            # We're inside an event loop already — create a task + block on it.
            import concurrent.futures as _cf
            with _cf.ThreadPoolExecutor(max_workers=1) as pool:
                return pool.submit(lambda: asyncio.run(coro)).result()
        return asyncio.run(coro)
    except Exception as e:
        logger.error(f"[V104.48] run_evolution_cycle_once failed: {e}")
        return {"status": "error", "error": str(e)}
