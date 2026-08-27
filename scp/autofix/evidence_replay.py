"""
[SCP-DNA R12-9-BSGVA] BSG-VA Evidence Replay — classify test PASS as
gold-aligned / regression-only / misleading / candidate-specific / diagnostic-negative.

TẠI SAO file này tồn tại?
  R11 audit: post_fix_verify có 4 phases (base / reality_test / completeness /
  semantic_equiv) — TẤT CẢ đều trả lời "fix có chạy được không?" nhưng KHÔNG
  phase nào trả lời "test PASS có thực sự chứng minh bug được fix không?".
  DNA #22 (PASS ≠ TRUE): test PASS trên candidate chưa chắc đã bằng test PASS
  trên gold. Agent có thể "fix" bằng cách làm test vô nghĩa (ví dụ: xóa test,
  thêm try/except nuốt lỗi, hoặc sửa code sao cho test vô tình pass).

  BSG-VA paper (arXiv 2607.28871) định nghĩa 5 role của test evidence bằng
  cách replay test trên 3 code states:
    B = Buggy (code gốc trước fix)
    S = candidate State (code sau khi agent fix)
    G = Gold (code fix chuẩn từ human hoặc gold dataset)
  So sánh (b_pass, s_pass, g_pass) → phân loại evidence.

  5 EvidenceRole:
    GOLD_ALIGNED        — Fail B, Pass S+G   (test thật sự kiểm tra bug)
    REGRESSION_ONLY     — Pass B+S+G          (test không kiểm bug, chỉ chứng minh không regression)
    MISLEADING          — Pass B+S, Fail G    (test vô tình pass — evidence-fake)
    CANDIDATE_SPECIFIC  — Fail B, Pass S, Fail G (fix của agent khác gold)
    DIAGNOSTIC_NEGATIVE — Fail S              (patch không hoạt động, hoặc regression)

Flow:
  EvidenceReplay.classify_evidence(test_cmd, buggy_src, candidate_src, gold_src, file_path)
    → backup file_path
    → write buggy_src → run test_cmd → b_result
    → write candidate_src → run test_cmd → s_result
    → write gold_src → run test_cmd → g_result
    → restore file_path
    → classify role based on (b_pass, s_pass, g_pass)
    → ReplayResult(role, b/s/g_results, test_command, discriminating)

  Wire vào run_full_post_fix_verify phase "evidence_replay" (sau completeness_check).
    MISLEADING / REGRESSION_ONLY → escalate_to_tier3=True + log warning
    DIAGNOSTIC_NEGATIVE          → rollback=True

DNA principles applied:
  #22 (PASS ≠ TRUE) — test PASS ≠ bug FIXED; replay against gold để verify
  #26 (Reality > Model) — chạy thật test_command qua subprocess, không giả định
  #7 (Autofix safe) — wrap fail-open, không block pipeline nếu replay lỗi
  #9 (No harm) — restore file gốc sau replay, không phá workspace
  #23 (Audit the auditor) — audit agent's test evidence bằng gold baseline
"""
from __future__ import annotations

import hashlib
import json
import logging
import shlex
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

logger = logging.getLogger("scp.autofix.evidence_replay")

# Timeout cho subprocess run test (seconds). Fail-open nếu vượt.
_MAX_TEST_TIME_S = 30
# Lấy 200 ký tự cuối của output làm snippet (đủ để debug, không quá dài).
_OUTPUT_SNIPPET_LEN = 200

# [SCP-DNA-FIX R13-5] Bug #4: shell metacharacter blacklist for file_path.
# EvidenceReplay writes buggy/candidate/gold source to `file_path` on disk
# then runs `test_command` (which may reference the file's stem/name via
# shell expansion). If file_path contains shell metacharacters, a malicious
# or corrupted path could escape via shell=True → shell injection (bandit
# B602). We use shell=False + shlex.split now, but ALSO validate file_path
# itself to fail-closed on suspicious paths (defense-in-depth — even if a
# future refactor accidentally re-introduces shell=True, this guard holds).
_SHELL_METACHAR_BLACKLIST = frozenset(
    ";|&$`><\n\r\"'!*?[]{()}~"
)


# ============================================================
# EvidenceRole — 5 roles per BSG-VA Table.
# ============================================================
class EvidenceRole(str, Enum):
    """5 roles classification of test evidence per BSG-VA paper.

    Each value is the canonical string used in JSONL / logs.
    """

    GOLD_ALIGNED = "gold_aligned"
    """Fail on B, Pass on S AND G — test truly checks the bug."""

    REGRESSION_ONLY = "regression_only"
    """Pass on B AND S — test doesn't check bug, only proves no regression."""

    MISLEADING = "misleading"
    """Pass on B AND S (same as regression-only but flagged as evidence-fake).

    Specifically: b_pass=T, s_pass=T, g_pass=F — test passes on B and S but
    FAILS on Gold, meaning the test is actively wrong / faked-evidence.
    """

    CANDIDATE_SPECIFIC = "candidate_specific"
    """Fail B, Pass S, Fail G — agent's fix differs from gold."""

    DIAGNOSTIC_NEGATIVE = "diagnostic_negative"
    """Fail on S — patch didn't work, or regression introduced."""


# Roles where test actually discriminates between buggy and fixed code.
# Used for `discriminating` flag in ReplayResult.
_DISCRIMINATING_ROLES: frozenset[EvidenceRole] = frozenset({
    EvidenceRole.GOLD_ALIGNED,
    EvidenceRole.CANDIDATE_SPECIFIC,
    EvidenceRole.DIAGNOSTIC_NEGATIVE,
})


# ============================================================
# ReplayResult — output of classify_evidence.
# ============================================================
@dataclass
class ReplayResult:
    """Result of replaying a test command on 3 code states (B/S/G)."""

    role: EvidenceRole
    b_result: tuple[bool, str]
    """Test result on Buggy code: (passed, last_200_chars_output)."""

    s_result: tuple[bool, str]
    """Test result on candidate State code: (passed, last_200_chars_output)."""

    g_result: tuple[bool, str]
    """Test result on Gold code: (passed, last_200_chars_output)."""

    test_command: str
    discriminating: bool = field(init=False)

    def __post_init__(self) -> None:
        self.discriminating = self.role in _DISCRIMINATING_ROLES

    def to_dict(self) -> dict:
        """Serialize to dict for JSON logging."""
        return {
            "role": self.role.value,
            "b_pass": self.b_result[0],
            "s_pass": self.s_result[0],
            "g_pass": self.g_result[0],
            "b_snippet": self.b_result[1],
            "s_snippet": self.s_result[1],
            "g_snippet": self.g_result[1],
            "test_command": self.test_command,
            "discriminating": self.discriminating,
        }

    def __str__(self) -> str:
        return (
            f"ReplayResult(role={self.role.value}, "
            f"b={'PASS' if self.b_result[0] else 'FAIL'}, "
            f"s={'PASS' if self.s_result[0] else 'FAIL'}, "
            f"g={'PASS' if self.g_result[0] else 'FAIL'}, "
            f"discriminating={self.discriminating})"
        )


# ============================================================
# Bug signature helper — sha256(bug_type + description).
# ============================================================
def compute_bug_signature(bug_type: str, description: str) -> str:
    """Compute canonical bug signature = sha256(bug_type + ':' + description).

    Used as key to look up gold fix in GoldDataset.
    """
    raw = f"{bug_type}:{description}".encode()
    return hashlib.sha256(raw).hexdigest()


# ============================================================
# GoldDataset — JSONL-backed map of bug_signature → gold fix.
# ============================================================
class GoldDataset:
    """JSONL-backed dataset mapping bug_signature → gold fix source.

    Each line in dataset_path is a JSON object:
        {
            "bug_signature": "<sha256>",
            "bug_type": "RUF012",
            "description": "mutable class default",
            "buggy_source": "...",
            "gold_source": "...",
            "test_command": "python -c ..."
        }
    """

    def __init__(self, dataset_path: str = "data/gold_dataset.jsonl") -> None:
        self.dataset_path = Path(dataset_path)
        # Cache: bug_signature → entry dict (loaded lazily).
        self._cache: dict[str, dict] | None = None

    # --- internal ---
    def _load(self) -> dict[str, dict]:
        """Lazily load all entries from JSONL into a dict keyed by signature."""
        if self._cache is not None:
            return self._cache
        cache: dict[str, dict] = {}
        if self.dataset_path.exists():
            try:
                with self.dataset_path.open("r", encoding="utf-8") as f:
                    for line_no, raw in enumerate(f, start=1):
                        line = raw.strip()
                        if not line:
                            continue
                        try:
                            entry = json.loads(line)
                        except json.JSONDecodeError as e:
                            logger.warning(
                                f"[BSG-VA] gold_dataset: skip malformed line "
                                f"{line_no}: {e}"
                            )
                            continue
                        sig = entry.get("bug_signature")
                        if sig:
                            cache[sig] = entry
            except OSError as e:
                logger.warning(f"[BSG-VA] gold_dataset load failed: {e}")
        self._cache = cache
        return cache

    # --- public API ---
    def get_gold_fix(self, bug_signature: str) -> str | None:
        """Return gold fix source for a bug_signature, or None if not present."""
        entry = self._load().get(bug_signature)
        if entry is None:
            return None
        return entry.get("gold_source")

    def get_entry(self, bug_signature: str) -> dict | None:
        """Return full entry (with test_command, buggy_source) for signature."""
        return self._load().get(bug_signature)

    def add_entry(
        self,
        bug_signature: str,
        buggy_source: str,
        gold_source: str,
        test_command: str,
        bug_type: str = "",
        description: str = "",
    ) -> None:
        """Append a new entry to the JSONL dataset.

        NOTE: does NOT update the in-memory cache (caller should re-instantiate
        or call _load() with cache cleared if they need to read it back).
        """
        self.dataset_path.parent.mkdir(parents=True, exist_ok=True)
        entry = {
            "bug_signature": bug_signature,
            "bug_type": bug_type,
            "description": description,
            "buggy_source": buggy_source,
            "gold_source": gold_source,
            "test_command": test_command,
        }
        with self.dataset_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        # Invalidate cache so next _load() picks up the new entry.
        self._cache = None

    def list_entries(self) -> list[dict]:
        """Return all entries in the dataset (as list of dicts)."""
        return list(self._load().values())


# ============================================================
# EvidenceReplay — run test on B/S/G code states, classify role.
# ============================================================
class EvidenceReplay:
    """Replay a test command on 3 code states (Buggy / candidate State / Gold),
    classify the test evidence into one of 5 EvidenceRole values per BSG-VA.
    """

    def __init__(self, working_dir: str = ".") -> None:
        self.working_dir = Path(working_dir)

    # --- subprocess runner ---
    def run_test(self, test_command: str, cwd: str = ".") -> tuple[bool, str]:
        """Run a test command via subprocess, return (passed, last_200_chars).

        Fail-open: any error (timeout, OSError, etc.) → return (False, err_msg).
        DNA #7: never raise out of this method.

        [SCP-DNA-FIX R13-5] Bug #4: previously used shell=True with
        test_command, claiming the command was "trusted" (from gold dataset
        or operator). However, the surrounding EvidenceReplay flow
        substitutes `Path(file_path).stem` into shell-quoted contexts
        (via test_command templates), and file_path ultimately comes from
        the bug report / fix pipeline — which CAN be attacker-influenced
        (e.g. a fix targeted at a file with a maliciously-crafted name).
        bandit B602 (subprocess_popen_with_shell_equals_true) flagged this.
        Fix: shell=False + shlex.split(test_command) so subprocess receives
        a tokenized argv list (no shell parsing at all). Also reject
        file_path containing shell metacharacters in classify_evidence
        (defense-in-depth).
        """
        try:
            # Use shell=False + shlex.split to safely tokenize the command.
            # shlex.split handles `python -c "..."` style commands with
            # nested quotes correctly (produces ['python', '-c', '...']).
            # If the command is already a list, use it as-is.
            if isinstance(test_command, list | tuple):
                argv = [str(a) for a in test_command]
            elif sys.platform.startswith("win"):
                # POSIX shlex treats backslashes as escape characters and turns
                # a Windows executable path into `C:Users...`. Parse with
                # Windows-preserving mode, then remove only the outer quotes
                # that quote a complete argv token. Keep shell=False: this is
                # tokenization, not shell execution.
                argv = shlex.split(test_command, posix=False)
                argv = [
                    token[1:-1]
                    if len(token) >= 2 and token[0] == token[-1] and token[0] in {"'", '"'}
                    else token
                    for token in argv
                ]
            else:
                argv = shlex.split(test_command)
            if not argv:
                return False, "[empty test_command after shlex.split]"
            win_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if sys.platform == "win32" else 0
            result = subprocess.run(
                argv,
                shell=False,
                cwd=cwd,
                capture_output=True,
                text=True,
                timeout=_MAX_TEST_TIME_S,
                creationflags=win_flags,
            )
            output = (result.stdout or "") + (result.stderr or "")
            snippet = output[-_OUTPUT_SNIPPET_LEN:] if output else ""
            passed = result.returncode == 0
            return passed, snippet
        except subprocess.TimeoutExpired:
            return False, f"[TIMEOUT after {_MAX_TEST_TIME_S}s]"
        except FileNotFoundError as e:
            return False, f"[FileNotFoundError: {e}]"
        except ValueError as e:
            # shlex.split raises ValueError on malformed quotes.
            return False, f"[ValueError (bad shlex): {e}]"
        except OSError as e:
            return False, f"[OSError: {e}]"
        except Exception as e:  # noqa: BLE001 — fail-open per DNA #7
            return False, f"[{type(e).__name__}: {e}]"

    # --- classification ---
    @staticmethod
    def _classify(b_pass: bool, s_pass: bool, g_pass: bool) -> EvidenceRole:
        """Classify evidence role based on (b_pass, s_pass, g_pass) per BSG-VA Table.

        Truth table (8 cases):
            b s g → role
            F T T → GOLD_ALIGNED
            T T T → REGRESSION_ONLY  (test doesn't check bug, all pass)
            F T F → CANDIDATE_SPECIFIC
            T T F → MISLEADING        (passes B+S but fails G — evidence-fake)
            F F * → DIAGNOSTIC_NEGATIVE (candidate didn't work)
            T F * → DIAGNOSTIC_NEGATIVE (regression introduced by candidate)
            (any other unhandled case → DIAGNOSTIC_NEGATIVE as safe default)
        """
        # Order matters — check most specific cases first.
        if not b_pass and s_pass and g_pass:
            return EvidenceRole.GOLD_ALIGNED
        if b_pass and s_pass and g_pass:
            return EvidenceRole.REGRESSION_ONLY
        if b_pass and s_pass and not g_pass:
            return EvidenceRole.MISLEADING
        if not b_pass and s_pass and not g_pass:
            return EvidenceRole.CANDIDATE_SPECIFIC
        # Remaining: s_pass=False (regardless of b/g) → DIAGNOSTIC_NEGATIVE.
        # Also catches any uncovered combination as safe default.
        return EvidenceRole.DIAGNOSTIC_NEGATIVE

    # --- main entrypoint ---
    def classify_evidence(
        self,
        test_command: str,
        buggy_source: str,
        candidate_source: str,
        gold_source: str,
        file_path: str,
    ) -> ReplayResult:
        """Replay test_command on 3 code states, classify evidence role.

        Args:
            test_command: Shell command to run as test (e.g. ``python -c "..."``).
            buggy_source: Source code of the BUGGY version (state B).
            candidate_source: Source code of the CANDIDATE fix (state S).
            gold_source: Source code of the GOLD fix (state G).
            file_path: Path (relative to working_dir or absolute) of file to
                write each version to before running test_command.

        Returns:
            ReplayResult with role, per-state results, and discriminating flag.

        Side effects:
            - Backs up current file_path content (or notes if it didn't exist).
            - Writes each version to file_path in turn, runs test_command.
            - ALWAYS restores original file content (or deletes if not existed)
              via try/finally — DNA #9 (No harm).

        [SCP-DNA-FIX R13-5] Bug #4 (continued): classify_evidence is the
        only entrypoint where file_path enters the subprocess flow. We
        validate it here (fail-closed on shell metacharacters) so that
        even if a future caller passes a malicious path, the subprocess
        can't be subverted. See _SHELL_METACHAR_BLACKLIST above.
        """
        # [SCP-DNA-FIX R13-5] Bug #4: validate file_path against shell
        # metacharacters. Even though we now use shell=False + shlex.split
        # in run_test, file_path may STILL be substituted into test_command
        # templates by callers (e.g. `python -c "import {stem}"`), so a
        # path containing shell metacharacters remains a risk. Defense-
        # in-depth: reject any path containing shell metacharacters.
        if file_path and any(c in _SHELL_METACHAR_BLACKLIST for c in file_path):
            bad_chars = sorted(set(c for c in file_path if c in _SHELL_METACHAR_BLACKLIST))
            logger.error(
                f"[BSG-VA] REJECTED file_path with shell metacharacters: "
                f"{file_path!r} (contains {bad_chars}) — fail-closed "
                f"(DNA #4 Constitution KILL — no shell injection vector)"
            )
            return ReplayResult(
                role=EvidenceRole.DIAGNOSTIC_NEGATIVE,
                b_result=(False, "[file_path rejected: shell metacharacters]"),
                s_result=(False, "[file_path rejected: shell metacharacters]"),
                g_result=(False, "[file_path rejected: shell metacharacters]"),
                test_command=test_command,
            )
        target = Path(file_path)
        if not target.is_absolute():
            target = self.working_dir / target
        cwd = str(target.parent)
        module_name = target.stem

        # Backup current file (DNA #9: must restore after replay).
        backup_existed = target.exists()
        backup_content: str | None = None
        if backup_existed:
            try:
                backup_content = target.read_text(encoding="utf-8", errors="replace")
            except OSError as e:
                logger.warning(f"[BSG-VA] cannot backup {target}: {e}")
                backup_content = None

        try:
            # State B: buggy
            self._write_source(target, buggy_source)
            b_result = self.run_test(test_command, cwd=cwd)
            logger.debug(
                f"[BSG-VA] B state ({module_name}): "
                f"{'PASS' if b_result[0] else 'FAIL'}"
            )

            # State S: candidate
            self._write_source(target, candidate_source)
            s_result = self.run_test(test_command, cwd=cwd)
            logger.debug(
                f"[BSG-VA] S state ({module_name}): "
                f"{'PASS' if s_result[0] else 'FAIL'}"
            )

            # State G: gold
            self._write_source(target, gold_source)
            g_result = self.run_test(test_command, cwd=cwd)
            logger.debug(
                f"[BSG-VA] G state ({module_name}): "
                f"{'PASS' if g_result[0] else 'FAIL'}"
            )

            # Classify.
            role = self._classify(b_result[0], s_result[0], g_result[0])
            result = ReplayResult(
                role=role,
                b_result=b_result,
                s_result=s_result,
                g_result=g_result,
                test_command=test_command,
            )
            logger.info(f"[BSG-VA] classify_evidence: {result}")
            return result
        finally:
            # DNA #9: ALWAYS restore original file content.
            self._restore(target, backup_existed, backup_content)

    # --- helpers ---
    @staticmethod
    def _invalidate_bytecode_cache(target: Path) -> None:
        """Remove bytecode for target so B/S/G replay cannot read stale code."""
        candidates = [target.with_suffix(".pyc")]
        cache_dir = target.parent / "__pycache__"
        if cache_dir.exists():
            candidates.extend(cache_dir.glob(f"{target.stem}.*.pyc"))
        for cached in candidates:
            try:
                cached.unlink(missing_ok=True)
            except OSError as exc:
                logger.warning(f"[BSG-VA] bytecode cache cleanup failed {cached}: {exc}")

    @staticmethod
    def _write_source(target: Path, source: str) -> None:
        """Write source to target file (UTF-8), invalidating stale bytecode."""
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(source, encoding="utf-8")
            EvidenceReplay._invalidate_bytecode_cache(target)
        except OSError as e:
            logger.error(f"[BSG-VA] write failed {target}: {e}")

    @staticmethod
    def _restore(
        target: Path, backup_existed: bool, backup_content: str | None
    ) -> None:
        """Restore original file content (or delete if didn't exist)."""
        try:
            if backup_existed and backup_content is not None:
                target.write_text(backup_content, encoding="utf-8")
            elif not backup_existed:
                # File didn't exist before replay → remove it (DNA #9).
                if target.exists():
                    target.unlink()
        except OSError as e:
            logger.error(f"[BSG-VA] restore failed {target}: {e}")


__all__ = [
    "EvidenceRole",
    "ReplayResult",
    "GoldDataset",
    "EvidenceReplay",
    "compute_bug_signature",
]


# ============================================================
# Smoke test — synthetic B/S/G triple, run classify_evidence.
# ============================================================
if __name__ == "__main__":  # pragma: no cover — smoke test
    import tempfile

    print("=" * 70)
    print("[BSG-VA smoke test] synthetic buggy/candidate/gold triple")
    print("=" * 70)

    with tempfile.TemporaryDirectory(prefix="bsgva_smoke_") as tmpdir:
        work = Path(tmpdir)
        module_path = work / "smoke_module.py"

        # Synthetic bug: function should return 1.
        # - Buggy: returns 0 (test will fail).
        # - Candidate: returns 1 (test passes — matches gold).
        # - Gold: returns 1 (canonical fix).
        buggy_src = "def answer() -> int:\n    return 0\n"
        candidate_src = "def answer() -> int:\n    return 1\n"
        gold_src = "def answer() -> int:\n    return 1\n"

        test_cmd = (
            f'{sys.executable} -c "from smoke_module import answer; '
            f'assert answer() == 1, \'answer must be 1\'"'
        )

        replay = EvidenceReplay(working_dir=str(work))
        result = replay.classify_evidence(
            test_command=test_cmd,
            buggy_source=buggy_src,
            candidate_source=candidate_src,
            gold_source=gold_src,
            file_path=str(module_path),
        )

        print(f"test_command : {test_cmd}")
        print(f"file_path    : {module_path}")
        print(f"buggy_src    : {buggy_src!r}")
        print(f"candidate_src: {candidate_src!r}")
        print(f"gold_src     : {gold_src!r}")
        print()
        print(f"ReplayResult : {result}")
        print(f"  role           : {result.role.value}")
        print(f"  b_result       : pass={result.b_result[0]}, snippet={result.b_result[1]!r}")
        print(f"  s_result       : pass={result.s_result[0]}, snippet={result.s_result[1]!r}")
        print(f"  g_result       : pass={result.g_result[0]}, snippet={result.g_result[1]!r}")
        print(f"  discriminating : {result.discriminating}")
        print(f"  to_dict        : {result.to_dict()}")

        # Verify role is one of 5 EvidenceRole values.
        valid_roles = {r for r in EvidenceRole}
        assert result.role in valid_roles, (
            f"smoke test FAIL: role {result.role!r} not in EvidenceRole"
        )
        # For this specific triple (F, T, T) → GOLD_ALIGNED.
        expected_role = EvidenceRole.GOLD_ALIGNED
        assert result.role == expected_role, (
            f"smoke test FAIL: expected {expected_role.value}, "
            f"got {result.role.value} "
            f"(b={result.b_result[0]}, s={result.s_result[0]}, g={result.g_result[0]})"
        )
        assert result.discriminating is True, (
            "smoke test FAIL: GOLD_ALIGNED should be discriminating"
        )

        print()
        print(f"[SMOKE TEST PASS] role={result.role.value} (expected GOLD_ALIGNED)")
        print(f"[SMOKE TEST PASS] discriminating={result.discriminating} (expected True)")

        # Also verify file was restored (didn't exist before — should be gone).
        assert not module_path.exists(), (
            "smoke test FAIL: file_path should be removed after replay (DNA #9)"
        )
        print(f"[SMOKE TEST PASS] file_path restored (no longer exists: {not module_path.exists()})")

    # Quick sanity: also verify GoldDataset loads the seeded file (if present).
    print()
    print("=" * 70)
    print("[BSG-VA smoke test] GoldDataset round-trip")
    print("=" * 70)
    with tempfile.TemporaryDirectory(prefix="bsgva_gold_") as tmpdir:
        ds_path = Path(tmpdir) / "gold.jsonl"
        ds = GoldDataset(dataset_path=str(ds_path))

        sig = compute_bug_signature("RUF012", "mutable class default")
        ds.add_entry(
            bug_signature=sig,
            buggy_source="class X:\n    items = {}\n",
            gold_source="from dataclasses import dataclass, field\n\n@dataclass\nclass X:\n    items: dict = field(default_factory=dict)\n",
            test_command='python -c "from module import X"',
            bug_type="RUF012",
            description="mutable class default",
        )

        entries = ds.list_entries()
        assert len(entries) == 1, f"expected 1 entry, got {len(entries)}"
        assert ds.get_gold_fix(sig) is not None, "gold fix not retrievable"
        # Fresh instance to verify reload from disk.
        ds2 = GoldDataset(dataset_path=str(ds_path))
        assert ds2.get_gold_fix(sig) is not None, "gold fix not persisted to disk"
        print("[SMOKE TEST PASS] GoldDataset add_entry + get_gold_fix round-trip OK")
        print(f"  entries: {len(entries)}")
        print(f"  signature: {sig[:16]}...")

    print()
    print("=" * 70)
    print("[BSG-VA smoke test] ALL PASS")
    print("=" * 70)
