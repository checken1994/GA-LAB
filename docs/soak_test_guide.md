# SCP TaskKernel soak test

The harness runs complete TaskKernel lifecycles, verifies every task journal,
performs periodic database-wide integrity checks, and writes atomic progress
evidence. It never deletes or reuses an existing database.

## Short validation

```powershell
python scripts/scp_soak_test.py --duration-seconds 10 --run-id smoke --output-dir reports/soak/smoke --workers 2 --batch-size 2 --interval-seconds 0.2 --integrity-interval-seconds 2 --report-interval-seconds 1 --min-free-mb 128
```

## Overnight run (24 hours)

```powershell
python scripts/scp_soak_test.py --duration-hours 24 --run-id <commit>-<timestamp> --output-dir reports/soak/<commit>-<timestamp> --workers 4 --batch-size 2 --interval-seconds 5 --integrity-interval-seconds 900 --report-interval-seconds 60
```

The evidence files are:

- `progress.json`: atomic current/final status, counters, latency, integrity and
  Git/Python/platform provenance;
- `events.jsonl`: append-only start, progress, integrity and final snapshots;
- `kernel.sqlite3`: workload database; the final report records its SHA-256.

`COMPLETED` proves only that the configured duration ended with no observed
workload error, SQLite quick-check failure or invalid journal chain. A running,
interrupted or missing report is not a successful soak. The PC and user session
must remain powered, with adequate disk space, for the full duration.
