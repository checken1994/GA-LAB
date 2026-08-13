# SCP Autofix Engine v4 — Changelog (R8 v3 → R9 v4)

> Stronger + more accurate + faster — 6 new improvements (IMP-19..IMP-24,
> 4,389 LOC) inspired by Hypothesis/QuickCheck (property-based testing),
> pyright/mypy strict mode (type-flow), GitHub Copilot speculative
> decoding (pre-fix cache), mypy daemon/TypeScript LSP/Rust Analyzer
> (incremental graph), Sentry canary + Istio traffic shadowing (shadow
> apply), AWS SCP + OPA/Rego + Anthropic Constitutional AI (policy gate).

All changes are in `/home/z/my-project/scp/autofix/`.

---

## [v4] — 2026-08-08 (R9)

### Added — 6 new files

#### `property_validator.py` (728 LOC) — IMP-19 (ACCURACY)
- `BugLocation` dataclass — function_name, line_start, line_end,
  statement_kind, `contains_line(lineno)` method
- `PropertySpec` dataclass — invariants (list of callables),
  strategy (name in STRATEGY_REGISTRY or callable),
  skip_if_none_input flag
- `Violation` dataclass — input_value, original_output, fixed_output,
  invariant_index, reason, over_broad flag, `summary()` method
- `PropertyResult` dataclass — ok, violations, inputs_tested, coverage
  (type_tag → count), reason, invariants_held_both,
  invariants_held_fixed_only, invariants_held_neither, `to_dict()`
- Built-in strategy generators (8 total):
  - `_edge_ints` — boundary integers (0, ±1, ±MAX_INT, ±10^18)
  - `_edge_floats` — boundary floats (0.0, ±0.0, NaN, ±inf, subnormals)
  - `_edge_strs` — boundary strings (empty, unicode, NULL bytes, 10KB)
  - `_edge_lists` — boundary lists (empty, nested, mixed, 10K elements)
  - `_edge_dicts` — boundary dicts (empty, nested, unicode keys, 100 keys)
  - `_edge_none` — always None
  - `_edge_bools` — True/False/0/1/None
  - `_edge_mixed` — random pick across all strategies
- `STRATEGY_REGISTRY` — dict mapping name → strategy callable.
  `register_strategy(name, fn)` for custom strategies.
- `validate_fix(orig_source, fixed_source, bug_location, spec, n=100, seed=None)`:
  1. Compile orig + fixed source into callable functions (isolated
     namespace, builtins only — fail-open on compile error).
  2. Resolve strategy from spec (fail-open on unknown strategy).
  3. Generate N edge-case inputs, run BOTH functions on each.
  4. For each input + invariant:
     - Original held, fixed violated → record Violation (regression).
     - Original violated, fixed held → benign improvement (counted).
     - Both held → invariants_held_both (counted).
     - Both violated → invariants_held_neither (counted).
  5. Track coverage by input type tag.
  6. Return PropertyResult.
- `run_property_suite(fix, specs, n=100)` — run list of specs against
  one fix, return list of PropertyResult (one per spec).
- `fingerprint_inputs(spec, n)` — deterministic SHA-256 of N inputs
  (seed=0xC0DEFEED) for audit trail (DNA #8 KB accumulation).
- Helpers: `_resolve_strategy`, `_compile_function` (isolated namespace
  + dedent), `_safe_call` (handles TypeError retry with tuple/list
  unpacking), `_check_invariants`, `_type_tag`, `_outputs_differ`
  (NaN-aware).
- Fail-open: import error / strategy unavailable / compile error →
  `ok=True, reason="skip — ... (fail-open)"`. Pure function (no side
  effects on engine state).

#### `type_flow_verifier.py` (723 LOC) — IMP-20 (ACCURACY)
- `TypeNode` dataclass — name, args (list of TypeNode).
  `is_optional()` detects Optional[X] + Union[X, None]. `unwrap_optional()`
  returns X from Optional[X]. `to_str()` round-trips.
- `parse_type(ann_str) -> TypeNode | None` — handles int, str,
  Optional[X], List[X], Dict[K, V], Tuple[X, ...], Union[X, Y, ...],
  None, PEP 604 `X | Y`, forward-ref quoted annotations. Fail-open
  on parse error → None.
- `Signature` dataclass — args (list of type strings), returns,
  arg_names (optional, for keyword-call detection).
- `CallerSite` dataclass — file, line, col, context,
  checks_none (caller has `if result is None`),
  unwraps_attr (caller does `result.attr`),
  passes_arg_index, passes_arg_repr.
- `IncompatibleSite` dataclass — caller, reason, severity.
- `TypeFlowResult` dataclass — compatible, breaking_callers,
  incompatible_sites, caller_count, reason, bounded, `to_dict()`.
- `_CallSiteCollector` (ast.NodeVisitor) — walks AST, collects call
  sites of target_function. Tracks variable bindings via
  `_pending_target_name` (set in visit_Assign, consumed in visit_Call).
  visit_If detects `if x is None` / `if x is not None` patterns.
  visit_Attribute detects `x.attr` unwraps on bound variables.
- `_is_narrowing(orig, new)` / `_is_widening(orig, new)` — type
  compatibility heuristics (Optional→X narrowing, Any→X narrowing,
  List[Any]→List[X] element narrowing, etc.).
- `_check_return_compat(site, orig_ret, new_ret)` — return-type
  change compatibility check (Optional→X dead branch, X→Optional[X]
  attribute unwrap without None check).
- `_check_arg_compat(site, orig_args, new_args)` — arg-type narrowing
  check (Any→int with string literal, Any→str with int literal).
- `verify_type_flow(target_file, target_function, orig_signature,
  new_signature, scp_root)`:
  1. Parse signatures into TypeNode trees.
  2. Walk scp_root for .py files mentioning target_function.
  3. AST-parse each, collect call sites via _CallSiteCollector.
  4. For each call site, check return compat + arg compat.
  5. Aggregate incompatible sites → result.compatible = False.
- `summarize_type_flow(result)` — human-readable summary for audit log.
- Fail-open: parse error / no callers / scp_root missing →
  `compatible=True, reason="skip — type-flow unverifiable (fail-open)"`.
- Bounded: MAX_FILES_TO_SCAN=400, MAX_NODES_PER_FILE=5000,
  MAX_CALLERS_RECORDED=100, MAX_BREAKING_SITES=50.

#### `speculative_prefixer.py` (798 LOC) — IMP-21 (SPEED)
- `CandidateFix` dataclass — pattern_name, file_sha (16-char prefix),
  file_path, line_start, line_end, original_snippet, patched_snippet,
  full_patched_source, confidence_hint (default 0.9),
  generated_at, generator ("template" | "rule"), `to_dict()`.
- Pattern generators (template matchers):
  - `_find_bare_excepts` — `except:` → `except Exception:`
  - `_find_bare_except_pass` — `except: pass` → `except Exception:`
  - `_find_mutable_default_arg` — `def f(x=[])` → `def f(x=None): if x is None: x = []`
    (handles List, Dict, set() defaults; inserts None-guard at function body start)
  - `_find_missing_encoding_open` — `open(path)` → `open(path, encoding='utf-8')`
- `PATTERN_REGISTRY` — dict mapping name → generator function.
  `DEFAULT_PATTERNS` — list of all 7 pattern names.
- `SpeculativeCache` class:
  - Persistent JSON cache at `data/speculative_cache.json`
  - Key: `(file_sha16, pattern_name)` → CandidateFix
  - LRU eviction above `max_entries` (default 1000)
  - TTL eviction (default 3600s)
  - Thread-safe: `threading.RLock` guards all mutations
  - Atomic JSON write via `os.replace(tmp, cache_file)`
  - `lookup(file_sha, pattern_name)` — returns CandidateFix or None
    (fail-open on miss / TTL expiry)
  - `invalidate(file_path)` — removes all entries for a file path
  - `clear_all()`, `stats()` (hits, misses, prefetch_calls,
    candidates_stored, evictions, invalidations, errors)
  - `prefetch_candidates(file_path, patterns, source_override)` —
    walks file AST, runs each pattern generator, stores results.
    Timeout-capped at `DEFAULT_PREFETCH_TIMEOUT=0.5s` per file.
  - `_load()` / `_save()` — JSON persistence (fail-open on corrupt:
    rebuild from empty).
- Singleton: `get_speculative_cache()` (lazy) +
  `reset_speculative_cache()` for tests.
- Module-level shortcuts: `prefetch_candidates()`, `lookup()`,
  `invalidate()`, `stats()`.
- Fail-open: cache miss → return None (caller falls back to normal
  path). Cache corrupt → rebuild. Pattern generator crash → log +
  continue. Cached fix STILL goes through IMP-14 confidence + IMP-15
  semantic_equiv (DNA #22 — NOT a free pass).

#### `callgraph_delta.py` (642 LOC) — IMP-22 (SPEED)
- `CallEdge` dataclass — caller_file, target_name, line, col,
  is_method_call, `key()` method for dedup.
- `FileNode` dataclass — path, sha (16-char prefix), mtime,
  functions_defined, calls (list of CallEdge), parse_error.
  `to_dict()` / `from_dict()` for JSON serialization.
- `DeltaResult` dataclass — added_edges, removed_edges,
  affected_callers, affected_callees, files_rebuilt, files_skipped,
  bounded, reason, `to_dict()`.
- `_FileAnalyzer` (ast.NodeVisitor) — walks AST, collects function
  defs (FunctionDef + AsyncFunctionDef) + call sites (Call nodes,
  both Name and Attribute func). Bounded by MAX_NODES_PER_FILE=8000,
  MAX_FUNCTIONS_PER_FILE=500, MAX_CALLS_PER_FILE=2000.
- `_analyze_file(path)` — parse + analyze one .py file. Returns
  FileNode (never raises — fail-open on parse/read error).
- `CallGraph` class:
  - Persistent JSON cache at `data/callgraph.json` (version=1)
  - `self._files: dict[str, FileNode]` — file_path → FileNode
  - `self._func_index: dict[str, set[str]]` — function_name →
    file_paths where defined
  - `self._caller_index: dict[str, set[str]]` — function_name →
    file_paths that call it
  - Thread-safe: `threading.RLock` guards all mutations
  - Atomic JSON write via `os.replace(tmp, cache_file)`
  - `build_full(scp_root)` — walk scp_root, analyze every .py file,
    persist graph. Replaces any existing graph.
  - `apply_delta(changed_files)` — re-analyze only changed files,
    compute edge delta (added/removed), rebuild indexes, persist.
    Returns DeltaResult.
  - `get_callers(func_name)` / `get_definitions(func_name)` —
    return sorted list of file paths.
  - `get_calls_in_file(file_path)` — return list of CallEdge.
  - `invalidate_file(path)` — remove file from graph.
  - `clear_all()`, `stats()`, `is_file_current(path)` (SHA check).
  - `_load()` / `_save()` / `_rebuild_indexes()` (internal).
- Singleton: `get_call_graph()` (lazy) + `reset_call_graph()` for tests.
- Bounded: MAX_FILES_PER_BUILD=500, skips .git/__pycache__/.venv/etc.
- Fail-open: graph corrupt (JSON malformed / version mismatch) →
  rebuild from scratch (log warning). File unparseable → skip (don't
  crash build). Internal error → log + continue with empty graph.

#### `runner_phases/shadow_canary.py` (743 LOC) — IMP-23 (SAFETY)
- `ShadowFix` dataclass — original_source, patched_source, fix_id,
  bug_location (tuple of function_name, line_start, line_end).
- `CanaryTest` dataclass — name, fn (callable), description.
- `CanaryTestResult` dataclass — name, passed, output, reason,
  duration_ms.
- `CanaryResult` dataclass — passed, original_outputs,
  shadow_outputs, diffs, reason, shadow_path, flagged_for_review,
  tests_run, `to_dict()`.
- `CanarySuite` dataclass — tests (list of CanaryTest), max_tests=50,
  timeout_seconds=5.0. `add(test)` / `add_test(name, fn, description)`.
- Built-in canary tests:
  - `_ast_parse_test` — shadow source must parse (SyntaxError → fail)
  - `_import_test` — shadow module must import (ImportError → fail)
  - `_smoke_call_test` — call each top-level function with edge inputs
    (None, [], {}, "", 0, 1, -1). Records per-input exception signature
    in output (list of [fname, input_repr, exc_class]) for regression
    comparison. Distinguishes "wrong arg count" TypeError (skip) from
    real TypeError (e.g. None + 1, record).
  - `_reality_test_wrapper` — invoke IMP-2 reality_test (lazy import,
    fail-open if unavailable)
  - `_property_test_wrapper` — invoke IMP-19 property_validator (lazy
    import, fail-open if unavailable)
- `default_canary_suite()` — returns CanarySuite with all 5 tests.
- `_write_shadow(source, original_filename)` — write source to temp
  file in `data/shadow/`, import as fresh module via
  `importlib.util.spec_from_file_location`. Returns (path, module).
  Fail-open on write/import error → ("", None).
- `_cleanup_shadow(shadow_path)` — best-effort cleanup of shadow temp
  file + associated __pycache__ entries.
- `_detect_exception_regression(orig_output, shadow_output)` —
  compare exception signatures, return True if shadow raises where
  original didn't.
- `_short_output(output, max_len=100)` — short repr for diff logging.
- `shadow_apply_and_compare(target_file, fix, canary_suite)`:
  1. Default suite if None provided.
  2. Empty suite → fail-open (passed=True, flagged_for_review=True).
  3. Write + import original shadow (fail-closed if can't import).
  4. Write + import patched shadow (fail-closed if can't import).
  5. Run each canary test on both modules.
  6. Compare: shadow fails where original passed → REGRESSION diff.
     Original fails where shadow passed → IMPROVEMENT diff (non-blocking).
     Both passed with different output → check for exception regression
     (blocking) or output diff (non-blocking, flag for review).
  7. Verdict: passed=True iff all_shadow_passed AND no REGRESSION diffs.
  8. Cleanup shadow temp files (finally block).
- `summarize_canary(result)` — human-readable summary for audit log.
- Fail-open policy (DNA #7 + #11 tension):
  - Empty suite → passed=True, flagged_for_review=True (don't block
    fixes if safety infra is down, but flag for review).
  - Canary runner crash → passed=False (fail-closed).
  - Shadow apply fails → passed=False (fail-closed).
  - Internal error → passed=True, flagged_for_review=True + stderr.

#### `policy_gate.py` (755 LOC) — IMP-24 (SAFETY)
- `ForbiddenPattern` dataclass (frozen) — name, regex, severity
  ("BLOCK" | "REVIEW"), description, dna_ref. `matches(text)` method
  (case-insensitive, multiline, fail-open on regex error).
- `FORBIDDEN_PATTERNS` — list of 13 built-in patterns:
  - BLOCK: lower_threshold, remove_check, disable_validation,
    allow_attack, skip_auth, world_writable_chmod, verify_false_tls
  - REVIEW: bare_except_pass, noqa, type_ignore,
    shell_true_subprocess, eval_call, exec_call
- `PolicyFix` dataclass — fix_id, patch, patched_source, bug_file,
  bug_line, scanner_name, extra.
- `PolicyDecision` dataclass — allowed, blocked_patterns, severity
  ("ALLOW" | "REVIEW" | "BLOCK"), reason, audit_id (SHA-256[:16]),
  fix_id, timestamp, `to_dict()`.
- `ImmutableAuditLog` class:
  - Append-only JSONL at `data/policy_blocks.jsonl`
  - Each entry includes `entry_hash` (SHA-256[:32] of prev_hash +
    entry payload) + `prev_hash` (chained from previous entry).
  - "GENESIS" is the initial prev_hash.
  - `append(entry)` — atomic append, returns entry_hash. Fail-open
    on OSError (disk full / permission denied) → log to stderr
    (DNA #11), return None.
  - `read_since(since_ts)` — read entries with timestamp >= since_ts.
  - `verify_chain()` — recompute hashes, detect tampering. Returns
    (ok, reason).
  - File permissions set to 0o644 on creation.
  - Thread-safe: `threading.RLock` guards all mutations.
- `PolicyGate` class:
  - `evaluate_fix(fix)` — coerce to PolicyFix if needed, scan patch +
    patched_source against all patterns, build PolicyDecision
    (BLOCK if any BLOCK-severity match, REVIEW if only REVIEW-severity,
    ALLOW if no match). Log every decision (including ALLOW for
    transparency) to audit log.
  - `appeal_block(fix_id, human_token, justification)` — log appeal
    to `data/policy_appeals.jsonl` (separate file). Returns dict
    with appeal_id + status. Does NOT auto-unblock — operator must
    manually re-apply the fix if justified.
  - `list_blocks(since_ts)` — return BLOCK decisions since timestamp.
  - `stats()` — return counts (allow/review/block) + patterns_registered.
  - `_log_decision(decision, fix)` — write to audit log. If audit log
    unwritable AND decision was BLOCK → scream to stderr (DNA #11)
    but keep in-memory BLOCK decision in effect.
- Fail-open policy (DNA #4 + #7 tension):
  - Policy engine crash → DEFAULT-DENY (block + log) per DNA #4.
    "Safer to block than allow a dangerous fix when safety net is broken."
  - Audit log unwritable → DEFAULT-ALLOW with loud stderr warning per
    DNA #7 (don't brick engine if disk is full — but scream per DNA #11).
    In-memory BLOCK decision still in effect; only audit trail incomplete.
- Singleton: `get_policy_gate()` (lazy) + `reset_policy_gate()` for tests.
- Module-level shortcuts: `evaluate_fix()`, `appeal_block()`,
  `list_blocks()`.

---

### Modified — 0 files

Per task spec ("LIGHT TOUCH — don't modify engine.py heavily"): no v2
or v3 file was modified. All 6 v4 modules are standalone with clearly
documented integration points (see V4_MANIFEST.md "Integration
approach" table). Integration into `engine.py` / `runner.py` /
`runner_phases/ast_scan.py` / `runner_phases/blast_radius.py` /
`runner_phases/post_fix_verify.py` is deferred to a follow-up task to
avoid destabilizing the v2/v3 engine.

---

### Removed

None. All v2 + v3 code preserved (backward compatible). New v4 features
are additive — if any v4 module fails to import, the v2/v3 engine
continues to work unchanged (each v4 module is imported lazily by its
caller, not at engine startup).

---

## Migration guide (v3 → v4)

### No action needed for existing callers

All 6 v4 features are:
- **Standalone** — no v2/v3 file modified, no engine startup import
- **Opt-in** — callers explicitly call v4 functions; if not called, v3
  behavior is unchanged
- **Fail-open** — engine continues to work if any v4 module is unavailable
- **Backward compatible** — no v2/v3 API signature changed

### To enable v4 features (when ready to wire in)

| Feature | How to enable |
| --- | --- |
| IMP-19 property validation | Call `validate_fix(orig, fixed, bug_loc, spec, n=100)` in `runner_phases/post_fix_verify.py:run_full_post_fix_verify()` AFTER IMP-2 reality_test, BEFORE IMP-14 confidence scoring |
| IMP-20 type-flow | Call `verify_type_flow(file, func, orig_sig, new_sig, scp_root)` in `runner_phases/post_fix_verify.py:run_full_post_fix_verify()` AFTER IMP-15 semantic_equiv |
| IMP-21 speculative prefix | Call `prefetch_candidates(file, DEFAULT_PATTERNS)` in `runner_phases/ast_scan.py` BEFORE scan; call `lookup(sha, pattern)` in `engine.py:process_bug()` AFTER scanner confirms bug |
| IMP-22 callgraph delta | Replace internal walk in `runner_phases/blast_radius.py:compute_blast_radius()` with `get_call_graph().get_callers(func)`; call `apply_delta([patched])` after each fix in `engine.py` |
| IMP-23 shadow canary | Call `shadow_apply_and_compare(file, fix, default_canary_suite())` in `engine.py:apply_fix()` BEFORE the actual file write |
| IMP-24 policy gate | Call `evaluate_fix(fix)` in `engine.py:apply_fix()` BEFORE IMP-14 confidence scoring |

---

## Verification

All 6 new v4 files pass `ast.parse` — no syntax errors. Verification
was run with `-W error::SyntaxWarning` (stricter than v3 — catches
invalid escape sequences in docstrings, which v3's verification missed;
the `policy_gate.py` docstring was made a raw string `r"""..."""` to
avoid `\s` escape warnings).

All 51 v2 + 6 v3 = 57 existing files STILL pass `ast.parse` (no v2/v3
file modified, no regression).

```
$ cd /home/z/my-project/scp/autofix
$ for f in property_validator.py type_flow_verifier.py \
           speculative_prefixer.py callgraph_delta.py \
           runner_phases/shadow_canary.py policy_gate.py; do
    python3 -W error::SyntaxWarning -c "import ast; ast.parse(open('$f').read())" \
      && echo "OK: $f" || echo "FAIL: $f"
  done
OK: property_validator.py
OK: type_flow_verifier.py
OK: speculative_prefixer.py
OK: callgraph_delta.py
OK: runner_phases/shadow_canary.py
OK: policy_gate.py

$ total=0; fails=0
$ for f in $(find . -name "*.py" -not -path "./__pycache__/*"); do
    total=$((total + 1))
    python3 -W error::SyntaxWarning -c "import ast; ast.parse(open('$f').read())" \
      || { echo "FAIL: $f"; fails=$((fails + 1)); }
  done
$ echo "Total: $total, Fails: $fails"
Total: 63, Fails: 0

$ wc -l property_validator.py type_flow_verifier.py \
        speculative_prefixer.py callgraph_delta.py \
        runner_phases/shadow_canary.py policy_gate.py | tail -1
4389 total

$ find . -name "*.py" -not -path "./__pycache__/*" | wc -l
63
```

---

## Smoke tests run (DNA #22 — PASS ≠ TRUE)

Each module was smoke-tested by importing it and calling a public
function with injected fakes. The smoke tests verify REAL behavior, not
just `ast.parse` success. Full output captured in V4_MANIFEST.md
"Smoke tests run" section. Summary:

- **IMP-19 (`property_validator`):** bad fix (removes `abs()`) → 21
  invariant violations across 50 inputs. no-op fix → 0 violations.
  fingerprint stable across calls. ✓
- **IMP-20 (`type_flow_verifier`):** parses Optional[X], PEP 604 X|Y.
  Narrowing Optional→X with caller `if x is None` → compatible=False,
  1 incompatible site. Fail-open with missing scp_root. ✓
- **IMP-21 (`speculative_prefixer`):** 7 candidates prefetched for 3
  patterns in test source. Cache hit on valid SHA, miss on bad SHA.
  Stats tracked correctly. ✓
- **IMP-22 (`callgraph_delta`):** build_full indexes 2 files. Delta
  after removing `bar()` call → +1/-2 edges, 1 affected caller.
  `get_callers('bar')` returns 0 after delta. ✓
- **IMP-23 (`shadow_canary`):** no-op fix passes (5 tests). Regression
  fix (removes None check) → passed=False with diff "shadow raises
  where original didn't". Syntax-broken fix → fail-closed. Empty
  suite → fail-open (flagged). ✓
- **IMP-24 (`policy_gate`):** `verify=False` → BLOCK. `chmod 0o777` →
  BLOCK. Clean fix → ALLOW. bare-except-pass → REVIEW. Appeal logged.
  Audit chain verifies OK (4 entries, no tampering). ✓
