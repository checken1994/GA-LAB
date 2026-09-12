# C1 — TaskKernel PostgreSQL Storage (ADOPT-AND-FIX Track C1, session 1)

> Branch: `audit/runtime-guard-AUDIT-20260909` · Base: `f91aacb` · Date: 2026-09-12
> Scope: PgKernelStorage + schema + dual-write parity + migration tool. Chaos testing + PG chaos/failover = session 2.

## Skill binding (SHA256, machine-checkable)

| Skill | SHA256 |
|---|---|
| `.agents/skills/scp-dna/SKILL.md` | `4aada0be4873598dc50c3a7f38d90151429bb5263c511a838ed1cdcb4d594d10` |
| `.agents/skills/scp-task-kernel-review/SKILL.md` | `f9b4e31004662c2c3e3ea88c5be755d29ee7b9268d667daae07d8c09b0bc1334` |
| `.agents/skills/scp-reality-verifier/SKILL.md` | `a9d65ce53b18f8310ceeb302b18b341a0e1b8b19cddc7f46d4fa6ee99432269e` |

## Commits (per milestone)

| # | SHA | Nội dung |
|---|---|---|
| 1 | `56ee632` | `psycopg[binary]==3.3.5` (pinned, production dep trong `scp/requirements.txt`) + canonical PG schema `scp/kernel_storage_pg_schema.sql` |
| 2 | `f2c25a6` | `scp/kernel_storage_pg.py` — `PgKernelStorage` đầy đủ KernelStorage contract |
| 3 | `b4ca417` | `make_storage()` postgres backend (`SCP_KERNEL_BACKEND`/`SCP_KERNEL_PG_DSN`) + `tests/T04_kernel/test_pg_storage_parity.py` |
| 4 | `b81bf54` | `scripts/migrate_kernel_sqlite_to_pg.py` + `tests/T04_kernel/test_pg_migration.py` |

Push chưa thực hiện (orchestrator giữ quyền push).

## Schema mapping (SQLite → PostgreSQL)

Nguồn: `TaskKernel._schema()` trong `scp/task_kernel_parts/taskkernel.py` (7 bảng + 1 index). Canonical PG DDL: `scp/kernel_storage_pg_schema.sql`.

| SQLite | PostgreSQL | Lý do |
|---|---|---|
| `TEXT` | `TEXT` | 1:1 |
| `INTEGER` | `BIGINT` | SQLite INTEGER là signed 64-bit |
| `REAL` | `DOUBLE PRECISION` | IEEE-754 8-byte, đúng IEEE của SQLite REAL |
| `BLOB` | `BYTEA` | kernel hiện không dùng (fail-closed nếu gặp trong migration) |
| timestamp | giữ `TEXT` ISO-8601 (`now_iso()` = UTC `+00:00`) | parity byte-level, so projection trực tiếp |

Bảng: `control` (kill switch + epoch), `tasks`, `events` (UNIQUE(task_id, seq) hash-chain), `leases` (+`idx_leases_task`), `checkpoints`, `idempotency`, `queue_accounts`. Hai đường materialize hội tụ: (1) runtime — kernel gửi DDL SQLite qua `executescript()` được translate; (2) ops — file canonical + migration tool.

## PgKernelStorage — methods count

Interface `KernelStorage` (Protocol, runtime_checkable): 10 members — `begin`, `commit`, `rollback`, `execute`, `executescript`, `fetchone`, `fetchall`, `in_transaction`, `close`, `backup_to`. **PgKernelStorage triển khai đủ 10/10** (checked against the Protocol; static A-level + runtime B-level).

Điểm thiết kế chính (giữ nguyên kernel semantics, không đụng `taskkernel.py`):
- **Write slot**: `BEGIN` + `pg_advisory_xact_lock(<fixed key>)` ≡ `BEGIN IMMEDIATE` — serialize toàn bộ write transaction của kernel (chặn race `_append_event` đọc max-seq); advisory lock luôn là lock đầu tiên → không sinh deadlock mới. OCC (`UPDATE ... WHERE version=?` + `rowcount`) giữ nguyên.
- **Lock timeout**: `set_config('lock_timeout', '10000ms', false)` trên MỌI per-thread connection (≡ `busy_timeout=10000`); bounded retry 25 lần; hết retry → raise `sqlite3.OperationalError` — cùng exception type với SQLite path (yêu cầu parity behavior).
- **Dialect translation tại biên storage** (quote-literal-aware, không f-string SQL): `?`→`%s`, `:name`→`%(name)s`, `INSERT OR IGNORE`→`ON CONFLICT DO NOTHING`, qualification cột trong `ON CONFLICT DO UPDATE SET` (PG bắt buộc định danh — SQLite thì không), `strftime('%s',col)`→`EXTRACT(EPOCH FROM col::timestamptz)`, DDL type map. Construct lạ → fail-closed (`sqlite3.OperationalError`).
- **PRAGMA emulation**: `table_info` (pg_catalog, whitelist 7 bảng kernel; bảng thiếu → rows rỗng như SQLite), `quick_check` (kiểm structural presence thật của 7 bảng — KHÔNG fake 'ok'; integrity nội dung do hash-chain `verify_integrity()` đảm nhiệm, backend-neutral). PRAGMA khác → fail-closed.
- **Rows**: `PgRow(dict)` hỗ trợ cả `row['col']`, `row[0]` và `.keys()` (parity `sqlite3.Row`, dùng bởi `verify_integrity()`/`"version" in row.keys()`).
- **Integrity**: psycopg integrity error → `StorageIntegrityError` (như SQLite path translate `sqlite3.IntegrityError`).
- **backup_to**: `pg_dump` (plain format, secret qua env PGPASSWORD, không nằm trên argv); không có pg_dump → RuntimeError fail-closed, không ghi snapshot cục. ⚠️ File dump là SQL (restore bằng psql) dù TaskKernel đặt suffix `.sqlite3` — đã ghi chú trong code + mục limitations.

## Factory

`make_storage(db_path, backend=None)` — thứ tự ưu tiên: param `backend` > `SCP_KERNEL_BACKEND` (mới; `postgres` yêu cầu `SCP_KERNEL_PG_DSN`, thiếu → RuntimeError fail-closed) > `SCP_STORAGE_BACKEND` (legacy; giữ nguyên contract sqlite-only fail-closed — `postgres` qua env này vẫn `NotImplementedError`, không để deployment nào lật engine âm thầm) > mặc định `sqlite` (KHÔNG đổi). Docstring giữ nguyên 2 câu SPOF warning bị test pin.

## Parity test results (Postgres THẬT — docker `postgres:16-alpine`, không mock)

`tests/T04_kernel/test_pg_storage_parity.py` — **15/15 PASS** (chạy với `SCP_PG_TEST_DSN` trên docker PG):
- `test_pg_parity_full_sequence`: cùng chuỗi thao tác deterministic chạy trên SQLite tmp VÀ PG, so normalized step-records + projection 7 bảng (control/tasks/events/leases/checkpoints/idempotency/queue_accounts). Chuỗi gồm: create×3, transition flow, duplicate create (StorageIntegrityError), OCC stale version (OptimisticLockError), direct-to-COMPLETED (InvalidTransition), claim → start → checkpoint → idempotency claim/replay/complete → VERIFYING → commit_completed COMPLETED, heartbeat + heartbeat unknown lease (StaleLease) + heartbeat after release (fencing), release, global kill ON (claim khi kill → KillSwitchActive) / OFF, set_task_kill + kill lại terminal (InvalidTransition), rebuild_projection, verify_journal, recover_on_boot, verify_integrity. Normalization CHỈ phủ trường nondeterministic-by-design: random ids (evt_/lease_/cp_/attempt_), timestamps, hash sinh từ nội dung chứa random id, vendor wording của StorageIntegrityError — hash-chain validity được assert RIÊNG per backend (không bị nuốt).
- `test_pg_parity_occ_conflict_across_instances`: 2 storage instances cùng backend, stale version `rowcount==0` trên CẢ SQLite lẫn PG.
- 9 translator/factory unit tests chạy LUÔN không cần PG (placeholders, INSERT OR IGNORE, upsert qualification, strftime, DDL map, fail-closed constructs, PRAGMA fail-closed, missing-DSN RuntimeError, legacy env NotImplementedError).

Skip discipline: thiếu `SCP_PG_TEST_DSN` → 8 test PG skip với lý do tường minh (docker command kèm theo) — **declared infra-skip, không phải skip để qua lỗi**; chỉ 1 test fail duy nhất trong suite là pre-existing (xem dưới). Khi env SET nhưng PG không reachable → skip với prefix `INFRA-SKIP:` + error gốc (visible trong log).

## Migration results (synthetic SQLite → docker PG)

`tests/T04_kernel/test_pg_migration.py` — **2/2 PASS**:
- E2E: synthetic kernel DB (3 task, 14 events, 1 lease, 1 queue_account, kill switch on/off, 1 task CANCELLED) → tool subprocess:
  1. `--dry-run` trên target trống: báo plan, **không tạo gì** (`_schema_exists` vẫn False sau dry-run);
  2. migrate thật: counts khớp 7/7 bảng, atomic transaction;
  3. re-run không `--truncate` → exit 2 fail-closed "not empty", dữ liệu không đổi;
  4. re-run `--truncate` → idempotent, counts khớp;
  5. mở kernel trên PG sau migrate: `mig-a` RUNNING, `mig-c` CANCELLED, `recover_on_boot.corrupted == []` (hash-chain sống sót qua migrate), `verify_integrity` ok trên 4 journal chain (3 task + `__global__`).
- Missing source file → exit 2 fail-closed.

An toàn: shape check cột 1:1 fail-closed; BLOB abort; identifier chỉ qua `psycopg.sql.Identifier` từ whitelist compile-time (`COPY_ORDER == KERNEL_TABLES`); kernel write-slot session advisory lock suốt migration; password không ra argv/stdout (redact).

## Baseline SQLite regression (reality check)

| Run | Lệnh | Kết quả | Exit code |
|---|---|---|---|
| Baseline (trước commit đầu tiên) | `python -m pytest tests/T04_kernel/ -q` | 176 passed, **1 failed** (pre-existing) | 1 |
| Sau milestone 4, KHÔNG có env PG | như trên | 185 passed, 8 declared infra-skips, **1 failed (giống hệt baseline)** | 1 |
| Sau milestone 4, CÓ env PG (docker) | như trên | 193 passed, **1 failed (giống hệt baseline)** | 1 |

⚠️ **Baseline KHÔNG phải exit 0 như giả định đề bài**: fail duy nhất `tests/T04_kernel/test_adversarial_kernel_flaws.py::test_branch_9_task_kernel_bridge_policy_denial_integration` — `PermissionError: CapabilityRequiredError` tại `scp/hands/task_kernel_bridge.py:314`, tồn tại TRƯỚC mọi commit của phiên này (xác minh bằng baseline run trước khi thêm code; thay đổi của phiên không import được vào path này). Ngoài scope Track C1 (hands capability, không phải storage) → không tự ý sửa, báo orchestrator (FA-11: không làm ngơ; cần session riêng cùng root cause nếu được chỉ định).

## Reality-verifier verdict

**VERIFIED (PASS_WITHIN_SCOPE)** — claim: "PgKernelStorage triển khai đủ KernelStorage contract, parity với SQLite trên chuỗi thao tác kernel thực, migration 1:1 verified counts, SQLite baseline không đổi". Bằng chứng: 17/17 test mới PASS trên PG thật (docker, image digest `sha256:cf78e766...`), exit codes thu trực tiếp (không qua pipe), commit SHAs trên.

## Limitations (chưa được chứng minh — cho session 2)

1. **Chaos/failover PG chưa test** (connection drop giữa transaction, restart PG, pool exhaustion) — theo plan là phiên sau.
2. **Multi-process OCC trên PG** mới test 2 instance trong 1 process + threads; chưa có probe đa process như `tools/probe_gap05_occ_multiprocess.py`.
3. **backup_to** phụ thuộc pg_dump trên PATH; chưa test restore round-trip; suffix file vẫn `.sqlite3` do TaskKernel hardcode (kernel untouched).
4. **PgKernelStorage chỉ được consume qua TaskKernel SQL surface hiện tại** — SQL SQLite-dialect mới của kernel tương lai có thể cần mở rộng translator (fail-closed sẽ báo thay vì chạy sai).
5. Load/performance PG vs SQLite chưa đo (scope là correctness parity).
6. Container test đã teardown (`docker stop scp-pg-test`); không để lộ DSN password trong repo (DSN chỉ qua env).
