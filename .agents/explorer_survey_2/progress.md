# Progress — Explorer Survey 2

Last visited: 2026-09-05T10:22:25Z

## Current Status
Initialized investigation. Beginning Deep Scan for:
1. FA-02 skip paths, xfails, conditional skips, commented/loosened assertions in `tests/` and `tools/`.
2. Epistemic EvidenceStore lifecycle, atomic staging, fsync/write barriers, crash recovery.

## Current Status
Deep scan underway:
1. FA-02 Skip Paths & Baseline Technical Debt:
   - Executed `tools/t00_meta_audit.py`: Confirmed 5 baseline debt findings in trusted_base:
     * `scp/tests/external_audit/test_security.py` -> 2 skips in `test_bandit_no_new_high_severity_via_bandit`
     * `scp/tests/external_audit/test_security.py` -> 1 skip in `test_no_hardcoded_token_in_source`
     * `tests/T03_capability/test_os_sandbox.py` -> 2 skips for non-Windows platforms
     * `scp/autofix/evidence_replay.py` -> hardcoded VERIFIED stub
   - Uncovered critical AST Blind Spots in `t00_meta_audit.py`:
     * `scp/tests/external_audit/conftest.py` modifies collection dynamically using `item.add_marker(pytest.mark.skip(...))` for missing ruff/bandit/grep, bypassing static AST analysis!
     * `scp/tests/property/test_none_safety.py` aliases `_HYPOTHESIS_SKIP = pytest.mark.skipif(...)`, escaping AST attribute detection!
     * `tests/reality-tests/*.py` catches broad `except Exception:` and prints `✓ Reality test ... PASSED` with exit code 0, turning fatal runtime crashes into false greens!
     * `scp/autofix/runner_phases/reality_test.py` declares `VERIFIED` as long as `callables_exercised >= 1`, ignoring failing callables in `exceptions`!
2. Epistemic EvidenceStore Lifecycle:
   - Analyzed `scp/epistemic/evidence_store.py`, `scp/persistence/db.py`, and `scp/epistemic/runtime_bridge.py`.
   - Verified crash-ordering: staging -> fsync -> atomic rename -> DB transaction.
   - Identified key vulnerabilities:
     * Orphan blob leaks on crash between atomic rename and DB commit (no automatic purge/reconciliation on startup).
     * Missing directory fsync on POSIX platforms.
     * Concurrency race in `__init__`: unlinking `.staging/*` during startup can destroy an active concurrent process's in-flight staging blob!
     * Default keyless mode uses plain sha256, allowing raw-SQL tampering if trigger is dropped.
     * `self.db._conn.commit()` called outside thread lock during error recording in `verify_integrity`.

## Steps
- [x] Read DISPATCH.md, ORIGINAL_REQUEST.md, GA.md
- [x] Read SKILL.md (scp-dna, scp-reality-verifier)
- [x] Initialize BRIEFING.md and progress.md
- [x] Scan for FA-02 skip paths in `tests/` and `tools/`
- [x] Analyze causal chains of skip/bypass mechanisms and false greens
- [x] Locate and analyze Epistemic EvidenceStore implementation and tests
- [x] Trace crash-ordering, atomic staging, journal append, write barriers, recovery lifecycle
- [x] Synthesize findings into handoff.md
- [x] Report to Orchestrator Parent via send_message
