# A — Mạch 1 (Boot & Background) fixes

- Agent: A (SCP Worker Agent)
- Branch: `audit/runtime-guard-AUDIT-20260909`, HEAD `fe4bc8d` (chưa commit — working tree)
- Ngày: 2026-09-09
- Scope files: đúng danh sách owner cho phép; KHÔNG commit; KHÔNG đụng `.env`, compose.yml, `scp/api/_lifespan.py` (dead code).

## Fix 1 — Registry watchdog sống lại

**File:line**
- `scp/api_server_parts/lifespan.py:355-368` — gọi `_bg_registry.start_all()` ngay trước `yield` (sau khi mọi `@registry.register` đã chạy), bọc trong try/except **re-raise**: required job fail → boot fail (fail-closed đúng contract `required=True`). Shutdown đã có sẵn `registry.stop_all()` (dòng ~385).
- `scp/api/background_jobs.py:210-232` — thêm `_get_kernel_or_none()`: resolve kernel thật theo thứ tự (1) `scp.api._shared.get_kernel` (future contract), (2) reuse `scp.api_server._ASK_KERNEL_ADAPTERS[*].kernel` (chỉ reuse, không trigger side-effect init).
- `scp/api/background_jobs.py:249-252, 266-268` — 2 required job dùng resolver thay cho `from scp.api._shared import get_kernel` + `except ImportError: pass` cũ.
- `scp/api/background_jobs.py:60-71` — log một dòng `"first execution completed"` khi job execute lần đầu (evidence chạy thật, không chỉ thread scheduled).

**Phát hiện ngoài scope nhưng đúng điểm lỗi (DNA #26):** `scp.api._shared` KHÔNG hề có `get_kernel` (PEP 562 `_DELEGATED_NAMES` không chứa nó) → ngay cả khi `start_all()` được gọi, 2 required watchdog sẽ vẫn no-op thầm lặng mãi (ImportError→pass). Đã sửa resolver trong `background_jobs.py` (file nằm trong danh sách cho phép) để watchdog tác động lên kernel thật của app.

**Evidence (docker compose logs scp-api, container scp-scp-api-1, boot 18:15:32):**
```
[BackgroundJobRegistry] Started: kernel_lease_expiry (required=True)
[BackgroundJobRegistry] Started: kernel_orphan_reconcile (required=True)
[BackgroundJobRegistry] Started: canary_token_cleanup (required=False)
[BackgroundJobRegistry] Started: deep_audit_scheduler (required=False)
[BackgroundJobRegistry] Started: attack_mode_monitor (required=False)
[MACH1-FIX-1] Background job registry started (5 jobs: attack_mode_monitor, canary_token_cleanup, deep_audit_scheduler, kernel_lease_expiry, kernel_orphan_reconcile)
[BackgroundJob] kernel_lease_expiry: started (interval=30s)
[BackgroundJob] kernel_lease_expiry: first execution completed
[BackgroundJob] kernel_orphan_reconcile: started (interval=60s)
[BackgroundJob] kernel_orphan_reconcile: first execution completed
[BackgroundJob] deep_audit_scheduler: started (interval=86400s)
```

## Fix 2 — Boot config gate fail-closed

**File:line:** `scp/api_server_parts/lifespan.py:49-55` — `validate_boot_config()` là lệnh đầu tiên trong lifespan, NGOÀI try/except: `ConfigContractError` lan lên → uvicorn không boot.

**Evidence (Docker boot 18:15:32):**
```
[ConfigContract] Boot config OK — 2 required vars validated.
[MACH1-FIX-2] Boot config contract validated (fail-closed)
```
Container boot OK → `.env` (env_file) đủ `SCP_JWT_SECRET` + `SCP_ADMIN_KEY` (chỉ kiểm tra tên biến tồn tại qua `printenv`, không đọc/hiện giá trị). Nhánh "boot gate blocked" KHÔNG xảy ra.

**Test:** `test_causal_boot_config_missing_jwt_secret_raises` (monkeypatch.delenv — fixture chuẩn, không mock) PASSED.

## Fix 3 — RetryPolicy thật (phương án A)

**File:line**
- `scp/policy/retry_policy.py:71-96` — thêm `run_background(interval_sec, stop_event)`: loop chờ interval (Event hoặc sleep) → observe toàn bộ plans từ `get_plans_fn` → `check_and_retry()`.
- `scp/policy/retry_policy.py:33-36` — `observe()` chấp nhận thêm state `RETRY_SCHEDULED` (task kernel park chờ retry).
- `scp/policy/retry_policy.py:60-63` — `check_and_retry()` fallback `step_id=""` cho plan dạng flat task dict (không có `steps`) thay vì skip → retry thật được gọi. (Đã grep: không có caller production khác của `check_and_retry` ngoài lifespan → thay đổi an toàn.)
- `scp/api_server_parts/lifespan.py:294-352` — thay block stub: `_get_waiting_plans` = SELECT thật `SELECT task_id, state FROM tasks WHERE state='RETRY_SCHEDULED'` trên TaskKernel DB (path: `SCP_KERNEL_DB_PATH` ưu tiên, fallback `SCP_DATA_DIR/ask_task_kernel.sqlite3` — cùng convention với block doubt-cron/recovery hiện có); `_retry_plan` = `TaskKernel.transition(task_id,'QUEUED',actor='retry_policy',reason='retry_policy_background')` (state machine thật validate RETRY_SCHEDULED→QUEUED); thread daemon có `stop_event` (shutdown set qua `app.state.retry_policy_stop`, `lifespan.py:373`); poll interval `SCP_RETRY_POLL_SEC` (default 60s).

**Evidence:** log boot: `[RESTORED-SYSTEMS] RetryPolicy background thread started (real kernel wiring, db=/var/lib/scp/data/ask_task_kernel.sqlite3)`. Test end-to-end `test_causal_retry_policy_run_background_requeues_kernel_task`: TaskKernel SQLite tmp THẬT, tạo task → PLANNING→READY→QUEUED→claim→start→`commit_failed(RETRYABLE)` → `RETRY_SCHEDULED` → `run_background` requeue → assert state `QUEUED` PASSED (không có mock nào).

## Fix 4 — /ask 503 gate

**File:line:** `scp/api_server.py:483-495` — đầu route `/ask` (sau counter, trước kernel gate): `judge_ready` False → `JSONResponse 503 {"detail": "judge_initializing", "reason": ..., "retry_after_seconds": 5}`.

**Evidence:**
- In-process (app thật + config thật `SCP_JUDGE_START_DELAY_SEC=180`, không mock): `test_causal_ask_returns_503_while_judge_not_ready` PASSED (503 + detail đúng).
- Docker smoke: `POST /ask` trả **401** — dependency auth (`Depends(get_current_user)`) chạy TRƯỚC body route nên request không có/ sai token không chạm được gate 503. Deployment này judge ready < ~20s sau boot (window `t=10s readiness=000` → `t=20s readiness=200`), nên không thể curl 503 từ ngoài mà không có JWT hợp lệ (không được phép mint từ secret thật). Owner đã cho phép 401 trong smoke và TestClient làm evidence.

## Fix 5 — Credentials ra khỏi source

**File:line**
- `scripts/run_scp_acceptance.py:261-265, 271-272` — `OPENROUTER_API_KEY` / `OPENAI_API_KEY` thay literal bằng `os.environ.get("<CÙNG_TÊN>", "")` (2 key này trỏ vào loopback provider cục bộ nên rỗng vẫn chạy).
- `.env.example:69-84` — block mới "External data-source credentials" với giá trị RỖNG cho `OPENROUTER_API_KEY, OPENAI_API_KEY, EIA_API_KEY, USDA_API_KEY, NVD_API_KEY, CASE_LAW_API_KEY, GOOGLE_FACT_CHECK_API_KEY, NASA_API_KEY` + ghi chú `SCP_GIT_SHA` do build-arg inject.
- Scan residue: `grep -rniE "(sk-[a-f0-9]{8,}|api_key\s*=\s*[\"'][a-zA-Z0-9]{10,})"` trên wiremixin.py + run_scp_acceptance.py → 0 match.

**Điểm KHÔNG sửa + lý do (evidence-first):** `scp/autofix/evolution_parts/wiremixin.py:54-59` KHÔNG chứa giá trị API key nào — đó là dict map TÊN biến env → đường dẫn data_source file (vd `"EIA_API_KEY": "scp/data_sources/energy.py"`). Scan toàn file không thấy secret value (không `sk-`, không literal dài). Không thể "thay giá trị hardcode bằng os.environ.get" khi không có giá trị → không tự chế patch hình thức. `scp/data_sources/*.py` nằm NGOÀI danh sách file được phép nên không audit sâu thêm tại đây.

## Fix 6 — Commit SHA vào image

**File:line**
- `Dockerfile:33-39` — `ARG SCP_GIT_SHA=unknown` + `ENV SCP_GIT_SHA=${SCP_GIT_SHA}` (không đụng phần compose/Dockerfile orchestrator đã fix).
- `scp/api_server.py:98-115` (`_scp_service_identity`) — ưu tiên `SCP_GIT_SHA` env (bỏ qua literal `"unknown"`) trước git subprocess.

**Evidence:** `docker build --build-arg SCP_GIT_SHA=fe4bc8d26f268222943e7ae30aed87267b3a2443 -t scp-api:sha-verify .` (exit 0) → run container tạm `scp-sha-verify` (port 18000, env test throwaway: JWT/ADMIN/CAPABILITY secret dạng `image-verify-only-throwaway-*`, KHÔNG phải secret thật, không ghi vào file nào) → `GET /health` → `COMMIT= fe4bc8d26f268222943e7ae30aed87267b3a2443 STATUS= ok` — đúng build-arg. Container tạm + tag đã xoá sau verify.

## Fix 7 — Nâng chuẩn test T01 (không mock)

**File:line:** `tests/T01_boot/test_flow_01_boot_background_scp_standard.py`
- Xoá 10 method causal rỗng (`pass`) — thay bằng 7 test THẬT (lớp `TestFlow01BootBackgroundCausalCoverage`, dòng ~370+):
  1. `test_causal_boot_config_missing_jwt_secret_raises` — delenv → `ConfigContractError`.
  2. `test_causal_lifespan_starts_required_registry_jobs` — `stop_all()` normalize → `TestClient(app)` (app thật) → 2 required job `_started` + thread `is_alive` + shutdown stop lại.
  3. `test_causal_ask_returns_503_while_judge_not_ready` — config thật `SCP_JUDGE_START_DELAY_SEC=180`, JWT thật mint bằng `create_access_token` → 503.
  4. `test_causal_ask_invalid_token_returns_401` — auth chạy trước gate.
  5. `test_causal_retry_policy_run_background_requeues_kernel_task` — TaskKernel tmp thật, full state machine, requeue QUEUED.
  6. `test_causal_doubt_cron_escalation_backlog_real_sqlite` — UN-MOCK: `_check_escalation_backlog` chạy trên SQLite tmp thật (kernel thật, 1 task HUMAN_REVIEW qua state machine thật) → `total==1`, `backlog["HUMAN_REVIEW"]==1`.
  7. `test_causal_registry_starts_and_stops_registered_job` — start/stop execution evidence.
- Un-mock `test_lifespan_initializes_otel_telemetry`: bỏ 4 lớp `patch` trên dead module `scp/api/_lifespan`; bỏ import dead module.
- Env fixture module-level: `os.environ.setdefault` cho `SCP_JWT_SECRET`/`SCP_ADMIN_KEY` (giá trị test throwaway 32+ ký tự, không thuộc FORBIDDEN_VALUES; setdefault không ghi đè env thật). Lý do: lifespan thật giờ fail-closed, suite phải hermetic khi không có .env.
- Các doubt-cron test mock cũ (fitness/kernel/why) GIỮ NGUYÊN theo chỉ định "un-mock quá nặng thì giữ nguyên"; không skip/xfail/weaken assertion nào.
- Không bị chặn PROTECTED_PATHS (ghi file tests/ thành công).

## VERIFY CUỐI (output thật)

1. `python -m pytest tests/T01_boot/test_flow_01_boot_background_scp_standard.py -q` → **25 passed in 7.98s** (baseline 28 = 25 cũ giữ nguyên + xóa 10 stub; sau fix 25 = 25 cũ + 7 mới − 10 stub... thực tế: 18 test cũ pass giữ nguyên + 7 test mới).
   Chi tiết verbose: toàn bộ 25 PASSED, 0 skipped, 0 xfailed.
2. `python -m pytest tests/T01_boot/ tests/T03_capability/test_api_token_boundary.py -q` → **38 passed in 7.94s** (PYTEST_EXIT=0). Không regression.
3. Docker: `docker compose build scp-api` exit 0 → `up -d --force-recreate` exit 0 → `/health` **200** → `/readiness` **200** `{"status":"ready","checks":{"judge":"ok","background_scheduler":"ok"}}` → logs evidence 5 registry jobs (Fix 1) + ConfigContract (Fix 2) + RetryPolicy wiring (Fix 3) + Judge ready 27 SLMs + Background scheduler started.
4. Smoke `/ask` ngay sau recreate: **401** (auth dependency trước gate; judge ready <20s nên 503 window khép trước khi curl được — 503 được chứng minh bằng test in-process với config thật, xem Fix 4).

## Limitations / open items (cho orchestrator/owner)

1. **503 window trên Docker không bắt được từ bên ngoài** không có JWT hợp lệ (không được mint từ secret thật). Nếu cần evidence HTTP 503 thật: mint token từ SCP_ADMIN_KEY rồi curl trong 20s đầu sau recreate.
2. **Kernel DB path split (pre-existing, ngoài scope):** trong compose, adapter `/ask` dùng `/app/data/ask_task_kernel.sqlite3` (vì `SCP_KERNEL_DB_PATH` không set) và doubt-cron/retry dùng `SCP_DATA_DIR=/var/lib/scp/data`. Compose hiện mount CÙNG named volume `scp-data` ở CẢ HAI path nên hai đường dẫn quy về cùng một DB — nhưng nếu volume mount đổi, cần set `SCP_KERNEL_DB_PATH` để nhất quán. Retry wiring của tôi đã ưu tiên `SCP_KERNEL_DB_PATH` sẵn.
3. **wiremixin.py không sửa** — không có secret value (đã scan); nếu Mimosa flag lại, finding cần được re-check với đúng file chứa giá trị (data_sources nằm ngoài scope file list).
4. **DoubtCron fitness_drift FAIL trong Docker (pre-existing):** `/app/tests/golden/golden_dataset.json` không có trong image → check báo `ok: false` lúc boot. Không thuộc Mạch 1 file list; cần owner quyết (COPY tests/golden vào image hoặc cấu hình path).
5. Compose build KHÔNG tự truyền `SCP_GIT_SHA` → image `scp-api:local` hiện có ENV `SCP_GIT_SHA=unknown` baked; cơ chế sẵn sàng, orchestrator truyền `--build-arg SCP_GIT_SHA=$(git rev-parse HEAD)` khi build release (đã verify riêng với scp-api:sha-verify).
6. Docker build warning `SecretsUsedInArgOrEnv` cho `ENV OPENROUTER_API_KEY=""` là pre-existing (dòng 26, giá trị rỗng, trước cả lần sửa này).

## Container state khi kết thúc

`scp-scp-api-1` **Up**, `/health` 200, `/readiness` 200 (judge ok, scheduler ok). KHÔNG commit — mọi thay đổi nằm trong working tree.
