# SCP PC structure-debt baseline

## Snapshot

| Field | Observed value |
|---|---|
| Machine | User Windows PC |
| Repository | `C:\Users\check\Downloads\scp` |
| Branch | `main` |
| HEAD | `4e47add244edadfc1eb53baa4f75ebf239a75e82` |
| Remote | `https://github.com/checken1994/GA-LAB.git` |
| Snapshot time | `2026-08-25T00:26:10.1861851+07:00` |
| Working-tree entries | 93 changed/untracked entries reported by `git status --porcelain=v1` |
| Production port | No listener observed on port 8000 in the snapshot command |
| Isolated port | No listener observed on port 8002 in the snapshot command |

## Observed structure debt

| Item | Observed value |
|---|---:|
| Tracked backup-like paths | 3 |
| Tracked backup-like paths listed | `scp/core/auto_backup.py`, `scp/core/github_backup.py`, `scp/core/smart_classifier.py.tier3bak` |
| `judgecore_mixin.py` lines | 3,325 |
| `judge()` location | line 93 |
| `judge_pipeline.py` | absent |
| `judge_state.py` | absent |
| `judge_phase_*` modules | absent |
| `exception_policy.py` | absent |
| Root `Dockerfile` | absent |
| `.github/workflows/ci.yml` | absent |
| `pytest.ini` test path | `tests` |
| Existing test directory | `scp/tests` and top-level `tests` both exist |

## Safety conclusion

The PC repository is not a clean checkout and is not the same snapshot as `checken1994/scp-agent` in the sandbox. Existing dirty changes must be preserved. No blind overwrite, reset, clean, stash, or production-port restart is allowed. Changes must be isolated on a new branch or a separate worktree, with postconditions recorded after every batch.

The original request mentions 41 `.bak` files, but this PC Git index exposes only three backup-like paths, two of which are functional modules. The cleanup must not delete `auto_backup.py` or `github_backup.py`; only confirmed artifact files may be removed after a separate filesystem inventory.
