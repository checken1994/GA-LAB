# Architectural Analysis: R6 AutoFix Rollback & Cognitive Loop Perfect Isolation

**Date**: 2026-09-08  
**Investigator**: Explorer R6 (`teamwork_preview_explorer`)  
**Scope**: AutoFix Engine, Cognitive Loop, AST Mutator, Patch Application, Verification Gates, Snapshot/Rollback Mechanisms, and Peripheral Gaps (FA-11).

---

## 1. Executive Summary

Autonomous code modification in SCP is distributed across three primary subsystems:
1. **AutoFixEngine** (`scp/autofix/engine.py`, `autofix_mixin.py`, `verify_mixin.py`, `engine_extensions.py`)
2. **CodeEvolutionAgent** (`scp/core/code_evolution_agent.py`)
3. **Cognitive Loop & Orchestrator** (`scp/knowledge/cognitive_orchestrator.py`, `evolution.py`)

**Core Vulnerability (R6)**:
The current codebase lacks atomic, crash-resilient snapshot isolation. When a patch is applied:
- Pre-patch backups are stored primarily in volatile Python process RAM (`ctx.pre_fix_content: str` in `autofix_mixin.py:324`, `backup: str` in `code_evolution_agent.py:241`).
- Physical disk backups, when made, are scattered as ad-hoc artifacts directly inside the source code tree (`.tier3bak`, `.tier3bak.<token>`, `.branch{i}.bak`), violating the **Clean Workspace** mandate and leaving source trees vulnerable to disk pollution.
- The pytest verification gate in `verify_mixin.py:162` is **disabled by default** (`SCP_AUTOFIX_RUN_PYTEST == "0"`), only points to single source files instead of actual test suites, and explicitly catches all exceptions **fail-open** (`logger.debug("pytest verify fail-open")`).
- In `_auto_approve_tier3` (`engine.py:657-684`), when a post-patch Reality Test encounters a `SyntaxError`, the failure is merely recorded in an audit string (`_reality_test_result = "FAIL:SyntaxError:..."`) while the engine proceeds to declare the bug `fixed` without rolling back.
- If a background worker, pytest run, or external host process crashes, hangs, or is terminated (OOM, SIGKILL, power outage), the in-memory backup is wiped out, leaving the codebase corrupted on disk with no boot-time reconciliation.

---

## 2. Inventory of Investigated Files & Components

| Component | File Path | Line Range | Architectural Role | Current Rollback & Isolation Status |
|---|---|---|---|---|
| **AutoFixEngine Core** | `scp/autofix/engine.py` | 172–307 | Main engine class, tier dispatching | No direct rollback; delegates to mixins; tier3 auto-approve ignores reality test failure |
| **Tier-3 Auto-Approve** | `scp/autofix/engine.py` | 579–685 | Autonomous Tier-3 patching | Creates `.tier3bak.<token>` beside source; logs reality test `FAIL` without rolling back |
| **AutoFix Lifecycle Mixin** | `scp/autofix/engine_parts/autofix_mixin.py` | 18–49, 315–370, 1035–1350 | Three-part autofix pipeline | Relies on RAM string `ctx.pre_fix_content`; ad-hoc `.tier3bak` copy; in-memory rollback |
| **Verification Gate Mixin** | `scp/autofix/engine_parts/verify_mixin.py` | 150–231 | Post-patch pytest & AST verification | Pytest gate disabled by default (`SCP_AUTOFIX_RUN_PYTEST=="0"`); fails open on exception |
| **AST Mutator & Evolver** | `scp/core/code_evolution_agent.py` | 240–345 | Applies search/replace & AST patches | Writes directly to disk; restores from RAM `backup: str`; commits unvetted git changes |
| **Rollback Registry** | `scp/autofix/rollback_registry.py` & `engine_extensions.py` | 58–110, 59–300 | Public rollback API & token storage | Post-hoc manual rollback only; does not catch in-flight crashes or automatic test failures |
| **Dry-Run Manager** | `scp/autofix/engine_extensions.py` | 319–469 | Generates diffs in `/tmp/` | Preview only; bypassed by standard `_auto_fix` and `CodeEvolutionAgent` |
| **Shadow Canary** | `scp/autofix/runner_phases/shadow_canary.py` | 100–180, 426–478 | Pre-apply smoke execution in `data/shadow` | Pre-apply canary only; does not protect real file once written |
| **Auto-Rollback Watcher** | `scp/autofix/runner_phases/auto_rollback.py` | 106–243, 288–370 | Background 60s reality test re-verifier | Only tests callable dummy inputs; does not run pytest; fail-open on worker crash |
| **Cognitive Orchestrator** | `scp/knowledge/cognitive_orchestrator.py` | 12–81 | Epistemic learning loop driver | Pure skeleton; methods `_process_stale_knowledge`, `_process_lessons` are empty `pass` |
| **Speculative Branching** | `scp/autofix/speculative_branching.py` | 5–31 | Multi-patch candidate race prototype | Dead code; mutates host file directly with `.branch{i}.bak` without sandboxing |

---

## 3. Line-by-Line Call Graph (Navigation Map)

### Flow A: AutoFix Execution & Missing Rollback Invariant
```text
[1] scp/autofix/runner.py:395
    └── process_bug_with_llm(bug, engine, allow_llm=...)
        └── [2] scp/autofix/llm_fix_parts/process_bug_with_llm.py:37 / 44 / 53 / 70 / 124 / 146
            └── autofix_engine.process_bug(bug)
                └── [3] scp/autofix/engine.py:231
                    ├── classify tier (Line 244)
                    ├── if Tier 1/2/4: self._auto_fix(classified, ...) (Lines 286, 289, 304)
                    └── if Tier 3: self._request_permission(classified) (Line 292)
                        └── [Option: Tier 3 Auto-Approve] scp/autofix/engine.py:579
                            ├── bak_path = filepath.suffix + f".tier3bak.{_rollback_token}" (Line 625)
                            │   └── ⚠️ GAP: Writes backup inside source tree
                            ├── result = self._auto_fix(bug, report=True) (Line 636)
                            └── reality_test (ast.parse) (Lines 653-667)
                                └── ⚠️ GAP: If SyntaxError: _reality_test_result = "FAIL:..."
                                    └── Line 684: returns result anyway without rollback!
```

### Flow B: Deep Dive into `_auto_fix` (`autofix_mixin.py`)
```text
[4] scp/autofix/engine_parts/autofix_mixin.py:18
    ├── Line 21: ctx = FixContext(bug, filepath=Path(bug.file), ...)
    ├── Line 28: res = self._auto_fix_gates(ctx)
    │   └── checks _is_protected_path, capability, policy_gate
    ├── Line 32: res = self._auto_fix_part1(ctx)
    │   ├── Line 317: ctx.pre_fix_content = None
    │   ├── Line 324: ctx.pre_fix_content = _pre_fix_file.read()
    │   │   └── ⚠️ GAP: Backup stored ONLY in Python RAM variable
    │   └── Line 344: XSS pattern fix writes directly: filepath.write_text(...)
    │       └── Line 367: If syntax error: filepath.write_text(ctx.pre_fix_content) (RAM restore)
    ├── Line 35: res = self._auto_fix_part2(ctx)
    │   └── Line 957: _v4_shadow_compare(...) in shadow_canary.py (pre-apply temp check)
    └── Line 38: res = self._auto_fix_part3(ctx)
        ├── Line 1047: agent = CodeEvolutionAgent.__new__(CodeEvolutionAgent)
        ├── Line 1095: verify_patch_realtime(...)
        ├── Line 1144: bak_path = filepath.with_suffix(filepath.suffix + ".tier3bak")
        ├── Line 1145: shutil.copy2(filepath, bak_path)
        │   └── ⚠️ GAP: Clobbers any existing .tier3bak; clutters source repo
        ├── Line 1146: patched = agent._apply_fix(filepath, ctx.bug.suggested_fix)
        │   └── [5] scp/core/code_evolution_agent.py:293
        │       └── Line 314 / 339: self._write_if_safe(filepath, original, patched)
        │           ├── Line 271: ast.parse(patched)
        │           ├── Line 275: self._drift_allows(...)
        │           └── Line 277: filepath.write_text(patched, encoding="utf-8")
        │               └── 🚨 PHYSICAL DISK WRITE TO REPOSITORY SOURCE CODE
        ├── Line 1197: _verify_ok, _verify_reason = self._verify_fix(filepath, [ctx.bug])
        │   └── [6] scp/autofix/engine_parts/verify_mixin.py:150
        │       ├── Line 162: if os.environ.get("SCP_AUTOFIX_RUN_PYTEST", "0") == "1":
        │       │   └── 🚨 CRITICAL: Disabled by default! Pytest NEVER runs unless env is set!
        │       ├── Line 176: [_sys.executable, "-m", "pytest", "-q", "--timeout=60", str(filepath)]
        │       │   └── 🚨 GAP: Runs pytest on the Python SOURCE file, not test suite!
        │       ├── Line 191: _backup_path = filepath.with_suffix(".tier3bak")
        │       ├── Line 228: if not exists -> skip (fail-open)
        │       └── Line 229-230: except Exception as _pytest_err: logger.debug("fail-open")
        │           └── 🚨 VIOLATION (FA-01): Catches all errors and treats as PASS!
        ├── Line 1198: if not _verify_ok:
        │   └── Line 1210: filepath.write_text(ctx.pre_fix_content, encoding="utf-8", newline="")
        │       └── ⚠️ GAP: Restore from RAM string. If process crashed during Line 1146-1197, corruption is permanent!
        ├── Line 1261: run_full_post_fix_verify(...)
        │   └── if not ok: lines 1282, 1321, 1335, 1349 restore from ctx.pre_fix_content
        └── Line 1497: self.register_fix_for_rollback(...)
            └── Line 1515: RegressionWatcher.register(..., ttl=60)
                └── ⚠️ GAP: Only runs callable smoke-test, never pytest; fail-open on error.
```

### Flow C: CodeEvolutionAgent Standalone Loop
```text
[7] scp/core/code_evolution_agent.py:72
    └── run_cycle()
        ├── Line 97: backup = self._backup_file(filepath)
        │   └── Line 241: return filepath.read_text(encoding="utf-8") (RAM only)
        ├── Line 98: actually_patched = self._apply_fix(filepath, fix) -> MUTATES FILE ON DISK
        ├── Line 112: test_result = self._run_tests()
        │   └── Line 371: subprocess.run([sys.executable, "-m", "pytest", str(self.tests_dir), ...])
        ├── Line 113: if test_result["passed"]:
        │   └── Line 115: self._commit_fix(bug, fix, test_result)
        │       └── 🚨 DANGEROUS: Executes `git add -A` and `git commit` directly!
        └── Line 125: else:
            └── Line 126: self._restore_backup(filepath, backup)
                └── Line 365: filepath.write_text(backup, encoding="utf-8") (RAM restore)
```

---

## 4. Architectural Analysis of the Gaps

### Gap 1: In-Memory Volatility & Crash Vulnerability
Both `AutoFixMixin` and `CodeEvolutionAgent` read the pre-patch content into a Python `str` in memory. If any of the following events occur between `_apply_fix` and `_restore_backup`:
- OS process kill (`SIGKILL`, Windows `taskkill`)
- Memory exhaustion (`MemoryError`, OOM Killer)
- Unhandled `SystemExit` from an imported or tested module
- Pytest hanging and receiving external termination
- System power interruption
The RAM string evaporates. The target file on the host filesystem is left in a half-patched, syntactically broken, or semantically corrupted state. No journal or marker remains on disk to indicate that a transaction was underway.

### Gap 2: Ad-Hoc In-Tree Backups Violate Clean Workspace
Current code produces:
- `foo.py.tier3bak`
- `foo.py.tier3bak.<uuid>`
- `foo.py.audit_fix_backup`
- `foo.py.evolutionbak`
- `foo.py.branch{i}.bak`
- `foo.py.dryrunbak`
These files are placed in the same directory as production source files (`scp/`, `dashboard/`, etc.). This causes:
1. Linters (flake8, ruff, mypy) scanning directories to flag syntax errors or duplicate definitions in backup files.
2. Git status to be dirty unless complex `.gitignore` entries exist.
3. Multiple successive fixes on the same file to clobber earlier backups.

### Gap 3: Broken Pytest Gate in `verify_mixin.py`
In `scp/autofix/engine_parts/verify_mixin.py:150-231`:
```python
if os.environ.get("SCP_AUTOFIX_RUN_PYTEST", "0") == "1":
    ...
    _proc = _sp.run([_sys.executable, "-m", "pytest", "-q", "--timeout=60", str(filepath)], ...)
    ...
except Exception as _pytest_err:
    logger.debug(f"[WORLD-CLASS-GATE] pytest verify fail-open: {_pytest_err}")
```
1. **Disabled by default**: Since `SCP_AUTOFIX_RUN_PYTEST` is `"0"` unless specifically set, AutoFix runs with ZERO pytest verification.
2. **Target Mismatch**: Passing `str(filepath)` (e.g. `scp/autofix/engine.py`) to pytest does not execute unit tests or regression tests—it merely attempts to discover test functions inside a production module!
3. **Fail-Open Policy**: Any unexpected crash, timeout, or environment error silently falls through as a pass, directly violating **FA-01** and DNA Principle #7 / Fail-Closed.

### Gap 4: Lack of Transactional Multi-File Atomicity
If a bug requires modifying multiple files (or touches imports across modules), AutoFix applies them sequentially. If file 1 succeeds and file 2 fails verification, file 2 is rolled back in RAM, but file 1 remains permanently altered on disk.

### Gap 5: No Boot-Time Crash Recovery Reconciler
There is no startup hook that scans for interrupted patching transactions and rolls them back before accepting tasks.

---

## 5. Detailed Design for Snapshot / Rollback (R6 Remediation)

To provide **perfect isolation and crash durability** at the filesystem/database boundary without relying on RAM variables, we design the **Shadow Snapshot Transaction Manager (`ShadowSnapshotManager`)**:

### Directory Structure
```
data/shadow/
├── active/                         # In-flight transactions
│   └── <tx_id>/
│       ├── manifest.json           # Atomic status journal (fsynced)
│       ├── files/                  # Byte-exact pre-patch copies
│       │   └── <relative_path>.bak
│       └── lock.pid                # Process ownership lock
├── completed/                      # Successfully committed transactions
│   └── <tx_id>/
│       └── manifest.json           # Kept for auditing and manual rollback
└── rolled_back/                    # Rolled-back transactions with failure logs
    └── <tx_id>/
        ├── manifest.json
        ├── failure_reason.txt
        └── test_stdout_stderr.log
```

### Manifest Schema (`manifest.json`)
```json
{
  "tx_id": "tx_20260908_193000_abc123",
  "created_at": 1788879000.123,
  "status": "PRE_PATCH", 
  "pid": 12345,
  "bug_id": "BareExceptPass:scp/utils.py:20",
  "tier": 2,
  "target_files": [
    {
      "repo_rel_path": "scp/utils.py",
      "absolute_path": "C:/Users/check/Downloads/scp/scp/utils.py",
      "backup_path": "data/shadow/active/tx_.../files/scp/utils.py.bak",
      "pre_sha256": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
      "post_sha256": null
    }
  ]
}
```

### State Machine Transitions (`status`):
`INIT` → `PRE_PATCH_STORED` → `PATCH_APPLIED` → `TESTING` → (`COMMITTED` | `ROLLED_BACK`)

### Transaction Lifecycle Workflow:

```
[Start AutoFix Transaction]
        │
        ▼
[1. ShadowSnapshotManager.begin(files, bug_id)]
   ├── Create data/shadow/active/<tx_id>/files/
   ├── Copy physical files to backup directory
   ├── Compute SHA-256 pre-hashes
   ├── Write manifest.json with status="PRE_PATCH_STORED"
   └── fsync manifest.json to disk
        │
        ▼
[2. Apply Patch via CodeEvolutionAgent / AST Mutator]
   ├── Write patch to target file(s)
   ├── Compute SHA-256 post-hashes
   ├── Update manifest.json with status="PATCH_APPLIED"
   └── fsync manifest.json
        │
        ▼
[3. Run Verification Pipeline]
   ├── Run AST syntax check
   ├── Run DriftGuard postflight
   ├── Run Reality Tests (exercise callables)
   └── Run Targeted Pytest (Fail-Closed, timeout=60s)
        │
     ┌──┴─────────────────────────┐
     │                            │
   [PASS]                       [FAIL / Crash / Timeout / Exception]
     │                            │
     ▼                            ▼
[4. Commit Transaction]         [5. Rollback Transaction (Atomic)]
   ├── Update manifest:           ├── For each file in manifest.target_files:
   │   status="COMMITTED"         │   ├── Copy from backup_path to temp file in target dir
   ├── Move directory to:         │   ├── Verify pre_sha256 on temp file
   │   data/shadow/completed/     │   ├── fsync temp file
   └── Register token with        │   └── os.replace(temp, target) [Atomic POSIX/Win32]
       RollbackTokenRegistry      ├── Update manifest: status="ROLLED_BACK"
                                  ├── Record test stdout/stderr and failure reason
                                  └── Move directory to data/shadow/rolled_back/<tx_id>/
```

### 6. Boot-Time Crash Recovery Reconciler (`recover_abandoned_snapshots()`)
During startup (e.g. `AutoFixEngine.__init__` or `pre_startup_audit`):
1. Scan `data/shadow/active/` for existing transaction directories.
2. For each transaction found:
   - Check if the owning PID is still alive. If PID is dead (or machine rebooted):
   - If status is `PATCH_APPLIED` or `TESTING`:
     - System crashed while a patch was active!
     - Immediately invoke `rollback_transaction(tx_id, reason="CRASH_RECOVERY_ABANDONED_TRANSACTION")`.
     - Restore all original files from `files/`.
     - Log critical audit event to `data/autofix_audit.jsonl`.
   - If status is `PRE_PATCH_STORED`:
     - Target was never touched; delete active directory.
3. This guarantees that **no bad patch can ever persist across a crash or restart**.

---

## 6. Peripheral Gaps (FA-11 Mandatory Audit)

In accordance with FA-11 (Mandatory Peripheral Audit & No Blind Eye), we conducted a peripheral scan of neighboring components around AutoFix and the Cognitive Loop:

```
                  ┌────────────────────────────────────────┐
                  │          AutoFix / Cognitive Loop       │
                  └───────────────────┬────────────────────┘
                                      │
        ┌─────────────────────────────┼─────────────────────────────┐
        ▼                             ▼                             ▼
[Gap R6-P01: Fail-Open]     [Gap R6-P02: In-Tree Junk]   [Gap R6-P03: Silent Pass]
verify_mixin.py:162, 229     .tier3bak, .branch{i}.bak     engine.py:657-684
pytest disabled & fail-open  pollutes source tree         SyntaxError ignored in Tier 3
        │                             │                             │
        ▼                             ▼                             ▼
[Gap R6-P04: RAM Volatility] [Gap R6-P05: Hollow Core]   [Gap R6-P06: Unvetted Commit]
RAM-only pre_fix_content    cognitive_orchestrator.py     code_evolution_agent.py:398
crashes leave bad code      5 empty `pass` stubs          blind `git add -A`
```

1. **Gap R6-P01 (Pytest Fail-Open)**: `verify_mixin.py:229` swallows all exceptions during pytest verification with `logger.debug("pytest verify fail-open")`.
2. **Gap R6-P02 (In-Tree Pollution)**: `.tier3bak`, `.audit_fix_backup`, and `.evolutionbak` files placed in source folders violate Clean Workspace rule.
3. **Gap R6-P03 (Tier-3 Silent Pass on Syntax Error)**: `engine.py:664` sets `_reality_test_result = "FAIL:SyntaxError:..."` but returns `action="fixed"`, promoting broken code.
4. **Gap R6-P04 (Speculative Branching False Isolation)**: `speculative_branching.py` claims "N containers", but actually writes directly to host `target_file` with `.branch{i}.bak`.
5. **Gap R6-P05 (Hollow Cognitive Loop)**: `cognitive_orchestrator.py` contains skeleton stubs for knowledge processing and benchmarks without executing real verification.
6. **Gap R6-P06 (Unvetted Git Commit in Evolution Agent)**: `code_evolution_agent.py:398` executes `git add -A` and `git commit` directly upon test pass, risking committing unrelated user files or debug artifacts.

---

## 7. Concrete Next Steps for Implementer

1. **Create `ShadowSnapshotManager`** in `scp/autofix/shadow_snapshot.py`:
   - Store snapshots in `data/shadow/active/<tx_id>/`.
   - Atomic replace via temp file + `fsync` + `os.replace`.
   - Automatic boot-time reconciliation in `AutoFixEngine.__init__`.
2. **Integrate into `autofix_mixin.py`**:
   - Wrap `_auto_fix_part3` with `with shadow_snapshot_manager.transaction([filepath], bug_id):`.
   - Remove ad-hoc `filepath.with_suffix(".tier3bak")` writes.
   - Remove dependence on `ctx.pre_fix_content`.
3. **Harden `verify_mixin.py`**:
   - Make pytest gate fail-closed: return `(False, "pytest regression / failure")` on non-zero exit or exception.
   - Map modified files to relevant tests in `tests/` instead of passing source files to pytest.
4. **Fix Tier-3 Auto-Approve**:
   - In `engine.py:657`, if `_reality_test_result` starts with `FAIL:`, immediately rollback and return `action="skipped"`.
5. **Integrate into `CodeEvolutionAgent`**:
   - Replace in-memory `_backup_file` string with `ShadowSnapshotManager`.
   - Remove raw `git add -A` from `_commit_fix`.
