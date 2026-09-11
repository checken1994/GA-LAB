# S1 — SSRF Sweep đợt 1: `scp/data_sources/` + `scp/core/`

- **Agent:** S1b (Worker Agent, tiếp nối sweep bị ngắt giữa đường từ S1a)
- **Ngày:** 2026-09-10
- **Branch:** `audit/runtime-guard-AUDIT-20260909` (KHÔNG commit — thay đổi để review)
- **Nguồn findings:** `C:\Users\check\.mimosa\security-scans\project-362369a5effad96dedf43711\scan-2026-09-09T19-17-22.715Z-b3d7d688beca\findings.json` — filter ssrf/high, `location.path` ∈ `scp/data_sources/` + `scp/core/` → **43 findings** trong 22 file.
- **Skill áp dụng:** `scp-dna` (evidence-first, smallest reversible patch, reality test) + pattern chuẩn (`safe_urlopen` + pure URL builder, mẫu `misc_slms2.py` / `wikipedia_client.py`).

## 1. Trạng thái đợt 1 (S1a) — đã verify lại, KHÔNG đụng lại

Snapshot scan 2026-09-09 flag 43 điểm ssrf/high in-scope. Grep reality lúc S1b tiếp nối: S1a đã xử lý xong phần lớn — `wikipedia_client` (46 test PASS), `alphavantage`, `biology`, `chemistry`, `cornell_lii`, `dtic`, `geography`, `live_knowledge`, `medical`, `unesco`, `astronomy` (chỉ còn docstring), `finance`, `history`, `weather`, `audit_fetcher`, `ai_threat_scanner`, `harm_detector`, `reality_engine`, `streaming_factcheck`, `circuit_breaker`, `fast_learning_engine`. Các điểm còn lại do **S1b** fix trong đợt này (§2).

## 2. Điểm FIX của S1b theo file (call-site → builder + safe_urlopen)

Pattern: host là literal cố định trong builder pure; input động bị chặn (regex fullmatch / int-coerce) hoặc encode (urlencode / `quote(safe='')`) TRƯỚC khi fetch; fetch qua `scp.security.url_safety.safe_urlopen` (scheme allowlist + chặn private/loopback/link-local IP). `r.json()` → `json.loads(r.read().decode(...))`; `status_code != 200` / `raise_for_status()` → `HTTPError` (fail behavior giữ nguyên, fallback UNData giữ nguyên).

| File | Call-site sửa | Builder mới |
|---|---|---|
| `scp/data_sources/courtlistener.py` | 1 (search opinions) | `build_courtlistener_search_url` (urlencode) |
| `scp/data_sources/eric.py` | 1 (search) | `build_eric_search_url` (urlencode, key optional) |
| `scp/data_sources/google_factcheck.py` | 1 (claims:search) | `build_google_factcheck_url` (urlencode, truncate 500) |
| `scp/data_sources/gutenberg.py` | 2 (book + author, chung 1 URL shape) | `build_gutenberg_search_url` |
| `scp/data_sources/newsapi.py` | 1 (everything) | `build_newsapi_everything_url` (urlencode, truncate 100) |
| `scp/data_sources/glottolog.py` | 3 (glottocode / iso639 / language search) | `build_glottocode_url` (fullmatch `^[a-z]{4}\d{4}$`), `build_glottolog_language_url` (fullmatch `^[a-z]{3}$` hoặc urlencode) |
| `scp/data_sources/noaa.py` | 1 (data) | `build_noaa_data_url` (urlencode dict) |
| `scp/data_sources/metmuseum.py` | 2 (search + object) | `build_met_search_url`, `build_met_object_url` (int-coerce, >0) |
| `scp/data_sources/undata.py` | 1 (JsonService search; fallback giữ nguyên) | `build_undata_search_url` |
| `scp/data_sources/usgs.py` | 2 (min_mag + recent) | `build_usgs_query_url` (urlencode dict) |
| `scp/data_sources/wikiart.py` | 2 (artist + painting search) | `build_wikiart_artist_url` (fullmatch `^[\w\-]{1,128}$` unicode-aware — giữ slug tiếng Việt; chặn `/?#@%.`), `build_wikiart_painting_search_url` |
| `scp/data_sources/worldbank.py` | 1 (country/indicator) | `build_worldbank_indicator_url` (fullmatch `^[A-Za-z]{3}$` cho country, `quote(safe='')` cho indicator) |
| `scp/data_sources/fred.py` | 1 (series/observations) — phát hiện thêm ngoài danh sách gốc | `build_fred_observations_url` (fullmatch `^[A-Z0-9]{2,20}$` — đúng shape SERIES_MAP: GDP, GS10, A191RL1Q225SBEA) |
| `scp/data_sources/free_api_catalog.py` | 1 (`urllib.request.urlopen` trong `_http_get`) | không cần builder (URL là hằng `CATALOG_SOURCE_URL`); thay raw urlopen bằng `safe_urlopen` sau allowlist host + egress check (defense in depth) |
| `scp/core/top_systems_learning.py` | 2 (`_http_get_json` + `_http_get_raw`) | không cần builder (host đã allowlist `ALLOWED_HOSTS` + egress check); thay raw urlopen bằng `safe_urlopen` |
| `scp/core/multi_source_verifier.py` | 2 (wttr.in + Wikipedia summary) | không cần builder riêng (URL đã được quote + check scheme/host ngay tại chỗ); thay `httpx.get` bằng `safe_urlopen` (urllib tự follow redirect ≈ `follow_redirects=True` cũ); bỏ `import httpx` |
| `scp/core/knowledge_curation.py` | 3 (arXiv / HN Algolia / StackExchange) | không cần builder riêng (URL literal + `quote(query)` có sẵn); thay `httpx.get` bằng `safe_urlopen`; bỏ `import httpx` |
| `scp/core/question_fetchers/_common.py` | 1 (`_SESSION.get` trong `_http_get_json`) | thêm `validate_url(url)` trước MỌI fetch (cả nhánh requests.Session lẫn nhánh urllib) — giữ connection pooling, fail-closed → None |
| `scp/core/question_fetchers/knowledge_fetchers.py` | 1 (`_SESSION.get` trong `fetch_arxiv_physics`) | thêm `validate_url(url)` trước `_SESSION.get` |

Tổng: **27 raw call-site** trong 19 file chuyển qua gate (`safe_urlopen` hoặc `validate_url` cho nhánh session).

## 3. Điểm còn lại + lý do (grep verify bắt buộc)

`grep -rn "httpx\.\|requests\.get\|urllib\.request\.urlopen\|_SESSION\.get\|requests\.Session()" scp/data_sources/ scp/core/` (loại trừ comment/docstring) — còn đúng các điểm sau, đều có lý do giữ:

| Điểm còn lại | Lý do |
|---|---|
| `scp/core/url_fetcher.py` (toàn file), `scp/core/api_utils.py` (toàn file) | **Chính là hạ tầng fetch an toàn (gate)**: `http.client` pin-connection + `fetch_with_retry` + IP-check. `requests`/`urlopen` bên TRONG 2 file này là implementation của gate — GIỮ NGUYÊN theo quy tắc nhiệm vụ. |
| `scp/core/question_fetchers/_common.py:25` `_SESSION = requests.Session()` | Chỉ là tạo session (connection pooling), không phải fetch. Cả 2 đường fetch qua session đều đã có `validate_url` chặn trước. |
| `scp/core/question_fetchers/_common.py:97` `_SESSION.get(...)` | GATED — `validate_url(url)` chạy ngay trước (scheme + hostname + private/loopback/link-local IP). Giữ để không mất pooling + default headers. |
| `scp/core/question_fetchers/knowledge_fetchers.py:134` `_SESSION.get(...)` | GATED — `validate_url(url)` trước, URL là literal `https://export.arxiv.org/...` cố định. |

Các match còn lại trong grep đều là comment/docstring (ghi lý do fix, ví dụ "thay raw httpx.get").

## 4. Verify (evidence)

| Bước | Kết quả |
|---|---|
| Baseline TRƯỚC khi sửa | `python -m pytest tests/T03_capability/ -q` → **34 failed / 549 passed, EXIT=1** |
| `test_ssrf_sweep_s1.py` sau khi sửa | **81 passed** (46 cũ + 35 mới: 33 builder test fail-closed không network + 2 static no-raw-fetch gate), EXIT=0 |
| Full T03 SAU khi sửa | **34 failed / 584 passed, EXIT=1** — fail KHÔNG tăng (34→34; 584 = 549 + 35 test mới). `pytest --lf` xác nhận đúng 34/618; tất cả nằm ở flow_04/06/07/09/10/12 (domain admin/capability/streaming/doubt-cron — pre-existing của agent khác, đúng cảnh báo nhiệm vụ) |
| Docker | `docker compose build scp-api` OK → `up -d --force-recreate` OK → `curl /health` → **200** `{"status":"ok",...}` |
| Grep cuối | raw call-site ungated trong `scp/data_sources/` + `scp/core/` = **0** (xem §3) |

## 5. Giới hạn bằng chứng (scope statement)

- Đây là sweep static call-site + unit test pure-builder (không network trong test). PASS nghĩa là: không còn raw fetch bypass gate trong phạm vi 2 package; không khẳng định toàn hệ thống "secure/production-ready".
- Nhánh `_SESSION.get` giữ `requests` (không đổi sang `safe_urlopen`) vì cần connection pooling; đã thêm `validate_url` làm gate — nếu gate sau yêu cầu bắt buộc `safe_urlopen` tuyệt đối thì cần quyết định riêng (hybris: mất pooling/headers mặc định).
- Các finding HIGH khác class (sql-injection/path-traversal trong `storage_manager.py` v.v.) ngoài phạm vi đợt này — xem `S2-ssrf-sweep-runtime.md` §4.
