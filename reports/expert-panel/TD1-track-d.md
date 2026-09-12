# TD-1 (track D) — worker report: C1/C2 SQL de-dynamicization + D3/D4 assessments

- Date: 2026-09-12
- Branch: `audit/runtime-guard-AUDIT-20260909` (worker commits locally; orchestrator pushes and runs the PUSH-gate)
- Base HEAD: `45a7dc8`
- Scope: 4 HIGH push-gate findings in `scp/event_bus_pg.py` + `scripts/migrate_kernel_sqlite_to_pg.py` (Nhiệm vụ 1), D3 LiteLLM + D4 OPA/SIEM assessments (Nhiệm vụ 2–3, no code integration).

## Skill binding (SHA256)

| Skill | SHA256 |
|---|---|
| `.agents/skills/scp-dna/SKILL.md` | `4aada0be4873598dc50c3a7f38d90151429bb5263c511a838ed1cdcb4d594d10` |
| `.agents/skills/scp-reality-verifier/SKILL.md` | `a9d65ce53b18f8310ceeb302b18b341a0e1b8b19cddc7f46d4fa6ee99432269e` |

## Nhiệm vụ 1 — de-dynamic SQL composition (4 HIGH)

Diagnosis basis: Mimosa flags the *shape* of dynamic SQL composition
(`sql.SQL(...).format(...)`, f-string SQL text) even when the composed
identifier is a compile-time constant (the `DELETE FROM` finding flags
`Identifier("control")` — a literal). Proven-clearing shapes in this repo:
100% parameterized SQL + whitelist (`scp/kernel_storage_pg.py:427-457`, passed
all scans) and per-table literal statements (constant map).

### Fixes (file:line, behavior-preserving)

1. `scp/event_bus_pg.py:276` (now ~287) — `LISTEN` no longer composes SQL
   text at all. Root cause analysis: LISTEN is a PG utility statement — it
   accepts an identifier and NO bind parameters, so a per-event-channel
   LISTEN *forces* the statement text to be built from a variable. Iteration
   evidence: first candidate `"LISTEN " + sql.Identifier(channel).as_string()`
   was re-flagged by a normal-depth Mimosa scan (finding at the new line,
   "SQL text constructed dynamically via concatenation") — the rule flags
   concatenation/format/f-string regardless of quoting safety. The fix that
   clears the shape class honestly: a **fixed wake channel** (`_WAKE_CHANNEL =
   "scp_bus_wake"`):
   - `listen_conn.execute("LISTEN scp_bus_wake")` — compile-time constant, no
     variable ever enters SQL text;
   - `publish()` rings the same constant bell via the already-parameterized
     `SELECT pg_notify(%s, %s)` (`scp/event_bus_pg.py:~220`);
   - semantics preserved by the module's own design contract (module
     docstring + `scp/event_bus_pg_schema.sql:4-11`): the durable TABLE is the
     source of truth, NOTIFY is ONLY a wake-up bell, the bell payload is
     never read, and every poll re-filters by the subscriber's channel
     (`_SQL_POLL_BATCH`/`_SQL_REPLAY_BATCH` are parameterized on channel).
     A bell carrying unrelated news causes one empty indexed poll — a
     bounded, documented cost; delivery, ordering, replay, dead-letter
     semantics are unchanged.
   - `_validate_channel()` regex fail-closed validation is kept (channel
     remains data in the table filter / notify argument).
   - `from psycopg import sql` import removed (no longer used anywhere in
     the file).
2. `scripts/migrate_kernel_sqlite_to_pg.py:81` — `PRAGMA table_info("f{table}")`
   f-string replaced by a **bound-parameter** table-valued function:
   `SELECT name FROM pragma_table_info(?) ORDER BY cid` (SQLite >= 3.16; host
   ships 3.49.1). Same columns, same cid order, same empty result for a
   missing table; the table name is now a value, not SQL text.
3. `scripts/migrate_kernel_sqlite_to_pg.py:135` — f-string
   `SELECT COUNT(*) FROM "{table}"` replaced by per-table literal constant map
   `_SQLITE_COUNT_SQL` (7 fully written-out statements, keys pinned to
   `COPY_ORDER` by import-time asserts; unknown table → KeyError = fail-closed).
4. `scripts/migrate_kernel_sqlite_to_pg.py:209` —
   `pg_sql.SQL("DELETE FROM {}").format(pg_sql.Identifier("control"))` replaced
   by `_PG_DELETE_SQL["control"]` literal.
5. Same-shape siblings cleared proactively (S10 precedent):
   - `:214` + `:287` (`SELECT COUNT(*) FROM {t}` composition) → `_PG_COUNT_SQL[t]`.
   - `:253` (`DELETE FROM {table}` composition loop) → `_PG_DELETE_SQL[table]`.

### Kept (with justification, not flagged)

- `scripts/migrate_kernel_sqlite_to_pg.py:~174` — `CREATE SCHEMA IF NOT EXISTS`
  with `pg_sql.Identifier(schema)`: schema name is operator-supplied and not
  statically enumerable; psycopg `sql.Identifier` is the sanctioned safe API
  here (this exact site was not in the flagged set).
- `scripts/migrate_kernel_sqlite_to_pg.py:~259` — INSERT builder composes the
  column list from the source DB (dynamic by necessity); columns are
  fail-closed verified `sqlite_cols == pg_cols` against both catalogs before
  any INSERT runs, and values are 100% placeholders. Not in the flagged set.

## Verification (reality checks, TD-1 environment)

| Check | Command / method | Result |
|---|---|---|
| Compile | `python -m py_compile scp/event_bus_pg.py scripts/migrate_kernel_sqlite_to_pg.py` | exit 0 |
| Full T04 suite vs REAL PostgreSQL 16 (docker `scp-pg-test`, canonical hint from the tests) | `SCP_PG_TEST_DSN=... python -m pytest tests/T04_kernel/ -q` | **228 passed, 0 failed, 0 skipped**, exit 0 (62 s) — re-run after the final `_WAKE_CHANNEL` design |
| LISTEN/NOTIFY wake path under the fix | `tests/T04_kernel/test_pg_event_bus.py::test_e_notify_wakes_subscriber_below_poll_interval` inside the suite (real wake below a 60 s poll interval) | passed |
| Migration dry-run on synthetic DB (real CLI, real PG) | `TaskKernel(sqlite)` synthetic source → `scripts/migrate_kernel_sqlite_to_pg.py --pg-dsn ... --schema scp_td1_dryrun --dry-run` | rc=0, source counts correct, `DRY-RUN complete (no writes performed)`, DSN redacted |
| Migration end-to-end (real run, re-run fail-closed, `--truncate`, kernel semantics on migrated data) | `tests/T04_kernel/test_pg_migration.py::test_migrate_sqlite_to_pg_end_to_end` inside the suite | passed (exercises every changed line incl. `_PG_DELETE_SQL` paths) |
| Mimosa normal-depth re-scan (working tree with fixes) | MCP `security_scan` depth=normal, job `scan-job-mtye4uja-b75a384ba9eb9c66`, seal `sha256:2566c929...` | **0 findings in both fixed files**; repo-wide high count 0 (113 findings, all low/medium). Pre-fix comparison scan (job `scan-job-mtydy4lk-...`) had 1 HIGH at the intermediate concat shape and 0 in the migrate script — confirms the constant-map/parameterized fixes cleared 3 of 4 on first try and the LISTEN redesign cleared the last one |

Verdict: **PASS_WITHIN_SCOPE** — the 4 flagged dynamic-SQL shapes (and their
same-shape siblings) are gone from both files; a normal-depth Mimosa scan of
the fixed tree reports no finding in either file; the full T04 suite passes
against a real PostgreSQL with zero skips.

### Limits (DNA #22 #23)

1. The authoritative PUSH-gate (L3, interprocedural) is not reproducible by
   this worker; the orchestrator must re-run it on push. The normal-depth
   Mimosa re-scan recorded above is supporting evidence only.
2. `scripts/migrate_kernel_sqlite_to_pg.py` keeps two `psycopg.sql` sites
   (CREATE SCHEMA with operator-supplied schema name; INSERT builder with a
   source-derived column list). Both are outside the flagged set and have no
   static alternative without schema duplication; if a future gate flags
   them, the fix needs a drift-guarded schema-column constant map.
3. `_WAKE_CHANNEL` semantic note (documented in code): any publish wakes every
   live subscriber regardless of channel; each wake costs one indexed empty
   poll for unrelated channels. Delivery semantics are unchanged (bell is a
   pure optimization per the module contract). NOTIFY channels are
   cluster-global (not schema-scoped) — unchanged by this fix.
4. The PG test container was the canonical `scp-pg-test` started fresh for
   this task and removed afterwards (no repo state affected).

## Nhiệm vụ 2 — D3 LiteLLM evaluation

Verdict: **KEEP (core) + optional future borrow of provider-adapter breadth**.
Evidence-based assessment with file:line citations:
`reports/expert-panel/D3-litellm-evaluation.md`. No code integrated.

## Nhiệm vụ 3 — D4 OPA/SIEM evaluation

Verdict: **KEEP governance in-process + ADOPT a small PagerDuty-compatible
webhook exporter** (export-only, no control-flow dependency). Evidence:
`reports/expert-panel/D4-opa-siem-evaluation.md`. No code integrated.

## Commits

- `fix(C1/C2): de-dynamic SQL composition per push-gate findings` — 2 product
  files + this report.
- `docs(D3): LiteLLM evaluation — KEEP core gateway, borrow adapters later` — report only.
- `docs(D4): OPA/SIEM evaluation — KEEP in-process governance, adopt webhook exporter` — report only.
