# Kiểm chứng tĩnh độc lập — Mạch 1 (Boot & Background)

- Verifier: subagent độc lập (không thuộc chuỗi viết/sửa code M1)
- Repo: `C:\Users\check\Downloads\scp`
- Branch thực tế: `audit/runtime-guard-AUDIT-20260909`
- HEAD thực tế: `6328d513f53daf2cba03bf2d56a0bb380735f609`
- Chế độ: READ-ONLY (chỉ `Get-Content`, `Select-String`, `git log/show/diff/status`). Không sửa file, không commit, không docker, không pytest.
- Báo cáo bị kiểm chứng: `reports/expert-panel/A-mach1-boot-fixes.md`

Lưu ý về số dòng: `Get-Content | Select-Object -Skip N` đếm 1-based trong báo cáo này (dòng in ra đã được gắn số thật của file).

---

## Bảng đối chiếu tuyên bố ↔ thực tế

| # | Tuyên bố (trích ngắn) | Thực tế quan sát (trích code thật + file:dòng) | Verdict | Ghi chú |
|---|---|---|---|---|
| F1-1 | `lifespan.py:355-368` gọi `_bg_registry.start_all()` ngay trước `yield`, bọc try/except **re-raise** | `lifespan.py:355-368`: comment `[MACH1-FIX-1]`; `360: try:` `361: from scp.api.background_jobs import registry as _bg_registry` `362: _bg_registry.start_all()` `364: except Exception as exc:` `367: raise` `368: yield` | ĐÚNG | Đúng logic & dải dòng. `raise` trần = re-raise, abort boot khi required job fail |
| F1-2 | `background_jobs.py:210-232` thêm `_get_kernel_or_none()`: (1) `scp.api._shared.get_kernel`, (2) reuse `scp.api_server._ASK_KERNEL_ADAPTERS[*].kernel` | `background_jobs.py:210-238`: `223: try: from scp.api._shared import get_kernel` `230: from scp import api_server` `232: for adapter in list(getattr(api_server, "_ASK_KERNEL_ADAPTERS", {}).values()):` `233: kernel = getattr(adapter, "kernel", None)` `238: return None` | ĐÚNG | Hàm thực tế kéo dài tới dòng **238** (báo cáo ghi 210-232); đúng thứ tự resolve đã mô tả |
| F1-3 | `background_jobs.py:249-252, 266-268` — 2 required job dùng resolver thay `from scp.api._shared import get_kernel` | `251: kernel = _get_kernel_or_none()` (job `kernel_lease_expiry`), `267: kernel = _get_kernel_or_none()` (job `kernel_orphan_reconcile`) | ĐÚNG | Cả 2 required job (`required=True` tại dòng 244, 261) dùng resolver |
| F1-4 | `background_jobs.py:60-71` log `"first execution completed"` khi job chạy lần đầu | `67: if not _first_execution_logged:` `70: logger.info("[BackgroundJob] %s: first execution completed", self.name)` `71: _first_execution_logged = True` | ĐÚNG | Cờ `_first_execution_logged` khởi tạo dòng 62, đặt sau khi `self.fn()` chạy thành công (dòng 65) |
| F1-5 | Chuỗi `"[MACH1-FIX-1]"` có thật | Có: `lifespan.py:355,363,366`; `background_jobs.py:68,213,249,266` | ĐÚNG | Marker tồn tại |
| F1-6 | Shutdown đã có `registry.stop_all()` (dòng ~385) | `lifespan.py:396-399`: `from scp.api.background_jobs import registry` → `399: registry.stop_all(timeout=10.0)` | ĐÚNG | Thực tế ở dòng **399**, không phải ~385 (báo cáo lệch nhẹ số dòng; logic có thật) |
| F1-7 | DNA #26: `scp.api._shared` KHÔNG có `get_kernel` | `scp/api/_shared.py:110-115 _DELEGATED_NAMES = frozenset({" _SCP_VERSION", ..., "_voice_detector"})` — **không chứa `get_kernel`** | ĐÚNG | Củng cố phát hiện "ngoài scope"; lý do watchdog cũ no-op |
| F1-8 | Registry có 5 job | `kernel_lease_expiry` (bg:241), `kernel_orphan_reconcile` (bg:258), `canary_token_cleanup` (bg:274), `deep_audit_scheduler` (lifespan:209), `attack_mode_monitor` (lifespan:264) = 5 | ĐÚNG | Cả 5 đăng ký TRƯỚC `start_all()` tại dòng 362 |
| F2-1 | `lifespan.py:49-55` `validate_boot_config()` là lệnh đầu tiên, NGOÀI try/except | `49-52`: comment `[MACH1-FIX-2]`; `53: from scp.core.config_contract import validate_boot_config` `54: validate_boot_config()` — nằm trực tiếp trong thân lifespan, KHÔNG bọc try | ĐÚNG | Không phải literal dòng đầu (46-48 là logger banner), nhưng là hành động logic đầu tiên; đúng fail-closed |
| F2-2 | Chuỗi `"[MACH1-FIX-2]"` | `lifespan.py:49` (comment) và `55` (log `Boot config contract validated (fail-closed)`) | ĐÚNG | Marker tồn tại |
| F3-1 | `retry_policy.py:71-96` thêm `run_background(interval_sec, stop_event)` | `71: def run_background(self, interval_sec: float = 60.0, stop_event: threading.Event | None = None)` — loop tới dòng 95, chờ `stop_event.wait(interval_sec)` (85) hoặc `time.sleep` (88) | ĐÚNG | Hàm thực tế 71-95 (báo cáo ghi 71-96, lệch 1 dòng) |
| F3-2 | `retry_policy.py:33-36` `observe()` chấp nhận `RETRY_SCHEDULED` | `33-35`: comment `[MACH1-FIX-3]`; `36: if state in ("WAITING_APPROVAL", "RETRY_SCHEDULED"):` | ĐÚNG | Đúng dòng |
| F3-3 | `retry_policy.py:60-63` `check_and_retry()` fallback `step_id=""` cho plan flat | `60-61`: comment; `62: step_id = str(step.get("stepId", "")) if step else ""` | ĐÚNG | Đúng dòng; không skip plan thiếu `steps` |
| F3-4 | `lifespan.py:294-352` `_get_waiting_plans` = SELECT thật trên TaskKernel DB (`SCP_KERNEL_DB_PATH` ưu tiên, fallback `SCP_DATA_DIR/ask_task_kernel.sqlite3`) | `304-307` path; `313 from scp.task_kernel import TaskKernel` `320-322: rows = _rk.conn.execute("SELECT task_id, state FROM tasks WHERE state='RETRY_SCHEDULED'").fetchall()` | ĐÚNG | Đúng dải 294-352; path ưu tiên env `SCP_KERNEL_DB_PATH` rồi fallback `SCP_DATA_DIR` |
| F3-5 | `_retry_plan` = `TaskKernel.transition(task_id,'QUEUED',actor='retry_policy', reason='retry_policy_background')` | `331: _rk.transition(task_id, 'QUEUED', actor='retry_policy', reason='retry_policy_background')` | ĐÚNG | Đúng dòng & tham số |
| F3-6 | Thread daemon có stop_event; poll interval env `SCP_RETRY_POLL_SEC` (default 60s) | `337: _retry_stop = threading.Event()` `342: 'interval_sec': float(os.environ.get('SCP_RETRY_POLL_SEC', '60'))` `343: 'stop_event': _retry_stop` `345: daemon=True` | ĐÚNG | Đúng dòng & giá trị mặc định 60s |
| F3-7 | "shutdown set qua `app.state.retry_policy_stop`, **lifespan.py:373**" | Gán `app.state.retry_policy_stop` ở dòng **338**; tiêu thụ (set event) ở vòng lặp shutdown dòng **385-387** (`getattr(app.state,'retry_policy_stop',None)`). Dòng 373 thực tế là `from scp.meta.external_trust import get_external_trust_root` | **SAI** | Số dòng `373` sai. Cơ chế (gán `app.state.retry_policy_stop` → set event khi shutdown) **có thật** tại 338 & 385-387 |
| F3-8 | Log `[RESTORED-SYSTEMS] RetryPolicy background thread started` | `350: logger.info('[RESTORED-SYSTEMS] RetryPolicy background thread started (real kernel wiring, db=%s)', _retry_db_path)` | ĐÚNG | Chuỗi tồn tại |
| F3-9 | "không có caller production khác của `check_and_retry` ngoài lifespan" | Chỉ 2 nơi gọi: `retry_policy.py:93` (trong `run_background`) và `retry_policy.py:105` (trong helper `start_retry_monitor`). `start_retry_monitor` **không được gọi ở đâu** (grep toàn repo chỉ thấy định nghĩa) | ĐÚNG | Không có đường production khác; thay đổi an toàn |
| F4-1 | `api_server.py:483-495` đầu route `/ask` có gate `judge_ready` False → `JSONResponse 503 {"detail":"judge_initializing","reason":...,"retry_after_seconds":5}` | `478-481` route + `Depends(get_current_user)`; `482` counter; `483-486` comment `[MACH1-FIX-4]`; `487: if not getattr(app.state, "judge_ready", False):` `488-495: JSONResponse(status_code=503, content={"detail":"judge_initializing","reason":...,"retry_after_seconds":5})`; `496` kernel gate sau đó | ĐÚNG | Đúng dải; gate nằm sau auth dependency và trước kernel gate |
| F5-1 | `scripts/run_scp_acceptance.py:261-265, 271-272` dùng `os.environ.get("OPENROUTER_API_KEY"/"OPENAI_API_KEY")` thay literal | `261-263` comment `[MACH1-FIX-5]`; `264: "OPENROUTER_API_KEY": os.environ.get("OPENROUTER_API_KEY", ""),`; `271-272: "OPENAI_API_KEY": os.environ.get("OPENAI_API_KEY", ""),` | ĐÚNG | Đúng dòng |
| F5-2 | `.env.example:69-84` block "External data-source credentials" 8 key giá trị RỖNG | Block thực tế **dòng 71-83**: header `# ── External data-source credentials ──` (71), comment `[MACH1-FIX-5]` (72-74), 8 key (75-82): `OPENROUTER_API_KEY=`, `OPENAI_API_KEY=`, `EIA_API_KEY=`, `USDA_API_KEY=`, `NVD_API_KEY=`, `CASE_LAW_API_KEY=`, `GOOGLE_FACT_CHECK_API_KEY=`, `NASA_API_KEY=`. Đo `valueLen=0` cho cả 8 key | ĐÚNG | Block đúng nội dung; dòng thực tế 71-83 (báo cáo ghi 69-84, lệch 2). Giá trị rỗng thật (đã đo độ dài, không phải che) |
| F5-3 | Scan residue `sk-[a-f0-9]{8,}` và `api_key\s*=\s*["'][a-zA-Z0-9]{10,}` → 0 match | `run_scp_acceptance.py`: pattern1 = **0**, pattern2 = **0**. `wiremixin.py`: pattern1 = **0**, pattern2 = **0** | ĐÚNG | Đã chạy lại cả 4 phép đo, đều 0 |
| F5-4 | `wiremixin.py:54-59` không chứa secret value; là dict map TÊN env → đường dẫn data_source | `53-60: api_to_datasource = { "EIA_API_KEY": "scp/data_sources/energy.py", "USDA_API_KEY": "scp/data_sources/agriculture.py", "NVD_API_KEY": "scp/data_sources/cybersecurity.py", "CASE_LAW_API_KEY": "scp/data_sources/legal.py", "GOOGLE_FACT_CHECK_API_KEY": "scp/data_sources/reality.py", "NASA_API_KEY": "scp/data_sources/astronomy.py", }` | ĐÚNG | Đúng: map tên→đường dẫn file, không có khóa nào |
| F6-1 | `Dockerfile:33-39` `ARG SCP_GIT_SHA=unknown` + `ENV SCP_GIT_SHA=${SCP_GIT_SHA}` | Comment `[MACH1-FIX-6]` ở **36-39**; `40: ARG SCP_GIT_SHA=unknown`; `41: ENV SCP_GIT_SHA=${SCP_GIT_SHA}` | ĐÚNG | Thực tế ARG/ENV ở dòng **40-41** (báo cáo ghi 33-39, lệch ~1; 33-34 là 2 ENV retry/kw khác) |
| F6-2 | `api_server.py:98-115` `_scp_service_identity` ưu tiên env `SCP_GIT_SHA` (bỏ qua "unknown") trước git subprocess | `98-100` comment `[MACH1-FIX-6]`; `101: _env_sha = os.environ.get("SCP_GIT_SHA", "").strip()`; `102: if _env_sha and _env_sha != "unknown":` `103: _commit = _env_sha`; `104-115: else: ... git rev-parse HEAD ... except: _commit = "unknown"` | ĐÚNG | Đúng: ưu tiên env, bỏ qua literal "unknown", fallback git subprocess |
| F7-1 | Test file có đúng 7 causal test với tên liệt kê | Có đủ & đúng tên: `test_causal_boot_config_missing_jwt_secret_raises` (391), `test_causal_lifespan_starts_required_registry_jobs` (399), `test_causal_ask_returns_503_while_judge_not_ready` (427), `test_causal_ask_invalid_token_returns_401` (443), `test_causal_retry_policy_run_background_requeues_kernel_task` (454), `test_causal_doubt_cron_escalation_backlog_real_sqlite` (511), `test_causal_registry_starts_and_stops_registered_job` (535) | ĐÚNG | 7/7 tên khớp chính xác |
| F7-2 | Không còn method test thân chỉ `pass` | `Select-String -Pattern '^\s+pass\s*$'` → **0 match**. Chỉ có `pass` duy nhất ở `553-554` ngoài class (`if __name__ == "__main__": pass`) | ĐÚNG | Không còn stub rỗng trong các test method |
| F7-3 | Un-mock `test_lifespan_initializes_otel_telemetry`: bỏ 4 lớp `patch` trên dead module `scp/api/_lifespan`, bỏ import dead module | `75-85`: chỉ còn `with TestClient(app) as client: response = client.get("/health"); assert response.status_code == 200`. Không còn `patch(...)`. `grep '_lifespan'` chỉ ra dòng 3 (docstring "Covers:") và 80-81 (comment giải thích) — **không có import/patch thật** | ĐÚNG | Đúng: không còn patch. Di tích nhỏ: docstring dòng 3 vẫn nhắc `api/_lifespan.py` (chỉ là văn bản, không phải code) |
| F7-4 | Module-level `os.environ.setdefault` cho `SCP_JWT_SECRET`/`SCP_ADMIN_KEY` | `35-38`: `os.environ.setdefault("SCP_JWT_SECRET", "test-only-jwt-secret-...")`; `38: os.environ.setdefault("SCP_ADMIN_KEY", "test-only-admin-key-...")` | ĐÚNG | Đúng dòng; dùng `setdefault` (không ghi đè env thật) |
| F7-5 | "Xoá 10 method causal rỗng (`pass`) — thay bằng 7 test THẬT" | `git cat-file -e fe4bc8d:tests/T01_boot/test_flow_01_boot_background_scp_standard.py` → **"exists on disk, but not in 'fe4bc8d'"**. File **không tồn tại ở commit cha**; `git show 6328d51 --stat` cho file này = **554 insertions, 0 deletions** (file mới, commit trọn) | KHÔNG RÕ | Không thể xác minh "xoá 10 stub" qua git vì file chưa từng được track trước đó (thay đổi xảy ra trong working tree rồi commit trọn). **Phần outcome thì ĐÚNG**: hiện tại 0 stub rỗng + đủ 7 causal test |
| F7-6 | Suite 25 test (18 cũ + 7 mới); 0 skip/xfail | `26` lệnh `def test_` tại HEAD; trong đó 1 là helper lồng (`133: def test_job()` trong `test_background_job_registry_register_and_run`) → **25 test method thật**. 25 − 7 causal = 18 test cũ | ĐÚNG | Khớp "18 cũ + 7 mới"; 7 causal body đều real (assert thật, có `TestClient(app)` / SQLite tmp / state machine thật) |

---

## Fix M1 nằm ở đâu trong git

**Kết luận: (a) ĐÃ COMMIT trong HEAD `6328d51`** — KHÔNG phải only working tree, và tất nhiên KHÔNG phải "không tồn tại".

Bằng chứng (lệnh + output thật):

1. HEAD hiện tại:
```
$ git -C C:\Users\check\Downloads\scp rev-parse HEAD
6328d513f53daf2cba03bf2d56a0bb380735f609

$ git -C C:\Users\check\Downloads\scp branch --show-current
audit/runtime-guard-AUDIT-20260909
```

2. `git log --oneline -15` (đoạn đầu):
```
6328d51 fix(M1): boot/background circuit completed
fe4bc8d audit: snapshot working tree for runtime guard audit (token-only fail-closed + test_api_token_boundary)
55eda44 docs: GA.md handoff B9 final — 620/620 PASS, T07 fix complete
...
```

3. `git show --stat 6328d51` — commit M1 động đúng các file Mạch 1 (988 insertions, 59 deletions):
```
 .env.example                                       |  18 +
 Dockerfile                                         |  14 +
 compose.yml                                        |  35 +-
 reports/expert-panel/A-mach1-boot-fixes.md         | 116 ++++
 scp/api/background_jobs.py                         |  77 ++-
 scp/api_server.py                                  |  58 ++-
 scp/api_server_parts/lifespan.py                   | 130 ++++-
 scp/policy/retry_policy.py                         |  37 +-
 scripts/run_scp_acceptance.py                      |   8 +-
 tests/T01_boot/test_flow_01_boot_background_...py  | 554 ++++++++++
 10 files changed, 988 insertions(+), 59 deletions(-)
```

4. Working tree **SẠCH** đối với mọi file M1 (không có thay đổi uncommitted):
```
$ git -C C:\Users\check\Downloads\scp status --short -- <các file M1...>
(trống)

$ git -C C:\Users\check\Downloads\scp diff --name-only HEAD -- <các file M1...>
(trống)
```
→ Toàn bộ 8 file M1 (`lifespan.py`, `background_jobs.py`, `retry_policy.py`, `api_server.py`, `run_scp_acceptance.py`, `.env.example`, `Dockerfile`, `tests/T01_boot/`) đều trùng khớp HEAD.

5. `git log --stat -3 -- scp/api_server_parts/lifespan.py scp/api/background_jobs.py scp/policy/retry_policy.py`:
```
6328d51 fix(M1): boot/background circuit completed
 scp/api/background_jobs.py       |  77 +++++++++++++++++------
 scp/api_server_parts/lifespan.py | 130 +++++++++++++++++++++++++++++++++------
 scp/policy/retry_policy.py       |  37 +++++++++--
 3 files changed, 204 insertions(+), 40 deletions(-)
```
Commit gần nhất đụng các file này chính là `6328d51` (commit M1).

**Diễn giải:** Báo cáo gốc ghi "Branch ... HEAD `fe4bc8d` (chưa commit — working tree)" — điều đó **đúng tại thời điểm viết báo cáo**. Sau đó thay đổi M1 đã được **commit vào `6328d51` "fix(M1): boot/background circuit completed"** (Author `zcode-agent`, Thu Sep 10 02:00:41 2026 +0700). Ngoài các file M1, working tree hiện còn nhiều thay đổi/untracked khác (Mạch 2, các test flow mới, .mimosa/...) — nhưng **không liên quan M1** và **không** nằm trong danh sách file M1 đã kiểm.

Lưu ý phụ: file `tests/T01_boot/test_flow_01_boot_background_scp_standard.py` **không tồn tại trong commit cha `fe4bc8d`** — nên đối với riêng file này, commit `6328d51` là lần **thêm mới toàn bộ** (554 insertions, 0 deletions), không phải sửa-đè file đã track.

---

## Kết luận tổng

- **ĐÚNG: 29** tuyên bố (bao gồm các tuyên bố lệch nhẹ số dòng nhưng logic/giá trị đúng — đã ghi rõ dòng thực tế ở cột "Ghi chú").
- **SAI: 1** — F3-7: số dòng `lifespan.py:373` cho `app.state.retry_policy_stop` là không chính xác (thực tế gán ở dòng 338, tiêu thụ ở 385-387); cơ chế đúng, chỉ số dòng sai.
- **KHÔNG RÕ: 1** — F7-5: "xoá 10 method causal rỗng" không kiểm chứng được qua git (file chưa từng track ở commit cha); tuy nhiên trạng thái cuối cùng (0 stub rỗng + 7 causal test thật) thì ĐÚNG.

Nhận xét trung tính về sai lệch: 3 vị trí ghi dòng hơi lệch so với thực tế (`lifespan.py` stop_all 399 vs ~385; `background_jobs.py` resolver 210-238 vs 210-232; `.env.example` block 71-83 vs 69-84; `Dockerfile` ARG/ENV 40-41 vs 33-39) — **không có case nào logic thiếu sót**, chỉ là sai số dòng trong báo cáo. Tất cả các fix chính (F1 registry/watchdog, F2 fail-closed boot gate, F3 retry policy thật, F4 503 gate, F5 credentials, F6 commit SHA, F7 test nâng chuẩn) đều **hiện diện thật trong cây làm việc = HEAD `6328d51`**.

Không phê bình cá nhân; toàn bộ kết luận là quan sát code/git thực tế. Không thực hiện bất kỳ ghi hay đột biến nào lên repo.
