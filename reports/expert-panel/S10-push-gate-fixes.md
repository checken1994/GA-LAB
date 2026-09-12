# S10 — PUSH-gate 16 HIGH fixes (worker report)

- Date: 2026-09-12
- Branch: `audit/runtime-guard-AUDIT-20260909` (no commit — orchestrator pushes)
- Gate: Mimosa L3 PUSH-gate (stricter than deep scan, interprocedural) — 16 HIGH, 12 example lines given
- Base commit: `c01f7f8` (working tree clean for the 3 fixed files before this task)

## Skill binding (SHA256)

| Skill | SHA256 |
|---|---|
| `.agents/skills/scp-dna/SKILL.md` | `4aada0be4873598dc50c3a7f38d90151429bb5263c511a838ed1cdcb4d594d10` |
| `.agents/skills/scp-reality-verifier/SKILL.md` | `a9d65ce53b18f8310ceeb302b18b341a0e1b8b19cddc7f46d4fa6ee99432269e` |

## Diagnosis basis (evidence, not guesswork)

1. Read every flagged line + 20-line context in all 3 files.
2. Cross-checked unflagged sibling `console.*` calls in the same files (21 in
   `core.ts`, 18 in `loop-scheduler/index.ts`) to infer the flagged shape:
   **every flagged line interpolates scanner-tainted values (process.env reads,
   or HTTP request body via `_cacheKey`) INTO the log message string**; every
   unflagged dynamic log either passes values as separate args
   (`console.error("msg:", err)` at core.ts 836/933/1055) or interpolates only
   non-tainted values (static `ADVERTISED_MODELS` — line 1064 unflagged while
   its env-tainted neighbours 1061/1062/1063/1065 are flagged).
3. The "sql-injection" label comes from Mimosa's cross-file interprocedural
   graph: the latest deep scan (`scan-2026-09-11T22-48-15.829Z-47e219c5c3ca`,
   medium tier) reports `core.ts:873/887/965/980 环境变量 → scp/autofix/
   deterministic_worker.py:130 SQL 执行 .execute` (cross-file taint to a
   parameterized sqlite sink). No SQL exists in either TS file; no flagged log
   flows into any SQL construction. Verdict per line: **FP as "SQL injection";
   true as "tainted data interpolated into log message"** (mild log-injection/
   hygiene issue) → restructure per the task's FP menu; nothing needed
   parameterization.

## Per-line diagnosis + fixes

### 1. `scripts/diagnostics/patch_s_b1a_request_run_ledger.py:96` — path-traversal

- Diagnosis: **FP-as-taint, real-as-guard-gap.** Write sink `open(P, "w")` where
  `P = Path("scp/core/request_run_ledger.py")` is a module-level literal — no
  untrusted input. But the path is a variable at the sink with no validation,
  and the script silently follows CWD (running it from any other directory
  would write elsewhere).
- Fix: fail-loudly containment guard before the sink (task-specified: safe
  charset whitelist + resolve under repo): repo-relative check, charset
  allowlist `[A-Za-z0-9._-/]`, `P.resolve()` must be under
  `Path(__file__).resolve().parents[2]` AND equal the pinned in-repo target.
  Behavior unchanged when run from repo root (the only supported mode); any
  other CWD now fails loudly instead of writing to a wrong path.
- Verified: `python -m py_compile` OK; AST parse OK; file LF endings preserved
  (script's internal `\r\r\n` string literals untouched).

### 2. `mini-services/llm-bridge/core.ts` — lines 68, 84, 626, 1061, 1062, 1063, 1065

All 7: FP as sql-injection (no SQL anywhere in the file); taint-into-message is
real. Fix shape = smallest per line, chosen to mimic proven-safe sibling lines:
constant message first, dynamic value as a **separate log argument** (the same
shape as unflagged lines 836/933/1055). No runtime logic changed; only log
wording/formatting (explicitly allowed).

| Line | Content (before) | Taint | Fix |
|---|---|---|---|
| 68 | `console.log("[scp-llm-bridge] env source=process.env (no implicit .env fallback)")` | none in statement — flagged because it sits inside `_loadEnvFile`, which reads AND writes `process.env` (function-level tainted scope) | moved OUT of `_loadEnvFile` to the call site; function now returns `string \| null`, caller logs the constant branch |
| 84 | `` console.log(`[scp-llm-bridge] env source=${_p}`) `` | `_p` from `SCP_ENV_FILE`/`SCP_SIDECAR_ENV_FILE` + `path.join()` (1 hop) | same call site; `console.log("[scp-llm-bridge] env source=", _envSourcePath)` |
| 626 | `` console.log(`[llm-bridge] cache HIT (key=${_ck}) — 0 API calls`) `` | `_ck = _cacheKey(cleaned, model)` — 1 hop from HTTP request body | `console.log("[llm-bridge] cache HIT — 0 API calls, key:", _ck)` |
| 1061 | `` ...listening on http://${HOST}:${PORT}` `` | HOST/PORT from env consts | `console.log("[scp-llm-bridge] listening — host:", HOST, "port:", PORT)` |
| 1062 | `` ...OpenRouter (${OPENROUTER_BASE_URL})` `` | base URL from env | `console.log("... → OpenRouter — base URL:", OPENROUTER_BASE_URL)` |
| 1063 | `` ...model: ${OPENROUTER_MODEL} ...` `` | model from env | `console.log("[scp-llm-bridge] model:", OPENROUTER_MODEL, '— override ...')` |
| 1065 | `` ...API keys: ${OPENROUTER_API_KEYS.length} · TTL ${LLM_CACHE_TTL_MS}ms` `` | length/TTL derived from env | `console.log("... API keys:", OPENROUTER_API_KEYS.length, "... cache TTL(ms):", LLM_CACHE_TTL_MS)` |

Line 1064 (`ADVERTISED_MODELS` — static array) was NOT flagged and is untouched.

Side-effect order preserved exactly: parsing/throws inside `_loadEnvFile`
unchanged; the two logs execute at the same points in the sequence (constant
log where the early-return was; path log after the parse loop).

### 3. `mini-services/loop-scheduler/index.ts` — lines 66, 93, 564, 744

Same diagnosis and same fix shape as file 2:

| Line | Fix |
|---|---|
| 66 | moved out of `_loadEnvFile` to call site (function-level `process.env` read+write scope) |
| 93 | `console.log("[loop-scheduler] env source=", _envSourcePath)` |
| 564 (startLoop) | `console.log("... loop started — interval(s):", LOOP_INTERVAL_SEC, "scp:", SCP_BASE_URL, "log:", LOOP_LOG_PATH)` |
| 744 (main) | `console.log("... booting — port:", PORT, "interval(s):", ..., "mode:", ..., "max_bugs:", ..., "scp:", ...)` |

Sibling same-shape lines (heuristic coverage for the unlisted HIGHs, same file,
same fix class — env-taint interpolated into message): **754** (`restored
${total} prior runs from ${LOOP_LOG_PATH}`), **767** (`restored persisted state
from ${LOOP_STATE_PATH}: paused=...`), **813** (`listening on http://${HOST}:
${server.port}`). All three converted to separate-arg logging. Untouched safe
shapes: 251/551/809 (catch-var slices as separate/whole error logs), 776/781
(ternary of string constants), 764/786/1050 (constants), 817 (signal name).

## Verification (reality checks)

| Check | Command | Result |
|---|---|---|
| Python parse | `python -m py_compile scripts/diagnostics/patch_s_b1a_request_run_ledger.py` | OK (exit 0), AST parse OK, CR/LF profile unchanged |
| TS bundle llm-bridge | `cd mini-services/llm-bridge && bun build core.ts` | exit 0 |
| TS bundle loop-scheduler | `cd mini-services/loop-scheduler && bun build index.ts` | exit 0 |
| Runtime smoke loop-scheduler (no env file) | `bun index.ts` | prints `[loop-scheduler] env source=process.env (no implicit .env fallback)` at the same point in startup, then module's own `SCP_AUTOFIX_MODE` guard throws (pre-existing intended behavior, unrelated to fix) |
| Runtime smoke loop-scheduler (env file) | `SCP_ENV_FILE=<tmp> bun index.ts` | prints `[loop-scheduler] env source= <path>` (path as separate arg) |
| llm-bridge runtime | not executed | module starts `Bun.serve` on import — starting a live port was out of scope for this worker; bundle parse + shape-echo of runtime-verified loop-scheduler restructure is the stated evidence limit |

No test was deleted/skipped/xfail; no threshold loosened; no `nosec`-style
suppression used (none exists in this toolchain anyway).

## Files changed (no commit)

- `scripts/diagnostics/patch_s_b1a_request_run_ledger.py` (+13 lines guard)
- `mini-services/llm-bridge/core.ts` (7 example lines + `_loadEnvFile` restructure)
- `mini-services/loop-scheduler/index.ts` (4 example lines + 3 sibling lines + `_loadEnvFile` restructure)

## Open items / limits (DNA #22 #23 — PASS_WITHIN_SCOPE only)

1. **Gate re-run required.** The L3 PUSH-gate profile is not reproducible by
   this worker (MCP scan profiles here are normal/deep; the latest deep scan
   already shows `high: 0` regardless, so a re-scan cannot verify gate
   clearance). The orchestrator must re-run the PUSH-gate on the push.
2. **3–4 unlisted HIGHs.** 16 HIGH vs 12 example lines. Best heuristic
   candidates (same file, same flagged shape) were fixed proactively:
   `loop-scheduler/index.ts` 754/767/813. If the remaining unlisted HIGHs are
   elsewhere, they were not observable from the given examples; compare the
   next gate output against this report.
3. **Scanner-shape hypothesis is evidence-based but not engine-confirmed:**
   separate-arg logging clears the flagged shape in every unflagged sibling
   observed, but Mimosa's exact taint-stop rules are a black box here. If the
   gate still flags the `env source=` call sites, the fallback is dropping the
   dynamic path value from the log (wording-only change).
4. `reports/pytest-basetemp.corrupt-20260910/` is unreadable (EPERM) — pre-existing
   environment issue, affects Mimosa baseline completeness, not this fix.
