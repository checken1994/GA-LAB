# SCP History Migration R44 — What the Current System Can Learn

**Status:** staging scan implemented and exercised on the user's PC; no runtime/policy mutation.  
**Latest code commit:** `e582adadda3a77360b6382422ec3d9c4315c2d84`.

## The missing distinction

SCP history contains several different kinds of records. A simulator event, a code design, an autofix lesson, a retrieved fact, a prediction, and a resolved external outcome are not interchangeable. The migration lane therefore classifies artifacts by evidence level and creates candidates/quarantine entries instead of writing directly to `knowledge`, `experiences`, calibration factors or active policy.

| Evidence level | Example | Current allowed use |
|---|---|---|
| L0 design | V1/V88/scp-vietnam schemas and modules | Reuse architecture and test ideas. |
| L1 telemetry | `question_events`, `question_log`, learning run statuses | Regression corpus, recurrence and operational reliability analysis. |
| L2 operational lesson | Verified `BareExceptPass` evolution lesson | Candidate rule for the same bug, after current tests; no automatic policy promotion. |
| L3 verified knowledge | Source-attributed fact with independent re-verification | Candidate seed knowledge after freshness/contradiction checks. |
| L4 calibrated outcome | Numeric probability + locked event/deadline + evidence + adjudication + baseline | Calibration/scoring; only then policy impact through R43 gates. |

## What the PC actually has now

The real `data/v13.db` currently has 15,733 `question_events`, 13,815 `question_log` rows, 814 `knowledge_versions` rows, 146 `live_knowledge_cache` rows, 44 `experiences`, and one `knowledge` row. It has zero `error_history`, `memory`, `calibration_history`, `calibration_factors`, `predictions`, `meta_principles` and `meta_curiosity` rows. The 44 experiences are `VERDICT_UNKNOWN`, `VERDICT_CONFLICT`, `VERDICT_FAIL`, `VERDICT_PARTIAL`, `VERDICT_PASS` and `VERDICT_SPECULATIVE` history, all `applied=0`; they are not policy lessons.

The 15,733 question events are dominated by a known operational lineage: 15,587 source `threat_simulator` and 14,837 `REPEAT`. This history can teach which attack probes and routes recur, but it cannot prove an external claim. `knowledge_versions` is also not 814 verified facts: every row is `change_type=delete`, source `PolicyApplier`, which is cleanup/policy mutation history.

The separate `data/kb_evolve.sqlite` contains six lessons and four evolved patterns. All six lessons concern `BareExceptPass`; the PC inspection found `fix_verified=1` and `success_rate=1.0` for all six. The four patterns have confidence 0.5, occurrence 0 and false-positive count 0. Therefore the six rows are candidates for one narrow operational bug class, not general learning; the patterns remain quarantined.

`data/learning_runs.jsonl` contains 59 operational runs: 8 `SUCCESS`, 6 `VERIFY_REJECTED`, 3 `NO_NEW_FACTS`, 31 `TIMEOUT`, 10 `PROVIDER_FAILED` and 1 `DB_WRITE_FAILED`. This is useful evidence about provider/timeout/verification/persistence reliability, not content that should become policy.

## Migration behavior

`scp/history/migration.py` is read-only with bounded JSONL/SQLite sizes, SHA-256 per artifact, explicit dispositions and atomic manifest output. The CLI `scripts/history/r44_history_migration.py` scans current DBs and logs. It does not import rows into current runtime tables, mark lessons applied, promote policy, change `.env`, or mutate source artifacts.

The staging CLI was downloaded from commit `e582ada` into `.private-secrets/release-audit/r44-history-stage` on the user's PC and run against the real `v13.db`, `kb_evolve.sqlite`, learning/evolution logs and reality results. It returned `SCANNED`, `artifact_count=6`, `candidate_count=6`, `quarantine_count=4`, `mutating=false`, `policy_promotion=false`. A post-run reality check retained the same SHA-256 for `data/v13.db` (`A0F5BD0F…`) and `data/kb_evolve.sqlite` (`53A2DEB3…`) observed before the scan.

The existing `reality-tests-results.json` remains quarantined because its 73 result rows have `pass=null`; a top-level PASS header cannot replace row-level truth. The migration lane therefore reports contract invalid rather than converting it into verified history.

## What should happen next

The first useful migration is not “learn everything.” It is a bounded three-lane import. Lane A converts simulator/benchmark telemetry into a versioned adversarial regression corpus. Lane B evaluates the six verified `BareExceptPass` rows as one candidate rule class and reruns static, fault-injection and reality tests. Lane C re-verifies the one current knowledge row and selected V3 seed facts against independent sources before any KB insertion.

The 210 forecast registry stays in a fourth quarantine lane until its resolution contract exists. It is not the only history, but it is also not a substitute for operational learning. Future policy changes must still pass R43 materialization, backup/rollback, behavior-delta A/B measurement and human review.

## Safety boundary

The user's PC worktree remains dirty and behind the current GitHub head. The migration staging run did not force checkout, reset, edit the production `.env`, edit active policy, mark experiences applied, or alter the Knowledge Base. A later source installation must use the existing backup manifest, a narrow path update and a post-install reality test.
