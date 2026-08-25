# GA-LAB Structural-Debt Port Evidence

- **Worktree:** `structure-debt-pc-merge`
- **Base:** `06e1cef2e6c7c44bf23c354b0a106f93b72cd273`
- **Source reference:** `scp-agent` commit `cb132a5af9f0dbcc6293b939ab32136cef22593c`
- **Scope:** port only counterpart-compatible J-1, J-2 and Windows cascade fix. K-1/task-kernel and phase façade were not copied because GA-LAB has no corresponding module/API.

## Ported changes

| Area | Result |
|---|---|
| J-1 KB short-circuit | `locals().get` removed; explicit initialized `verdict_type`, `final_answer`, `confidence` used |
| J-2 speculative evidence | `verdict_evidence_spec = None`; final merge uses explicit `is not None` condition |
| Windows cascade test | Host PATH and native Windows variables preserved in child environment |
| K-1 fencing | Not ported; no GA-LAB TaskKernel/lease counterpart exists |
| Phase refactor | Not ported; GA-LAB remains monolithic and needs a separate compatibility project |

## Verification

| Check | Result |
|---|---|
| `python -m compileall -q scp scripts` | PASS |
| Targeted tests | 4 passed: scope contracts, API import, judge unknown characterization |
| Full pytest | 103 passed, 2 warnings, 3.48 seconds |
| Ruff F821/E722 changed paths | PASS |
| Ruff changed test files | PASS |
| Runtime `/health` on 8002 | HTTP 200 |
| Runtime golden `POST /ask` on 8002 | HTTP 200, PASS / UPHOLD / SUCCESS / OK, domain math |
| Runtime RAG context smoke | HTTP 200, UNKNOWN / ESCALATE; recorded as existing behavior, not claimed as PASS |
| Port 8000 | No listener before, during or after smoke |
| Cleanup | Runtime parent/children stopped; no listener remained |

## Static limitation

Broad Bandit over the monolith remains a legacy inventory with existing findings. The patch-specific critical checks have no new F821/E722 or Ruff errors. The release decision must not call GA-LAB production-ready solely from these tests.

## Merge safety

The original GA-LAB main was observed clean at `06e1cef` immediately before port, and a local restore branch `backup/pre-structural-port-20260825` points to that exact commit. The original directory was not edited directly during port; this worktree is the merge candidate.
