# C3 — Sandbox Evaluator: autofix không tự chấm bài (Track C3, ADOPT-AND-FIX)

- Agent: C3 (Track C3 — container hoá Sandbox Evaluator theo V2 P4)
- Nhánh: `audit/runtime-guard-AUDIT-20260909`
- Base commit: `e6acb56` (docs(C2): pin event bus closure record)
- Ngày: 2026-09-12
- Plan: `reports/expert-panel/ADOPT-AND-FIX-PLAN.md` Track C3 — "Sandbox Evaluator
  chạy pytest thật, autofix không tự chấm bài"
- Scope files (đủ 9, không more/less): `scp/sandbox_evaluator/*` (4 file mới),
  `scp/autofix/deterministic_worker.py`, `scp/autofix/engine.py`,
  `compose.yml`, `Dockerfile.sandbox-evaluator` (mới),
  `tests/T04_kernel/test_sandbox_evaluator_e2e.py` (mới).
  KHÔNG đụng GA.md, circuit-closures, dashboard, mini-services, TaskKernel,
  capability, verifier, T00-T11.

## Skill binding (SHA256)

| Skill | SHA256 |
|---|---|
| `.agents/skills/scp-dna/SKILL.md` | `4aada0be4873598dc50c3a7f38d90151429bb5263c511a838ed1cdcb4d594d10` |
| `.agents/skills/scp-learning-loop-guard/SKILL.md` | `63f651da13f0ff583c4906222ac08ab4a2403280ab90c66450a01d335da7ffef` |
| `.agents/skills/scp-reality-verifier/SKILL.md` | `a9d65ce53b18f8310ceeb302b18b341a0e1b8b19cddc7f46d4fa6ee99432269e` |

## 1. Thiết kế module

`scp/sandbox_evaluator/` (4 file):

- `evaluator.py` — lõi: `evaluate(patch_target: dict) -> EvalResult`.
  - Chạy `subprocess.run([sys.executable, "-m", "pytest", <target-tests>, "-x", "-q", "-p", "no:cacheprovider"], cwd=<workspace tạm>, shell=False, timeout=bounded, capture_output=True)`.
  - Workspace: `tempfile.mkdtemp(prefix="scp_sandbox_eval_")` trong SYSTEM TEMP —
    KHÔNG chạy trên repo sống. File đích (nội dung đã vá) + test files được copy
    vào; `conftest.py` tối tiểu chèn workspace root vào sys.path (import
    root-level + package-style qua namespace packages đều chạy).
  - **Fail-closed (DNA #22)**: PASS chỉ khi pytest chạy thật và `returncode == 0`.
    Timeout -> `FAIL(reason=timeout)`; setup lỗi -> `FAIL(setup:...)`;
    pytest exit 5 (no tests collected) -> FAIL ("no tests ran" is not PASS);
    không cung cấp test -> `FAIL(setup:no_tests)`; pytest không được spawn ->
    `returncode=None`.
  - Security: `shell=False`; timeout clamp [5, 900]s (env
    `SCP_SANDBOX_EVALUATOR_TIMEOUT_S`, default 120); env allowlist tối thiểu
    (PATH/SYSTEMROOT/TEMP/... — không kế thừa secret); traversal guard 2 lớp
    (`_safe_relpath` + `_contained_path` dùng `Path.resolve()` +
    `Path.is_relative_to()` tại mỗi write boundary).
- `events.py` — payload builder cho event bus (một channel `scp_eval`, payload
  phân biệt qua `type`): `EVAL_REQUEST` TỰ-ĐỦ (files + test content nhúng ->
  replay sau downtime an toàn; publish guard 5MB), `EVAL_RESULT` (raw
  stdout/stderr truncated 32k có đánh dấu).
- `loop.py` — evaluator service: consume `EVAL_REQUEST` qua `PgEventBus`
  (bảng durable `scp_events` + NOTIFY chỉ là chuông — Track C2),
  `start_at="beginning"` (service chết -> replay hết event chưa delivered),
  handler idempotent (evaluate thuần túy), payload malformed -> dead-letter
  guard. Fail-closed khởi động: không bus / thiếu DSN -> exit 2 (không idle nửa vời).
- `__init__.py` — exports.

## 2. Wire seams (opt-in, env-off giữ nguyên behavior)

| Seam | Env off (default) | Env `SCP_SANDBOX_EVALUATOR=1` |
|---|---|---|
| `deterministic_worker.process_job` | `require_tests=1` -> reject "no bounded targeted-test command" (như cũ) | payload có `test_paths` (qua `enqueue_bug(bug, test_paths=[...])`) -> chạy sandbox pytest THẬT trên bản sao `candidate.source_after`; FAIL -> reject TRƯỚC khi write (file không đổi — có test chứng minh); PASS -> apply với `reality_test_result="pass:sandbox"` + evidence trong result + audit `extra.sandbox_eval` |
| `engine._auto_approve_tier3` | ast.parse static gate (như cũ, từng byte) | ast.parse giữ làm pre-gate rẻ; GATE trở thành sandbox pytest qua env `SCP_SANDBOX_EVALUATOR_TESTS` (danh sách path, `,`/`;`); không cấu hình test -> `FAIL:sandbox:no_tests_configured` -> R6 rollback gate (fail-closed: bật opt-in mà không có test KHÔNG được tự chấm static PASS) |
| Event publish-side | không publish | `SCP_EVENT_BUS_ENABLED=1` -> worker publish `EVAL_REQUEST` (trước) + `EVAL_RESULT` (sau) lên `scp_eval` — best-effort loud: publish lỗi KHÔNG bao giờ đổi gate verdict (side-channel) |

## 3. Compose service

- `compose.yml` thêm service `sandbox-evaluator` (profile `sandbox`):
  `image scp-sandbox-evaluator:local`, command `python -m
  scp.sandbox_evaluator.loop`, read_only + cap_drop ALL + no-new-privileges +
  tmpfs /tmp (workspace pytest), volume scp-data.
- `Dockerfile.sandbox-evaluator`: base `scp-api:local` (tái dùng theo task) +
  `pip install pytest==9.1.1` (pin theo requirements-dev) + USER 10001.
  LÝ DO không dùng thẳng scp-api:local: image API cố tình KHÔNG chứa test
  runner (least capability) — evaluator là thành phần duy nhất cần pytest,
  nên pytest layer ở image riêng; API image giữ nguyên.
- Yêu cầu vận hành: `SCP_EVENT_BUS_DSN` trỏ tới PG có schema scp_events
  (thiếu -> service exit 2, fail-closed). Hint docker postgres:16-alpine:55432
  đã ghi trong compose.yml comment.

## 4. Commit per-milestone

| Commit | Nội dung |
|---|---|
| `3056d97` | feat(C3): SandboxEvaluator module (evaluate fail-closed) |
| `458df11` | feat(C3): wire opt-in vào deterministic_worker + engine |
| `85d106a` | feat(C3): event seam + loop service + compose service |
| `cca90ca` | test(C3): E2E suite 19 case NO-MOCK |
| `719f000` | fix(C3): rename engine alias `_run_sandbox_eval` -> `_sandbox_evaluation` (clear T03-S3 static sweep — substring `eval(`) |
| `72b7d53` | fix(C3): boundary containment check cho mọi workspace write (clear 3 Mimosa HIGH path-traversal) |

## 5. Reality evidence

### 5.1 E2E suite `tests/T04_kernel/test_sandbox_evaluator_e2e.py` (NO-MOCK, pytest thật)

4 case bắt buộc + mở rộng — `18 passed, 1 skipped (PG-gated declared
infra-skip)`; PG-gated case `test_event_bus_eval_roundtrip_real_pg`:
**PASSED** trên PostgreSQL thật (postgres:16-alpine, port 55432, schema
per-test `scp_c3_<hex>`). Chạy lại sau hardening: `18 passed, 1 skipped`.

| Case | Kết quả |
|---|---|
| 1. pass (file + test pass) | PASS, returncode 0, stdout "1 passed", command là argv list (shell=False) |
| 2. fail (sửa file) | FAIL `test_failed` rc=1, raw output chứa assertion + FAILED |
| 3. timeout (sleep + timeout=2) | FAIL `timeout`, subprocess bị kill, returncode None, elapsed bounded |
| 4. test file không tồn tại | FAIL `setup:test_path_missing`, returncode None — KHÔNG PASS khi không chạy được |
| 5. không có test | FAIL `setup:no_tests` |
| 6. pytest exit 5 (no tests collected) | FAIL `no_tests_collected` |
| 7. secret env không kế thừa | subprocess env allowlist — secret probe không xuất hiện trong env/output |
| 8. workspace ngoài repo | workspace trong system temp, không nằm trong repo |
| 9. worker gate E2E | env-off reject legacy / env-on PASS -> applied `pass:sandbox` / env-on FAIL -> rejected + file untouched / env-on thiếu test -> fail-closed |
| 10. engine tier3 E2E | sandbox FAIL -> rollback khôi phục file; PASS -> commit; env-on thiếu test -> `FAIL:sandbox:no_tests_configured`; env-off -> byte-identical legacy (không có sandbox_eval trong result) |
| 11. event payload guards | self-contained; unreadable test path -> không publish; oversized (5MB) -> không publish; EVAL_RESULT truncate 32k có đánh dấu |
| 12. event bus roundtrip (PG thật) | publish EVAL_REQUEST -> durable -> replay -> handler evaluate (pytest thật PASS) -> EVAL_RESULT collected |

Lưu ý harness: case 9-10 dùng monkeypatch cho ENV và `patch.object(engine,
"_auto_fix")` (cùng pattern harness T07 sẵn có) — subprocess pytest bên trong
evaluator là THẬT 100%.

### 5.2 Event path smoke trên PG thật (M3)

publish `EVAL_REQUEST` (self-contained) -> durable row -> replay ->
handler chạy evaluate thật (PASS "1 passed") -> `EVAL_RESULT` nhận về;
loop service fail-closed exits: không env -> exit 2; enabled thiếu DSN -> exit 2.

### 5.3 Regression T03 + T07

Lệnh: `python -m pytest tests/T03_capability tests/T03_integrity tests/T07_learning -q`

- **730-731 passed**, 2 failed — cả 2 là **pre-existing tại base `e6acb56`**
  (đã chạy lại tại base bằng worktree, cùng 2 test FAIL khi chạy isolated:
  `test_verify_fix_pytest_gate_fail_closed_on_exception`,
  `test_verify_fix_pytest_gate_fail_closed_on_regression` — mock
  `subprocess.run` + assert "fail-closed" trong reason; không liên quan C3).
- 1 flaky order-dependent: `test_autofix_end_to_end_rollback_on_verify_failure`
  (assert `len(rb_txs) >= 1` — shadow rolled_back rỗng khi T03_capability chạy
  trước; mechanism: shadow snapshot singleton `get_shadow_snapshot_manager` +
  `AutoFixEngine()` default data_dir trong T03). Ma trận 4 lần chạy combined:
  FAIL, FAIL, PASS (tree C3), PASS (swap engine/worker về base) — flake độc lập
  với C3: code path C3 trong suite này KHÔNG chạy được (SCP_SANDBOX_EVALUATOR
  chắc chắn off — các assertion env-off của T07 luôn PASS). Đề xuất track khác
  root-cause singleton pollution (ngoài scope C3).
- T03-S3 static sweep (`test_no_dangerous_idiom_literals_in_autofix_source`):
  bị C3 làm fail do alias `_run_sandbox_eval(` chứa substring `eval(` — đã sửa
  TẠI ĐIỂM LỖI (rename, không hạ chuẩn sweep), PASS lại (`719f000`).

### 5.4 Mimosa normal scan

| Scan | Kết quả |
|---|---|
| Scan trước phiên (09-11 22:48, cùng project) | 97 LOW + 15 MEDIUM, **HIGH=0** — nhưng `completeness: partial, runStatus: inconclusive` (phân tích chưa sâu) |
| Scan C3 lần 1 (12:23, `scan-2026-09-12T12-23-30.262Z-12fc7291b820`, seal `sha256:21cb...7850f`) | 98 LOW + 15 MEDIUM + **7 HIGH**: 3 path-traversal @ `scp/sandbox_evaluator/evaluator.py` (C3) + 4 tại file C1/C2 |
| Scan C3 lần 2 (12:31, `scan-2026-09-12T12-31-10.583Z-fa656aaf522c`, seal `sha256:5b88...aa5122`) | 98 LOW + 15 MEDIUM + **4 HIGH** — **HIGH=0 cho toàn bộ file C3** |

4 HIGH còn lại — pre-existing, thuộc file C1/C2 mà C3 KHÔNG đụng
(`git diff e6acb56..HEAD` trên 2 file = 0 change):
- `scp/event_bus_pg.py:276` — `sql.SQL("LISTEN {}").format(sql.Identifier(channel))`:
  safe-by-construction (psycopg identifier composition, C2 đã documented
  "100% parameterized DML") — FP của heuristic f-string/concat.
- `scripts/migrate_kernel_sqlite_to_pg.py:209` — `pg_sql.SQL("DELETE FROM
  {}").format(pg_sql.Identifier("control"))` — safe-by-construction (FP).
- `scripts/migrate_kernel_sqlite_to_pg.py:81,135` — f-string SQL
  (`PRAGMA table_info("{table}")`, `SELECT COUNT(*) FROM "{table}"`) với
  `table` đến từ hằng số nội bộ (`COPY_ORDER`), không phải external input —
  đề xuất C1 harden (whitelist check) trong track của mình.

## 6. Known gaps (không mở rộng thành claim)

1. **Subscribe-loop chưa wire vào worker loop**: worker publish-side
   `EVAL_REQUEST`/`EVAL_RESULT` (best-effort loud, side-channel); worker
   KHÔNG subscribe `EVAL_RESULT` — verdict gate là lần evaluate() in-process
   ("evaluator consume trực tiếp" theo phương án dự phòng của task). External
   evaluator service là độc lập (cross-lineage), không ai chờ ai.
2. **Evaluate() là single-process sandbox** (temp workspace trong system
   temp, container isolation ở tầng compose: read_only/cap_drop/no-new-
   privileges) — KHÔNG phải namespace/cgroup sandbox per-run; subprocess pytest
   chạy với env allowlist nhưng vẫn full filesystem read permission của user.
   Ranh giới đặt tên rõ: đây là "isolated workspace evaluator", không phải
   "hard sandbox".
3. **Timeout enforcement** theo semantics của `subprocess.run` (kill direct
   child; grandchild process nếu pytest tự spawn có thể sống sót trên POSIX —
   documented platform caveat).
4. **Flaky T07 end_to_end** (pre-existing) + 4 Mimosa HIGH C1/C2 — nêu ở 5.3/5.4,
   chờ track sở hữu xử lý.
5. Scan Mimosa có độ sâu thay đổi giữa các run (`completeness: partial` ở cả
   2 scan) — HIGH=0 cho file C3 được xác nhận trên scan sâu hơn của scan trước,
   nhưng không kết luận tuyệt đối ("no error found in current scope").

## 7. Final verdict

`PASS_WITHIN_SCOPE` — SandboxEvaluator chạy pytest THẬT trên bản sao workspace,
fail-closed đúng DNA #22, wire opt-in không đổi behavior default, compose
service + event seam hoạt động trên PG thật, E2E 18/18 (+1 PG-gated PASS),
Mimosa HIGH=0 cho file C3. Không claim production-ready; các known gaps ở §6
cần xử lý ở session sau (ưu tiên: subscribe-loop, C1/C2 Mimosa HIGH, T07 flake).
