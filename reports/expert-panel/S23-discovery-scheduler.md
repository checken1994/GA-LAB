# S23 — Free Discovery Scheduler (blueprint `free_discovery_scheduler.py`)

- Worker: S23 (no-commit). HEAD tại thời điểm bắt đầu: `b8fa536` (branch không đổi).
- Skills bắt buộc đã đọc: `scp-dna`, `scp-learning-loop-guard` (SHA256 ở cuối file).
- Ngày: 2026-09-13.

## 1. Problem statement (trước khi sửa)

`FreeAPICatalog.refresh(force)` đã chạy được runtime (egress mở, ~1,785 entries)
NHƯNG owner directive "tự động tìm và cập nhật hơn 1000 API" KHÔNG chạy vì:

1. Blueprint module `scp/core/free_discovery_scheduler.py` chưa từng tồn tại
   (đã verify `ls scp/core/` — không có file nào khớp `disc*`).
2. `search()/entries()` không lazy-refresh theo lịch; caller duy nhất của
   catalog là 2 route đọc trong `scp/api/routes/v104_routes.py`
   (`/v104/learn/top-systems/status`, `/v104/free-apis/search` — route search
   chỉ lazy-refresh khi catalog rỗng).
3. Không có event-hook refresh-on-404.

## 2. Xây gì (file changed)

| File | Loại | Nội dung |
|---|---|---|
| `scp/core/free_discovery_scheduler.py` | XÂY MỚI | `FreeDiscoveryScheduler` (async): tick đầu chạy NGAY khi boot, tick sau mỗi `interval` ± jitter 10%; mỗi tick refresh ĐỘC LẬP 2 nguồn qua `asyncio.to_thread` (blocking urllib/httpx KHÔNG chạy trong event loop); fail độc lập từng nguồn (raise → WARNING, nguồn kia vẫn chạy, loop không chết); kill-switch `SCP_DISCOVERY_SCHEDULER` (default on); interval `SCP_DISCOVERY_INTERVAL_SECONDS` (default 21600, parse lỗi / <=0 / NaN / Inf → default). |
| `scp/api_server_parts/lifespan.py` | SỬA (+28 dòng) | Boot: start scheduler sau background-job registry, lưu `app.state.discovery_scheduler`, log `[S23-DISCOVERY]`; mọi lỗi non-fatal. Shutdown: `await discovery_scheduler.stop(timeout=5)` (cancel + await, no leak) trước khi cancel các bootstrap task. |
| `tests/T07_learning/test_discovery_scheduler.py` | XÂY MỚI | 13 test hermetic phủ (a)–(f) của thiết kế chốt. |

Không đụng: `ask_kernel_adapter.py`, `_ask_impl.py`, classifier/`shard.py`,
`smart_classifier.py`, `judge*`, `taskkernel*`, `llm_gateway/client.py`,
`.env`, `GA.md`, `spec/`.

### Quyết định thiết kế có ghi chú

- `FreeAPICatalog.refresh(force=True)` mỗi tick (khác chữ "refresh()" trong
  brief): TTL 24h bên trong refresh() chỉ phục vụ đường lazy; nếu không force
  thì 3/4 tick 6h là no-op `cache_fresh` → mất ý nghĩa "tự động cập nhật".
  Đã ghi comment trong code.
- Nguồn LLM CHỈ GỌI seam có sẵn `free_catalog.refresh_free_catalog(force=True)`
  (không sửa file đó); sau khi ok, đọc (read-only)
  `scp.llm_gateway.client.OPENROUTER_FREE_MODELS` để log models count.

## 3. Refresh-on-404 — AUDIT-FIRST: BỎ (không có seam sạch)

Đã audit: grep toàn repo `get_catalog|free_api_catalog` — caller duy nhất là
`v104_routes.py` (status + search, chỉ đọc/lazy-refresh-when-empty); không có
đường nào "caller report model/API 404" quay lại catalog (`404` trong
`data_sources/` chỉ là xử lý HTTP của các fetcher weather/conversion không
liên quan). Theo đúng phạm vi: KHÔNG chế interface mới → phần 3 của thiết kế
BỎ, không code. Nếu cần sau này: thêm hook report-404 tại lớp fetcher dùng
entries (việc của worker khác, có seam thật).

## 4. Test results (local, Windows, Python 3.12.10)

- `python -m pytest tests/T07_learning/test_discovery_scheduler.py -q`
  → **26 passed** (13 hàm, gồm parametrize). Không skip/xfail.
  - (a) tick gọi đúng cả 2 nguồn + log `count=1785` / `models=...` (caplog).
  - (b) catalog raise RuntimeError mỗi tick → LLM vẫn chạy; `run_forever`
    sống nhiều tick, task kết thúc bằng cancel (không chết vì exception).
  - (c) jitter clamp trong [0.9x, 1.1x] (rng cố định + 500 mẫu rng thật);
    run_forever dùng jittered sleep, tick đầu trước lần sleep đầu.
  - (d) kill-switch `off|0|false|OFF|" False "` → `start()` trả None, không
    tạo task; default (unset, "1") → bật.
  - (e) `stop()` hủy sạch: task cancelled, `running_task=None`, idempotent,
    start lại sau stop được.
  - (f) interval parse lỗi (`abc`, `""`, `nan`, `inf`, `-5`, `0`, `12abc`,
    `1e999`, …) → default 21600; giá trị hợp lệ + explicit arg thắng env.
- `python -m pytest tests/T01_boot/ -q` → **37 passed**.
- `python tools/t00_meta_audit.py` → **EXIT=0** ("All integrity checks passed
  (0 new regressions)"; các mục BASELINE_DEBT liệt kê là nợ cũ có sẵn, không
  phát sinh từ file mới của S23).

## 5. Runtime proof (Docker, hôm nay)

```
docker compose up -d --build scp-api   → Image scp-api:local Built, container Recreated+Started
curl /health                           → HEALTH=200
docker logs scp-scp-api-1 | grep S23-DISCOVERY:

2026-09-13 16:51:51,153 | INFO  | scp.core.free_discovery_scheduler | [S23-DISCOVERY] FreeDiscoveryScheduler started (interval=21600s ±10%, first tick immediate)
2026-09-13 16:51:51,154 | INFO  | scp.api | [S23-DISCOVERY] Free discovery wired: FreeAPICatalog + LLM free-model catalog refresh on 6h cadence with jitter
2026-09-13 16:51:51,693 | INFO  | scp.core.free_discovery_scheduler | [S23-DISCOVERY] tick: free_api_catalog ok=True count=1785 (before=1785, network) | llm_free_catalog ok=False models=None
```

- Tick đầu chạy NGAY ~0.5s sau start (chứa cả network fetch).
- `free_api_catalog ok=True count=1785 served=network` → entries count > 0,
  fetch GitHub raw thành công trong container (egress allowlist cho phép
  `raw.githubusercontent.com`).

## 6. Giới hạn & open questions

1. **Nguồn LLM ok=False trong Docker là fail-closed ĐÚNG thiết kế, không phải
   bug scheduler**: log container cho thấy
   `EgressDeniedError: egress denied for 'https://openrouter.ai/api/v1/models':
   host 'openrouter.ai' not in SCP_EGRESS_ALLOWLIST (mode=allowlist)`.
   `openrouter.ai` chưa có trong allowlist egress của deployment. Tôi KHÔNG
   nới policy để "xanh" (FA kỷ luật test). Operator cần thêm `openrouter.ai`
   vào `SCP_EGRESS_ALLOWLIST`/`SCP_LLM_EGRESS_ALLOWLIST` (.env — ngoài phạm vi
   S23) nếu muốn nguồn LLM refresh; scheduler sẽ tự gọi đúng seam ở tick sau.
2. Refresh-on-404 BỎ (không có seam sạch — mục 3).
3. PASS chỉ trong scope đã test: hermetic unit (26) + boot (37) + meta-audit
   (exit 0) + 1 lần boot Docker với 1 tick. Chưa chứng minh: tick định kỳ 6h
   trong runtime thật (cần chạy ≥ interval), hành vi khi GitHub raw trả khác
   format, và nguồn LLM khi egress đã mở.
4. `FreeAPICatalog.refresh(force=True)` mỗi tick là quyết định có chủ ý
   (mục 2) — nếu owner muốn tôn trọng TTL 24h bên trong, đổi 1 tham số ở
   `_default_catalog_refresh`.
5. No-commit: commit do orchestrator thực hiện sau verify. `git diff --stat`:
   `scp/api_server_parts/lifespan.py | 28 ++++++`; file mới:
   `scp/core/free_discovery_scheduler.py`, `tests/T07_learning/test_discovery_scheduler.py`,
   report này. (2 file untracked cũ có sẵn từ trước session: `bench_sha.txt`,
   `reports/SCP_FULL_RUNTIME_RAG_1000_RETRY_V3_2026-08-17.jsonl` — không phải của S23.)

---

## SHA256 (skill binding — append cuối theo contract)

```
4aada0be4873598dc50c3a7f38d90151429bb5263c511a838ed1cdcb4d594d10  .agents/skills/scp-dna/SKILL.md
63f651da13f0ff583c4906222ac08ab4a2403280ab90c66450a01d335da7ffef  .agents/skills/scp-learning-loop-guard/SKILL.md
```
