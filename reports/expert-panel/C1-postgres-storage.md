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

---

# Phiên 2 (C1s2) — 2026-09-12

## Skill pins (SHA256, đọc trước khi làm việc theo binding)

| SKILL.md | SHA256 |
|---|---|
| `.agents/skills/scp-dna/SKILL.md` | `4aada0be4873598dc50c3a7f38d90151429bb5263c511a838ed1cdcb4d594d10` |
| `.agents/skills/scp-task-kernel-review/SKILL.md` | `f9b4e31004662c2c3e3ea88c5be755d29ee7b9268d667daae07d8c09b0bc1334` |
| `.agents/skills/scp-reality-verifier/SKILL.md` | `a9d65ce53b18f8310ceeb302b18b341a0e1b8b19cddc7f46d4fa6ee99432269e` |

## Milestone 1 — Triage branch-9 fail (pre-existing từ phiên 1)

**Verdict: TEST pin contract CŨ — sai; product (M4) đúng.** Bằng chứng:

- Fail: `PermissionError: CapabilityRequiredError: Hands action requires an authorized capability token (FA-05)` tại `scp/hands/task_kernel_bridge.py:314` khi `capability_token=None`.
- Product change: commit `0d13c85` (M4 FIX 2026-09-11) cố ý đổi thứ tự fail-closed: token không parse được → `PermissionError` TRƯỚC `registry.require` và TRƯỚC mọi kernel mutation (task/lease/idempotency/checkpoint). Contract mới được pin bởi `tests/T03_capability/test_flow_04_control_hands_scp_standard.py::test_hands_executor_rejects_missing_token_fail_closed` (không có test T04 nào pin contract mới).
- Test cũ (`test_branch_9...`, viết pre-M4) pin contract cũ "kernel mutation trước authz" — vi phạm FA-05 intent: caller KHÔNG được phép tạo kernel side effects khi chưa authorized.

**Fix (test-only, strictness TĂNG):** `tests/T04_kernel/test_adversarial_kernel_flaws.py` — test viết lại 2 leg:
- Leg A (mới, pin contract M4): `capability_token=None` → `pytest.raises(PermissionError)` với cả marker `CapabilityRequiredError` + `FA-05`; đồng thời chứng minh KHÔNG kernel mutation: `request_key` cố định → task id deterministic `bridge._task_id(...)` → `kernel.get_task` phải raise `NotFound`.
- Leg B (giữ intent gốc): token CapabilityToken hợp lệ (HMAC signature thật qua `get_capability_secret`/`compute_token_signature`) → executor PEP từ chối → bridge route `commit_failed()` → FAILED, `active_lease_id is None`, đúng 1 `TASK_FAILED`, indictment `hands://.../policy_denied/restricted_read`, actor == worker_id, + THÊM strictness: `verify_journal(task_id).hash_chain_valid is True`.

Reality test: `python -m pytest "tests/T04_kernel/test_adversarial_kernel_flaws.py::test_branch_9_task_kernel_bridge_policy_denial_integration" -x -q` → **1 passed**, exit 0. Không sửa product (không cần), không skip/xfail, không hạ assertion nào.

## Progress log — phiên 2 (2026-09-12, branch audit/runtime-guard-AUDIT-20260909)

| Milestone | Commit | Kết quả |
|---|---|---|
| 1. Triage branch-9 | `60abc1d` | Verdict: test pin contract CŨ (pre-M4, kernel mutation trước authz — sai); product M4 (`0d13c85`) đúng. Test T04 viết lại 2 leg, strictness TĂNG: (A) token thiếu → `PermissionError` (`CapabilityRequiredError` + `FA-05`) + KHÔNG kernel state (task id deterministic → `NotFound`); (B) token hợp lệ → denial route `commit_failed` → FAILED + indictment `hands://…/policy_denied/…` + journal chain valid. Pytest: 1 passed, exit 0. |
| 2. Chaos Pg | `79ced21` | `tests/T04_kernel/test_pg_storage_chaos.py` — 4/4 PASS ×2 lần chạy độc lập, exit 0 (4.89s / 4.85s): (a) `pg_terminate_backend` giữa write transaction → instance chết fail LOUD (`sqlite3.OperationalError`, type parity SQLite), write chưa commit rollback sạch, instance mới: version nguyên, `verify_integrity` ok, journal valid, `recover_on_boot` corrupted=[]; (b) `docker restart` giữa claim → stale conn raise đúng type, `recover_on_boot` LEASED→RECOVERING, orphan lease released, task re-claim end-to-end (fencing tăng); (c) 2 process spawn race `claim_next` → đúng 1 lease (1 row leases, 1 LEASE_GRANTED, loser sạch); (d) `backup_to` → pg_dump thật (binary trong container qua test-support PATH shim — host không có pg_dump, fail-closed contract giữ nguyên) → restore DB mới bằng psql thật → `verify_integrity` ok + tasks/control/event-counts khớp + kill-switch state giữ nguyên. |
| 3. Boot-on-Pg runtime | `005e928` | `tests/T04_kernel/test_pg_boot_runtime.py` — 2/2 PASS exit 0 (1.17s): full lifecycle qua TaskKernel API thật (create→PLANNING/READY/QUEUED→claim/lease→start→idempotency claim→checkpoint→heartbeat→VERIFYING→VerifierReceipt HMAC→`commit_verification_result`→COMPLETED) + `verify_integrity`/journal chain/`rebuild_projection`/recover_on_boot sạch/idempotency replay no-op; crash path: worker chết giữa RUNNING → HUMAN_REVIEW → operator loop → QUEUED → worker mới (fencing tăng) → COMPLETED. **SQLite-assumption census: 2 chỗ** (bridge `sqlite3.IntegrityError` dead except-leg `task_kernel_bridge.py:364`; `TaskKernel.backup()` hardcode `.sqlite3` suffix) — ghi nhận, KHÔNG sửa (ngoài scope; hành vi đúng cả 2 backend). Kernel core backend-neutral (không import sqlite3 trực tiếp). |
| 4. Final regression | — | T04 FULL với `SCP_PG_TEST_DSN`: **200 passed, 0 failed, exit 0** (21.21s) — trước phiên: 193 passed + 1 failed (branch-9). T03 FULL: **709 passed, 0 failed, exit 0** (90.60s) sau 2 harness repair (`72da6d3`): (1) `test_hands_authority_pep.py` bridge missing-token test cùng root cause branch-9 → cập nhật theo contract M4, strictness tăng (ZERO kernel state thay vì FAILED row); (2) flow-08 flaky do rate-limit accounting 60s process-wide chảy giữa các file T03 → thêm autouse isolation fixture (pattern có sẵn T02/flow-06), product logic + assertion 401/403 giữ nguyên. |
| 5. Closure record | (commit này) | `reports/circuit-closures/C1-postgres-closure.json` (D0–D8 thu gọn, sha_pin `72da6d3…`) + evidence vào `reports/circuit-closures/C1-evidence/` (parity/migration, chaos, boot, T04, T03, D2 docker PG runtime) + STATUS-LEDGER thêm hàng Track C1. |

### Evidence files (C1-evidence)

- `pytest-pg-parity-migration.txt` — 17 passed exit 0 (parity sequence SQLite↔PG + migration e2e)
- `pytest-pg-chaos.txt` — 4 passed exit 0 (chaos a–d)
- `pytest-pg-boot-runtime.txt` — 2 passed exit 0 (boot-on-Pg lifecycle)
- `pytest-T04-full-final.txt` — 200 passed exit 0 (T04 full, PG env)
- `pytest-T03-final.txt` — 709 passed exit 0 (T03 full)
- `D2-docker-pg-runtime.txt` — container `scp-pg-test`, image `sha256:cf78e766…` (cùng digest phiên 1), PG 16.15, pg_isready ok

## Reality-verifier verdict (phiên 2)

**VERIFIED (PASS_WITHIN_SCOPE)** — claim: "PgKernelStorage chịu được chaos kill-connection/restart, claim race đa process đúng 1 lease, backup round-trip khớp, TaskKernel chạy full lifecycle thật trên PostgreSQL, và không làm đỏ T04/T03". Bằng chứng: 6 file evidence ở trên (pytest exit codes thu trực tiếp, không qua pipe trung gian), commit SHAs pinned, image digest khớp phiên 1. DSN password chỉ qua env, không in vào bất kỳ file nào.

## Limitations còn lại (cho session/coordinator sau)

1. **Performance chưa đo** (PG vs SQLite latency/throughput) — known_gaps số 1 của closure.
2. **Multi-node/HA chưa chứng minh** — single-node durability only.
3. **NOTIFY/LISTEN event bus = Track C2 riêng** — không thuộc C1.
4. D4 seal chưa quét lại các commit Track C1; D5 chưa có reviewer độc lập riêng; D7 CIRCUIT-FLOW-MAP + header chưa có hàng Track C1.
5. `backup_to` trên host không có pg_dump → RuntimeError fail-closed (đúng contract); round-trip được chứng minh qua pg_dump binary trong container; host-native path chỉ chứng minh được trên máy có binary.
6. SQLite-assumption census 2 chỗ chưa sửa (ngoài scope, cần session riêng nếu muốn clean-up).

---

# C2 — PgEventBus (durable table + NOTIFY wake-up) — 2026-09-12

> Branch: `audit/runtime-guard-AUDIT-20260909`, tiếp nối sau closure C1 (`6184b7e`).
> Worker Agent C2. Thiết kế bắt buộc: **bảng `scp_events` durable là source of
> truth; NOTIFY chỉ là chuông wake-up** — NOTIFY mất ≠ event mất.

## Skill binding (SHA256, đọc đầu phiên C2 — không đổi so với pin C1)

| Skill | SHA256 |
|---|---|
| `.agents/skills/scp-dna/SKILL.md` | `4aada0be4873598dc50c3a7f38d90151429bb5263c511a838ed1cdcb4d594d10` |
| `.agents/skills/scp-task-kernel-review/SKILL.md` | `f9b4e31004662c2c3e3ea88c5be755d29ee7b9268d667daae07d8c09b0bc1334` |
| `.agents/skills/scp-reality-verifier/SKILL.md` | `a9d65ce53b18f8310ceeb302b18b341a0e1b8b19cddc7f46d4fa6ee99432269e` |

## Commits (per milestone)

| # | SHA | Nội dung |
|---|---|---|
| 1 | `c0867c5` | `scp/event_bus_pg_schema.sql` (bảng `scp_events`: id BIGSERIAL, channel, payload JSONB, created_at, delivered_at NULLABLE, correlation_id, attempts, dead; index (channel,id) + partial undelivered) + `scp/event_bus_pg.py` (`PgEventBus.publish/subscribe_poll/replay_undelivered/ensure_schema` + factory `make_event_bus`) |
| 2 | `5b4a6da` | `tests/T04_kernel/test_pg_event_bus.py` — 9/9 PASS ×2 lần chạy độc lập trên docker PG thật + evidence `C2-evidence/` |
| 3 | (commit này) | Closure record `reports/circuit-closures/C2-eventbus-closure.json` + STATUS-LEDGER hàng Track C2 |

## Thiết kế đã chứng minh

- **publish() = INSERT + `pg_notify(channel, event_id)` trong CÙNG transaction** (atomic, psycopg `conn.transaction()`): row thấy được ⇔ bell có thể kêu; bell payload chỉ là event id (message là row trong bảng). Fail-closed: mọi lỗi publish raise, không row mồ côi; connection được cleanup (rollback) rồi re-raise nguyên gốc.
- **subscribe_poll()**: cursor id (last_seen_id) poll bảng `dead = FALSE ORDER BY id`; LISTEN qua connection riêng, chờ bằng `select.select`; NOTIFY đến → drain non-blocking (`notifies(timeout=0)`) → poll ngay (deadline=0). Thứ tự khởi động an toàn: LISTEN trước, snapshot cursor sau → tail-start không mất event. Connection chết → raise loudly (events vẫn durable; recovery = restart + replay).
- **Handler exception**: log kèm traceback + KHÔNG mark delivered + attempts+1 + cursor KHÔNG tiến (head-of-line bounded) → retry lần sau; đủ `max_attempts` (default 3) → `dead=TRUE` + log CRITICAL + cursor tiến qua (poison message không chặn channel vô hạn).
- **replay_undelivered()**: một pass mọi `delivered_at IS NULL AND dead=FALSE` theo id; fail → vẫn để undelivered cho lần replay sau (fetch cursor tiến để không tái xử lý trong cùng pass).
- **Fan-out**: mỗi subscriber cursor riêng; `delivered_at` là ack cấp channel ("ít nhất một subscriber đã xử lý") dùng bởi replay — per-subscriber semantics nằm ở cursor, không ở cột.
- **Security**: 100% parameterized DML (kể cả chuỗi channel `pg_notify(%s)`); LISTEN compose bằng `sql.Identifier`; channel validate `^[A-Za-z0-9._:-]{1,63}$`; DSN chỉ log dạng redacted (`***`); không f-string SQL.

## Test results (docker `postgres:16-alpine`, digest `sha256:cf78e766…` — cùng image C1, PG 16.15, no-mock)

`tests/T04_kernel/test_pg_event_bus.py` — **9/9 PASS, exit 0, ×2 lần chạy độc lập** (3.52s / 3.54s; evidence `pytest-pg-event-bus-run1.txt`, `run2`):

| # | Test | Kết quả |
|---|---|---|
| a | publish → poll nhận đúng payload + correlation_id, đúng thứ tự id, delivered_at set | PASS |
| b | **listener chết giữa chuỗi publish** (0 subscriber) → 5 events durable, delivered_at NULL → instance PgEventBus MỚI replay_undelivered → đủ 5, đúng thứ tự id, đúng payload, attempts=0, dead=FALSE; sau đó publish mới + subscriber mới sống lại | PASS (test then chốt) |
| c | handler raise 2 lần → retry → lần 3 pass → delivered; attempts==2, dead=FALSE, đúng 3 lần chạy handler | PASS |
| d | handler raise > max_attempts → dead=TRUE đúng sau 3 attempts + log CRITICAL (caplog), KHÔNG loop vô hạn; event khỏe tiếp theo vẫn delivered (cursor trôi qua dead row) | PASS |
| e | NOTIFY wake-up: poll_interval=60s, handler nhận event <10s và stats.notify_wakes ≥ 1 → bell path, không phải periodic poll | PASS |
| f | 2 subscriber cùng channel → cả hai nhận đủ 3 events đúng thứ tự (fan-out qua cursor riêng) | PASS |
| g | publish fail-closed: payload không serialize được → raise, 0 row durable; channel invalid → ValueError trước khi chạm DB; connection sống sau publish lỗi | PASS |
| h | schema objects trên PG thật: 8 cột (delivered_at NULLABLE), index (channel,id) + partial undelivered index | PASS |
| i | factory không cần PG: default → None (disabled); enabled thiếu `SCP_EVENT_BUS_DSN` → RuntimeError fail-closed | PASS |

Regression: **T04 FULL với `SCP_PG_TEST_DSN`: 209 passed, 0 failed, exit 0** (25.18s; `pytest-T04-full-after-C2.txt`) = 200 của C1 + 9 mới. Không skip/xfail để qua lỗi; thiếu env → 8 declared infra-skips + docker hint (`pytest-pg-event-bus-skip-mode.txt`), test (i) vẫn chạy không cần PG.

## Wiring

`make_event_bus()` — opt-in như C1: `SCP_EVENT_BUS_ENABLED` falsey/mất → `None` (caller phải xử lý None); truthy + `SCP_EVENT_BUS_DSN` → `PgEventBus`; truthy thiếu DSN → RuntimeError fail-closed (không fallback âm thầm). Chưa wire vào TaskKernel/dashboard (known gap).

## Reality-verifier verdict (C2)

**VERIFIED (PASS_WITHIN_SCOPE)** — claim: "pattern bảng-durable + NOTIFY-wake hoạt động thật trên PostgreSQL; NOTIFY mất không làm mất event; retry/dead-letter bounded; không làm đỏ T04". Bằng chứng: pytest exit codes thu trực tiếp ×2 runs trên PG 16.15 docker thật (no-mock), regression T04 209/0. Verdict chỉ đúng trong phạm vi: single-node, infra + API, handler test giả định đơn giản; chưa gồm kernel wiring/multi-node/performance.
