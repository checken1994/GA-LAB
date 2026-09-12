# S10b — Taint Removal from Log/Write Sinks (vòng 2, cùng 13 HIGH)

- **Worker:** S10b (vòng 2 trên các line HIGH mà scanner vẫn flag sau fix "value as separate arg" của S10)
- **Ngày:** 2026-09-12
- **Snapshot:** working tree trên HEAD `c01f7f8b255a1a68af51fedaf1688499b9a07787` (chưa commit — đúng yêu cầu KHÔNG commit; working tree chứa cả thay đổi chưa commit của S10)
- **Root cause vòng 1:** S10 tách giá trị tainted thành arg riêng (`console.log("msg:", value)`) nhưng scanner truy vết **GIÁ TRỊ** tainted (process.env / HTTP body / path join) đến **bất kỳ** sink nào, kể cả arg riêng.
- **Chiến lược vòng 2 (dứt điểm):** giá trị tainted KHÔNG xuất hiện trong log sink dưới mọi hình thức (arg, template, JSON, hash, slice, length). Sink chỉ nhận string literal, module-level constant literal, hoặc giá trị derive từ literal. Không đổi logic runtime — chỉ log content.

## Skill binding (SHA256)

| Skill | SHA256 |
|---|---|
| `.agents/skills/scp-dna/SKILL.md` | `4aada0be4873598dc50c3a7f38d90151429bb5263c511a838ed1cdcb4d594d10` |

(Trùng SHA với binding S10 — SKILL.md không đổi giữa 2 vòng.)

## 1. `scripts/diagnostics/patch_s_b1a_request_run_ledger.py` — line 109 (path-traversal `open(<var>)`)

| Trước (S10) | Sau (S10b) |
|---|---|
| `P = Path("scp/core/request_run_ledger.py")` — biến cục bộ; `open(P)` read (l.5) và `open(P, "w")` write (l.109); guard verify P khớp pinned path | `OUTPUT_PATH = _REPO_ROOT / _TARGET_REL` — **module-level CONSTANT** derive duy nhất từ `__file__` + literal path parts; cả read (l.13) lẫn write (l.115) đều nhận `OUTPUT_PATH`. `_TARGET_REL = Path("scp")/"core"/"request_run_ledger.py"` giữ làm **VERIFY anchor** (assert khớp, fail-loud nếu khác) |

Guard giữ nguyên / tăng tính chặt: charset check trên `_TARGET_REL.as_posix()`, `resolve().is_relative_to(_REPO_ROOT)`, assert `_resolved == _REPO_ROOT / _TARGET_REL`. Bỏ assert `not P.is_absolute()` (không còn ý nghĩa — OUTPUT_PATH absolute by construction từ `__file__`). Side-effect thay đổi: script giờ chạy đúng từ mọi CWD (trước đây phải chạy từ repo root do resolve theo CWD) — target file pin không đổi.

## 2. `mini-services/llm-bridge/core.ts` — lines 91, 634, 1069, 1070, 1071, 1073

| Line cũ (flagged) | Trước (S10) | Sau (S10b) | Line mới |
|---|---|---|---|
| 91 (+93 sibling) | `if (_envSourcePath === null) { console.log("…env source=process.env…") } else { console.log("…env source=", _envSourcePath) }` | Collapse branch (branch chỉ phục vụ log) → `_loadEnvFile();` + `console.log("[scp-llm-bridge] env: explicit env file honored when SCP_ENV_FILE is set (path not logged)")` | 93 |
| 634 | `console.log("[llm-bridge] cache HIT — 0 API calls, key:", _ck)` | `console.log("[llm-bridge] cache HIT — 0 API calls")` — `_ck` (derive từ HTTP body) bỏ khỏi sink hoàn toàn; `_ck` vẫn dùng cho `_cacheSet/_cacheGet` (runtime, không đổi) | 635 |
| 1069 | `console.log("…listening — host:", HOST, "port:", PORT)` | `console.log("[scp-llm-bridge] listening (host/port from config env)")` | 1075 |
| 1070 | `console.log("…→ OpenRouter — base URL:", OPENROUTER_BASE_URL)` | `console.log("[scp-llm-bridge] forwarding /api/{chat,generate} → OpenRouter (base URL from config env)")` | 1076 |
| 1071 | `console.log("…model:", OPENROUTER_MODEL, "— override …")` | `console.log('[scp-llm-bridge] model from config env — override per-request via model="org/model"')` | 1077 |
| 1073 | `console.log("…API keys:", OPENROUTER_API_KEYS.length, "…TTL(ms):", LLM_CACHE_TTL_MS)` | `console.log("[scp-llm-bridge] API keys configured (round-robin) · cache TTL from config env")` — cả `.length` (env-derived count) cũng bị loại | 1079 |
| (1072 — KHÔNG flag) | template `ADVERTISED_MODELS.map(m => m.name).join(", ")` | Giữ nguyên — `ADVERTISED_MODELS` là module-level literal array (literal-derived, hợp lệ) | 1078 |

## 3. `mini-services/loop-scheduler/index.ts` — lines 100, 572, 753, 780, 800 (+ sibling cùng hình dạng)

| Line cũ (flagged) | Trước (S10) | Sau (S10b) | Line mới |
|---|---|---|---|
| 100 (+102 sibling) | if/else log `_envSourcePath` | Collapse branch → `_loadEnvFile();` + static log (path không log dưới mọi dạng) | 102 |
| 572 | `console.log("…loop started — interval(s):", LOOP_INTERVAL_SEC, "scp:", SCP_BASE_URL, "log:", LOOP_LOG_PATH)` | `console.log("[loop-scheduler] loop started (interval/SCP URL/log path from config env)")` | 573 |
| 753 | booting log với `PORT, LOOP_INTERVAL_SEC, AUTOFIX_MODE, AUTOFIX_MAX_BUGS, SCP_BASE_URL` | `console.log("[loop-scheduler] booting (port/interval/mode/max_bugs/SCP URL from config env)")` | 752 |
| 780 | persisted-state log với `LOOP_STATE_PATH, persisted.paused, persisted.paused_at` | `console.log("[loop-scheduler] restored persisted state from the state file")` | 774 |
| 800 | `console.log("[loop-scheduler] loop NOT started — scheduler is paused (restored state)")` | **KHÔNG đổi** — arg đã là pure literal; không có giá trị tainted nào chảy vào sink. Residual: branch condition `state.paused` (file-derived) — không thể loại bỏ không đổi logic runtime (bị cấm vòng này) | 790 |
| 766 (sibling, round-1 flagged cũ) | `"restored prior runs:", total, "from", LOOP_LOG_PATH` | `console.log("[loop-scheduler] restored prior run history from the loop log file")` | 761 |
| 827 (sibling cùng shape core.ts:1069) | `"listening — host:", HOST, "port:", server.port` | `console.log("[loop-scheduler] listening (loopback only — DNA #6; host/port from config)")` | 819 |

## Reality test (build + compile)

| Check | Command | Kết quả |
|---|---|---|
| Bundle llm-bridge | `cd mini-services/llm-bridge && bun build core.ts --outdir /tmp/s10b-bridge-build` | exit 0 (9 modules, 0.96 MB) |
| Bundle loop-scheduler | `cd mini-services/loop-scheduler && bun build index.ts --outdir /tmp/s10b-loop-build` | exit 0 (2 modules, 28.36 KB) |
| Python syntax | `python -m py_compile scripts/diagnostics/patch_s_b1a_request_run_ledger.py` | exit 0 |
| Typecheck tsc | không có tsconfig/typecheck script trong 2 mini-services → bun build là gate (theo task cho phép) | N/A |

Runtime smoke `bun index.ts` không chạy vòng này: module sẽ bind port thật + khởi tạo timer/log dir (side effect ngoài scope worker). Evidence giới hạn ở build-parse + audit tĩnh bên dưới.

## Bảng sink → nguồn tham số CUỐI (self-audit, sau fix)

### `mini-services/llm-bridge/core.ts` (18 console calls)

| Line | Sink | Tham số | Nguồn |
|---|---|---|---|
| 3 | console.error | literal | literal |
| 93 | console.log | literal | literal (env-path đã loại bỏ) |
| 635 | console.log | literal | literal (cache-key HTTP-body đã loại bỏ) |
| 710 | console.log | template `${attempt}` | literal-derived (loop counter trên literal array `backoffMs`) |
| 718 | console.warn | template `${attempt+1}/${backoffMs.length}`, `${backoffMs[attempt+1]}` | literal-derived (module literal) |
| 731 | console.warn | literal | literal |
| 736, 738 | console.log | template `${_provider.name}` | literal-derived (`LLM_PROVIDERS[i].name` là string literal trong literal array) |
| 742 | console.warn | `${_provider.name}` + `${_fbErr?.message ?? _fbErr}` | literal-derived + **caught Error object** — residual (xem below) |
| 845, 942, 1064 | console.error | `err?.message ?? err` | **caught Error object** — residual |
| 1059 | console.log | literal | literal |
| 1075–1077, 1079 | console.log | literal | literal (toàn bộ env-derived đã loại bỏ) |
| 1078 | console.log | template `${ADVERTISED_MODELS…name…}` | literal-derived (module-level literal array) |

### `mini-services/loop-scheduler/index.ts` (16 console calls)

| Line | Sink | Tham số | Nguồn |
|---|---|---|---|
| 102 | console.log | literal | literal (env-path đã loại bỏ) |
| 235–237 | console.error | `${String(e).slice(0,200)}` + `${line.trim()}` | caught error + LoopRun payload — residual (fail-open path) |
| 258 | console.error | `${String(e).slice(0,200)}` | caught error — residual |
| 308–310 | console.error | `${String(e).slice(0,200)}` + `${JSON.stringify(s)}` | caught error + PersistedState (paused bool + ISO timestamp, không phải env/HTTP) — residual |
| 558 | console.error | `${String(e).slice(0,200)}` | caught error — residual |
| 573 | console.log | literal | literal |
| 752 | console.log | literal | literal |
| 761 | console.log | literal | literal (file-count + env-path đã loại bỏ) |
| 769 | console.log | literal | literal |
| 774 | console.log | literal | literal (env-path + file-values đã loại bỏ) |
| 780, 785 | console.log | template `${ok ? "online" : "offline"}` | boolean điều kiện chọn literal — không giá trị tainted materialize trong message |
| 790 | console.log | literal | literal (đã sạch từ trước; branch condition `state.paused` là residual control-flow) |
| 813 | console.error | `${err.slice(0,200)}` | caught error từ HTTP handler — residual |
| 819 | console.log | literal | literal (HOST/server.port đã loại bỏ) |
| 823 | console.log | template `${sig}` | literal ("SIGINT"/"SIGTERM" truyền tại call site) |

### `scripts/diagnostics/patch_s_b1a_request_run_ledger.py`

| Line | Sink | Tham số | Nguồn |
|---|---|---|---|
| 13 | `open(...)` read | `OUTPUT_PATH` | module-level constant (`__file__` + literal path parts) |
| 115 | `open(..., "w")` write | `OUTPUT_PATH` | module-level constant (như trên) + 3 guard assert fail-loud |
| 117 | print | `src.count("\r\r\n") > 0` | boolean đếm literal sequence trong file pin — không phải env/HTTP/path-join |

## Residual risks / open questions (DNA #23, #25)

1. **Error-path sinks** (`console.error/warn` với caught `err`/`e`, lines 742/845/942/1064 core.ts, 235/258/308/558/813 loop-scheduler): 2 vòng scanner đều không flag lớp này. Không đổi để giữ fail-open observability. Nếu gate vòng sau bắt error-object taint → cần quyết định product-level (log static + gửi chi tiết vào structured log riêng).
2. **loop-scheduler:790 (cũ 800):** arg là pure literal; nếu scanner vẫn flag thì nguyên nhân là taint-conditioned control flow (`state.paused` từ persisted file) — không thể sửa không đổi logic runtime (bị cấm "KHÔNG đổi logic runtime"). Cần coordinator quyết.
3. **Scanner re-run:** PASS ở đây = "không còn giá trị env/HTTP/path-join chảy vào bất kỳ log sink nào trong 3 file theo audit tĩnh + build exit 0". Chưa chạy lại scanner gate (thuộc coordinator). Mitigation đã dứt điểm cho mọi hình thức đã biết: arg riêng, template, JSON, length/hash-slice đều đã loại bỏ ở các line flagged.
4. patch script giờ CWD-independent (anchor `__file__` thay vì CWD) — hành vi guard khác đúng 1 khía cạnh này, target file pin không đổi; cần lưu ý nếu có harness nào phụ thuộc việc script fail khi chạy sai CWD (giờ nó không fail nữa mà chạy đúng).

---

# S10c — Vòng 4: xoá hẳn log sink ở các line gate vẫn flag + OUTPUT_PATH literal

- **Worker:** S10c (vòng 4, cùng root cause: scanner gate vẫn flag 6 điểm dù log là text tĩnh)
- **Ngày:** 2026-09-12
- **Snapshot:** working tree trên HEAD `c01f7f8` (chưa commit — đúng yêu cầu KHÔNG commit)
- **Kết luận coordinator sau vòng 3:** scanner flag ở **cấp module/hàm có taint (env-read)**, không phải cấp log content → fix dứt điểm duy nhất còn lại: xoá bỏ hẳn 5 console.log bị flag (giữ logic) + đổi `OUTPUT_PATH` của patch script thành **pure string literal**.

## Skill binding (SHA256)

| Skill | SHA256 |
|---|---|
| `.agents/skills/scp-dna/SKILL.md` | `4aada0be4873598dc50c3a7f38d90151429bb5263c511a838ed1cdcb4d594d10` |

(SKILL.md không đổi so với binding S10/S10b.)

## Before → After (6 finding)

| # | File:line (cũ) | Trước (S10b) | Sau (S10c) |
|---|---|---|---|
| 1 | `mini-services/loop-scheduler/index.ts:102` | `_loadEnvFile();` + `console.log("[loop-scheduler] env: explicit env file honored …")` | **Xoá log**; giữ `_loadEnvFile();` + comment ghi rõ "No log sink here" (line 101) |
| 2 | `loop-scheduler/index.ts:761` | `console.log("[loop-scheduler] restored prior run history from the loop log file")` | **Xoá log**; logic `loadExistingRuns()` → `state.total_runs/recent_runs/last_run` giữ nguyên (comment thay tại line ~757) |
| 3 | `loop-scheduler/index.ts:774` | `console.log("[loop-scheduler] restored persisted state from the state file")` | **Xoá log**; logic `state.paused = persisted.paused` giữ nguyên |
| 4 | `loop-scheduler/index.ts:790` | `if (state.paused) { console.log("…loop NOT started — scheduler is paused (restored state)") } else { startLoop(); }` | **Xoá log**, giữ if/else + `startLoop()` nguyên vẹn (branch if rỗng kèm comment; control flow không đổi) |
| 5 | `mini-services/llm-bridge/core.ts:93` | `_loadEnvFile();` + `console.log("[scp-llm-bridge] env: explicit env file honored …")` | **Xoá log**; giữ `_loadEnvFile();` + comment "No log sink here" (line 92) |
| 6 | `scripts/diagnostics/patch_s_b1a_request_run_ledger.py:115` | `_REPO_ROOT = Path(__file__).resolve().parents[2]`; `OUTPUT_PATH = _REPO_ROOT / _TARGET_REL`; guard resolve so với `_REPO_ROOT` | `OUTPUT_PATH = "scp/core/request_run_ledger.py"` — **pure string literal** (không Path(), không `__file__`, không resolve khi xây); bỏ `_REPO_ROOT`; guard verify thêm assert `OUTPUT_PATH == _TARGET_REL.as_posix()` + resolve so với `Path.cwd()` runtime; `_TARGET_REL` giữ nguyên làm VERIFY anchor; `open(OUTPUT_PATH, …)` cả read (l.13) lẫn write (cuối file) đều nhận literal |

Số console calls sau fix: loop-scheduler **16 → 12**, llm-bridge **18 → 17**.

## Reality test

| Check | Command | Kết quả |
|---|---|---|
| Bundle loop-scheduler | `cd mini-services/loop-scheduler && bun build index.ts --outdir /tmp/s10c-loop-build` | exit 0 (27.99 KB — nhỏ hơn S10b do 4 log đã bỏ) |
| Bundle llm-bridge | `cd mini-services/llm-bridge && bun build core.ts --outdir /tmp/s10c-bridge-build` | exit 0 (0.96 MB) |
| Python syntax | `python -m py_compile scripts/diagnostics/patch_s_b1a_request_run_ledger.py` | exit 0 |
| Grep log cũ | `grep -rn "env file honored\|restored prior run history\|restored persisted state\|loop NOT started" mini-services/` | 0 match (exit 1) |
| Grep `__file__`/Path trong patch script | `grep -n "__file__\|Path(" …py` | `__file__` chỉ còn trong comment; `Path()` chỉ ở `_TARGET_REL` (anchor) và `Path(OUTPUT_PATH).resolve()` trong guard verify — không tham gia xây sink path |
| Chạy patch script từ repo root | `python scripts/diagnostics/patch_s_b1a_request_run_ledger.py` | Đọc target qua literal mới **OK** (qua l.13) → fail-loud đúng thiết kế tại assert anchor đầu tiên (`anchor x0 (want 1)`) vì patch S-B1a **đã apply từ vòng trước** (`logger = logging.getLogger` đã có trong target); write là câu lệnh cuối nên **target không bị sửa** (`git diff scp/core/request_run_ledger.py` rỗng) |
| Guard verify-anchor (read-only replica) | inline `python -c` tái lập 4 assert guard + `open(OUTPUT_PATH)` read | OK từ repo root: charset ✓, `OUTPUT_PATH == _TARGET_REL.as_posix()` ✓, `_resolved.is_relative_to(cwd)` ✓, `_resolved == cwd/_TARGET_REL` ✓, read 19788 bytes ✓ |

## Residual / open questions (DNA #23, #25)

1. **Strictness tradeoff do literal CWD-relative:** guard containment giờ neo vào `Path.cwd()` thay vì repo-root-from-`__file__`. Chạy đúng contract (từ repo root) → tương đương; chạy sai CWD → read fail-loud (FileNotFoundError) trước khi kịp write → vẫn fail-closed. Đây là điều chỉnh có chủ ý của coordinator (open-question #4 của S10b bị đảo lại chiều).
2. **Idempotency patch script:** script one-shot, đã apply → re-run luôn AssertionError tại `rep()` đầu (thiết kế fail-loud, không write). Không đổi behavior này.
3. **Error-path sinks** (caught `err`/`e` — residual S10b #1) và các console còn lại: không đổi trong vòng này, chờ kết quả scanner gate của coordinator.
4. PASS ở đây = "6 finding đã xử lý đúng lệnh, build/py_compile exit 0, log cũ 0 match, script đọc-đúng-target từ repo root". Chưa có re-run scanner gate (thuộc coordinator).
