# SCP 24/7 Operation — Final Reality Report

**Date:** 2026-08-14  
**Target:** `C:\Users\check\Downloads\scp`  
**Mode:** fail-closed, policy learning disabled  
**Status:** running canary successfully under a user-level Windows Task Scheduler task

## Executive conclusion

SCP is now running through a dedicated supervisor rather than the old manual four-window launcher. The supervisor starts the LLM Bridge, Loop Scheduler, SCP Python backend and dashboard as separate child processes, checks process/HTTP health every 15 seconds, records events in a private append-only JSONL ledger, applies a bounded restart budget, opens a circuit after repeated failures, and stops on an operator kill-switch file.

This is a **reality-tested 24/7 canary**, not a claim that every possible reboot, sleep, provider outage or Windows policy is proven. The PC must remain powered on and the user must log in because the installed trigger is `AtLogOn` with the user's interactive account. The design deliberately does not run as `SYSTEM` or as a Windows service because that would change environment/permissions and could silently bypass the user's existing production configuration.

## Phase 1 baseline

Before installation, no SCP scheduled task was found, no matching SCP/Python/Bun/Node/Electron process was running, and ports 3000, 3030, 8000, 11434, 18021 and 18022 were closed. The five dangerous flags were all OFF. The existing `start-scp.bat` used manual `cmd /k` windows and did not provide a watchdog, bounded recovery, kill switch or append-only supervisor ledger.

## Wiring failures found and fixed by reality testing

The first real canary exposed a genuine integration error: Loop Scheduler refused to start because `SCP_BASE_URL` was required but not passed by the old launcher. After that fix, a second canary exposed a second missing contract: `LLM_BRIDGE_URL` was also required. The supervisor now passes both explicit internal URLs:

| Variable | Runtime value |
|---|---|
| `SCP_BASE_URL` | `http://127.0.0.1:8000` |
| `LLM_BRIDGE_URL` | `http://127.0.0.1:11434` |
| `LOOP_LOG_PATH` | `<root>\data\loop_runs.jsonl` |
| `SCP_ENABLE_CLOSED_LOOP` | forced to `0` for child processes |

No provider secret was printed or changed. The production `.env` was not edited.

## Reality evidence

The staging supervisor passed PowerShell parser validation with zero errors and DryRun completed with exit code 0. The real canary then reached all four listeners and all four HTTP probes returned 200:

| Service | Port | HTTP result |
|---|---:|---:|
| LLM Bridge | 11434 | 200 |
| Loop Scheduler | 3030 | 200 |
| SCP Python | 8000 | 200 |
| Dashboard | 3000 | 200 |

A 60-second stability window recorded all four ports as listening at 15-second intervals. The new ledger events recorded four `HEALTHY` events per service during that window, with no restart in that window.

## Recovery and kill-switch evidence

The operator kill switch was created at `.private-secrets\release-audit\scp-247\KILL`. Within the bounded supervisor interval, the task entered `Ready` and all four ports became closed. After removing the kill switch and starting the task again, all four ports returned within 10 seconds. The final checkpoint kept all four HTTP endpoints at status 200.

The supervisor ledger includes `KILL_SWITCH`, `SUPERVISOR_STOPPED`, `SUPERVISOR_STARTED`, `START`, `STOP`, `RESTART`, `HEALTHY`, `CIRCUIT_OPEN` and `GUARDRAIL` events. Old `CIRCUIT_OPEN` and restart counts remain in the ledger as historical evidence from the first two failed canaries; they were not deleted or rewritten. The current post-fix window recorded healthy events for all four services.

## Guardrails and policy boundary

The installer did not modify `.env`, learning DBs, experiences, active policy or policy handoff ledger. The final checkpoint showed `SCP_ENABLE_CLOSED_LOOP=OFF`. `data\active_policies.json` and `data\policy_handoff_ledger.jsonl` were not created by this operation. The supervisor also forces `SCP_ENABLE_CLOSED_LOOP=0` in each child process, so the 24/7 process is for availability/observation and not automatic policy learning.

## Installation and rollback

The task name is `SCP-247-Supervisor`. It uses PowerShell 7 `pwsh.exe`, runs under the interactive user `check`, triggers at logon, and has `StartWhenAvailable`, battery-operation and unlimited execution-time settings. Before each wiring change, the previous supervisor script or scheduled-task XML was copied into `.private-secrets\release-audit\scp-247\` with a timestamped backup directory.

Rollback is:

1. Create the `KILL` file or run `scp_247_control.ps1 -Action kill`.
2. Confirm all four ports are closed.
3. Restore the timestamped `task-before.xml` if the task definition must be reverted.
4. Restore the timestamped `supervisor-before.ps1` if the supervisor code must be reverted.
5. Delete or disable the `SCP-247-Supervisor` task only after the rollback state is recorded.

## Remaining limits — DNA #22 and #25

This evidence proves the bounded canary and recovery path under the observed PC state. It does not yet prove clean-start behavior after a cold boot before user logon, Windows sleep/hibernate behavior, a second PC, prolonged provider outage, disk-full log rotation, or automatic circuit recovery after budget exhaustion. It also does not prove the SCP detection system can catch all AI or human attacks. The remaining next action is to run a controlled cold-boot/logon test and a bounded provider-outage simulation, then add log rotation and explicit circuit-reset evidence before calling the service production-grade.

## Versioned source

The 24/7 supervisor and controls are versioned in GitHub at commit [`e8ef171`](https://github.com/checken1994/GA-LAB/commit/e8ef171932c11595478d4def7d0584d7e74347cf). The installer PowerShell 7 wiring fix is at [`7503206`](https://github.com/checken1994/GA-LAB/commit/75032063533f984de9c9b674de608e7449eddbe0).
