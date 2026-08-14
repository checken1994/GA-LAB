# R44 BareExceptPass A/B Evidence

## Current PC source

The A/B harness scanned 606 Python files under `C:\Users\check\Downloads\scp` after excluding `venv`, `node_modules`, caches, Git metadata and private staging. The independent AST baseline found `0` `BareExceptPass` findings and the candidate generator found `0`. There were `0` parse failures and no policy promotion. This means the candidate had no current-source behavior change to measure; it does not prove the rule is universally correct.

## Historical lineage sources

The same harness was run against real source files from cloned historical repositories, not generated samples.

| Source lineage | Files scanned | Independent baseline findings | Candidate findings | Candidate patched files | Candidate patch compile pass | Compile fail |
|---|---:|---:|---:|---:|---:|---:|
| `scp-v88/scripts/legacy` | 6 | 7 | 7 | 3 | 3 | 0 |
| `V3-/SCP` | 7 | 1 | 1 | 1 | 1 | 0 |

The baseline and candidate counts match on both lineages. This supports **detector parity** for the narrow pattern in these files: the candidate generator found every finding identified by the independent AST detector in the bounded runs. It does not prove the historical bare exceptions were harmful, nor does it prove the proposed patch is semantically correct for every context.

The A/B report records `independent_true_positive_evidence=0`, `independent_false_positive_evidence=0`, `ground_truth_available=false` and `policy_promotion=false`. The candidate was not promoted into active policy. The current PC source was not modified by the A/B scan; results and cache were written under `.private-secrets/release-audit`.

## Independent PC reality gates

On the real PC, `reality_4-b-012.py` passed all seven checks. `reality_4-b-013.py` first exposed a default Windows code-page failure, then the explicit UTF-8 patch was applied with backup manifest from commit `c16fecd`; the test subsequently passed all eight rollback checks under the default PC process. The production `.env` was not changed. This closes the previously observed test-harness encoding defect within the tested file, but it does not prove every other reality test is UTF-8-safe.

## Interpretation under SCP DNA

The result is a **PASS within a narrow detector/compile scope**, not a truth claim. The key missing piece is semantic evidence: whether changing a particular historical `except: pass` to `except Exception: pass` preserves intended control flow and security behavior. The current method only proves syntactic detection and that the generated source parses.

The correct next gate is a semantic-equivalence review on the six evolution records and their exact source snapshots, followed by fault-injection and current reality tests. If the source snapshots cannot be recovered, the six records remain operational candidates rather than promotable fixes.
