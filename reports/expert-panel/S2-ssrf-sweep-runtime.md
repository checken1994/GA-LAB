# S2 — SSRF Sweep đợt 2: `scp/runtime/` + defuse FP wiremixin

- **Agent:** S2 (Worker Agent, sweep độc lập)
- **Ngày:** 2026-09-10
- **Branch:** `audit/runtime-guard-AUDIT-20260909` (KHÔNG commit — thay đổi để review)
- **Base commit lúc chạy verify:** `067e636216977c420e79811ebe4e75bd1c7bc05d`
- **Nguồn findings:** `C:\Users\check\.mimosa\security-scans\project-362369a5effad96dedf43711\scan-2026-09-09T19-17-22.715Z-b3d7d688beca\findings.json`
- **Skill áp dụng:** `scp-dna` (evidence-first, smallest reversible patch, reality test) + pattern chuẩn S1 (`safe_urlopen` + pure URL builder).

## 1. Phạm vi findings (scan 2026-09-09T19:17)

Findings filter `location.path` bắt đầu `scp/runtime/` + `wiremixin`:

| File | Class | Số lượng | Xử lý |
|---|---|---|---|
| `scp/runtime/slms_parts/entertainmentslm.py` | ssrf (L271, L331) | 2 | FIXED |
| `scp/runtime/slms_parts/misc_slms2.py` | ssrf (L533,600,618,747,803,862) | 6 | ĐÃ FIX từ S1 — verified lại: file chỉ còn comment, 0 raw call-site |
| `scp/runtime/storage_manager.py` | sql-injection (L272), path-traversal (L315) | 2 | OUT OF SCOPE (khác class SSRF, khác thẩm quyền sửa — xem §4) |
| `scp/autofix/evolution_parts/wiremixin.py` | hardcoded-credential (L54–59) | 6 | FIXED (restructure FP) |

Lưu ý: scan là snapshot 2026-09-09; reality hiện tại (grep) cho thấy ngoài 2 điểm `entertainmentslm.py`, còn 11 raw call-site SSRF cùng pattern ở 3 file copy mà scan chưa kịp flag — đã sweep luôn trong đợt này (xem §2).

## 2. Điểm FIX theo file

Pattern áp dụng theo mẫu S1 (`misc_slms2.py`, `experts/lifestyle.py`): host là literal cố định trong builder pure; input động bị chặn (regex fullmatch) hoặc encode (urlencode / quote(safe='')) TRƯỚC khi fetch; fetch đi qua `scp.security.url_safety.safe_urlopen` (gate B310: scheme allowlist + chặn private/loopback/link-local IP).

| File | Call-site sửa | Builder mới/sửa |
|---|---|---|
| `scp/runtime/slms_parts/entertainmentslm.py` | 2 — SWAPI search (L271 cũ), TVMaze singlesearch (L331 cũ); bỏ 2 comment `# nosec B310 — URL validated by SCP` sai lệch (urlopen thô, không gate) | `build_swapi_url` (fullmatch `^[a-z0-9_]{1,32}$` cho api_type + `quote(safe='')` cho name), `build_tvmaze_url` (urlencode) |
| `scp/runtime/slms_parts/foodslm.py` | 3 — MealDB, CocktailDB, Fruityvice | `build_mealdb_search_url`, `build_cocktaildb_search_url` (urlencode), `build_fruityvice_url` (`quote(safe='')` — 1 path segment) |
| `scp/runtime/experts/lifestyle.py` | 4 — MealDB, CocktailDB, Fruityvice, Open-Meteo geocode | reuse builder từ `foodslm` + `build_city_search_url` từ `misc_slms2` (single source of truth, không copy) |
| `scp/runtime/slm_impls/lifestyle_slm.py` | 4 — MealDB, CocktailDB, Fruityvice, Open-Meteo geocode (bản copy LIVE được `slms.py:506` import) | reuse như trên |
| `scp/autofix/evolution_parts/wiremixin.py` | 6 FP hardcoded-credential | dict `api_to_datasource` (key chứa literal `_API_KEY` trông như credential assignment) → module-level `API_DATASOURCES: tuple[tuple[str, str], ...]` gồm `("EIA","energy"), ("USDA","agriculture"), ("NVD","cybersecurity"), ("CASE_LAW","legal"), ("GOOGLE_FACT_CHECK","reality"), ("NASA","astronomy")`; call-site build `f"{source}_API_KEY"` + `f"scp/data_sources/{module}.py"` lúc runtime. Mapping/behavior giữ nguyên hệt; KHÔNG đổi logic khác của file. |

Tổng: **13 raw call-site SSRF** trong `scp/runtime/` được chuyển qua `safe_urlopen` + builder pure; **6 FP wiremixin** defuse.

Diff: 5 file, +283/−147 (xem `git diff --stat`).

## 3. Điểm còn lại + lý do (grep verify bắt buộc)

`grep -rn "requests\.get\|urllib\.request\.urlopen\|httpx\.get" scp/runtime/ | grep -v safe_urlopen | grep -v test` — **0 call-site fetch raw còn lại**. Các dòng còn lại trong grep đều là comment/docstring, không phải mã thực thi:

| Dòng còn lại | Lý do |
|---|---|
| `scp/runtime/engine_parts/direct_api_verifier.py:61` | Docstring của `_session_get` — **implementation bên TRONG verifier-gate** (DirectAPIVerifier, fallback judge Step 7, `engine.py:76`). Dùng `requests.Session` + `params=` (requests tự encode) + `raise_for_status`, host cố định theo domain. Theo đúng quy tắc nhiệm vụ #5: fetch bên TRONG implementation gate thì GIỮ. Scanner cũng không flag file này trong findings. |
| `scp/runtime/slms_parts/foodslm.py:20`, `entertainmentslm.py:22`, `experts/lifestyle.py:355`, `slm_impls/lifestyle_slm.py:355`, `slms_parts/misc_slms2.py:733` | Comment ghi lý do fix ("thay requests.get cũ không có SSRF guard") — không phải code. |

`grep -n "_API_KEY" scp/autofix/evolution_parts/wiremixin.py` — **không còn literal `_API_KEY` trong dict keys** (dict đã bị xóa). Còn lại:

| Dòng | Nội dung | Phân loại |
|---|---|---|
| 20, 23, 71 | Comment giải thích restructure + pattern build | comment |
| 64 | `_re.search(r"([A-Z][A-Z0-9_]*_API_KEY)", bug.description)` — regex TRÍCH XUẤT key từ bug description (logic có sẵn, scanner không flag dòng này) | regex pattern, không phải assignment |
| 74 | `api_key_var == f"{source}_API_KEY"` | f-string build theo đúng spec nhiệm vụ |

## 4. Out of scope — để lại cho gate sau

- `scp/runtime/storage_manager.py:272` (sql-injection HIGH), `:315` (path-traversal HIGH): **khác class** với SSRF sweep này; sửa SQL/path cần review riêng (schema/principle của storage layer). KHÔNG tự sửa để tránh patch vượt thẩm quyền. Mimosa commit gate cần một đợt sweep chuyên sql-injection/path-traversal (hoặc gộp vào S3) để về 0 HIGH.
- `direct_api_verifier.py` giữ nguyên (gate implementation — xem §3).

## 5. Verify bắt buộc — bằng chứng

### 5.1 Pytest T03_capability (pipe-exit-code discipline)

| Lần | Trạng thái tree | Kết quả | EXIT |
|---|---|---|---|
| Baseline (trước mọi sửa) | 5 file chưa sửa | `34 failed, 524 passed` | 1 |
| Sau khi sửa | 5 file đã sửa + test S2 mới | `39 failed, 544 passed` | 1 |
| Counterfactual (revert đúng 5 file của S2 qua `git stash`-style patch, exclude test S2) | 5 file reverted | **`39 failed` — tập FAILED GIỐNG HỆT 100% (diff exit 0)** | 1 |
| Sau re-apply patch (final) | 5 file đã sửa + test S2 mới | `39 failed, 544 passed` (giống hệt counterfactual) | 1 |

Đọc kết quả (DNA #22/#26 — phân biệt correlation với causation): mức 34→39 **không phải do diff S2** — tập 39 failed with-changes và without-changes trùng nhau từng tên test. 5 test tăng thêm (`test_flow_08_audit_benchmark` x2, `test_flow_09_threat_analysis` x3 — nhóm `requires_admin`) fail không deterministic giữa các run và nằm đúng domain `scp/api/routes/threat_routes.py` / `admin_v100.py` đang có uncommitted changes của agent khác trong cùng working tree (xác nhận qua `git status scp/`). Fail khi chạy isolated: PASS. Cần gate riêng xác nhận (ngoài thẩm quyền S2).

`tests/T03_capability/test_ssrf_sweep_s2.py` (mới, no-mock, thuần function): **25/25 PASS** — kiểm build-URL helpers (input xấu → ValueError trước fetch / encode không thể đổi host-path), reuse builder qua import (regression guard), mapping `API_DATASOURCES` derive đúng 100% mapping cũ, guard chống hồi quy raw-fetch trên 4 file đã patch.

### 5.2 Docker (runtime/judge import lúc boot)

```
docker compose -f compose.yml build scp-api          → BUILD-EXIT=0 (image scp-api:local)
docker compose -f compose.yml up -d --force-recreate → container scp-scp-api-1 Recreated/Started, UP-EXIT=0
curl http://127.0.0.1:8000/health                    → HTTP 200 (attempt 1)
  body: {"status":"ok","service_identity":{"service_name":"scp-backend","mode":"isolated",...}}
```

Reality check trong container: `build_swapi_url` (3 matches) + `API_DATASOURCES` (3 matches) có trong image; `foodslm.py` trong container có 0 `requests.get(`. Boot log: 0 match `error|traceback|importerror` (chỉ warning `free_catalog` do egress policy deny — cấu hình chủ đích).

## 6. Giới hạn bằng chứng (không tuyên bố quá)

- `PASS` ở đây = "không thấy failure trong scope test đã nêu": 25 test pure-function cho builder + full suite không tăng fail + health 200 lúc boot. KHÔNG tuyên bố hệ thống hoàn toàn không SSRF/secure.
- Không re-run Mimosa scan sau patch (scanner thuộc coordinator); kỳ vọng: 8 ssrf findings trong `scp/runtime/` (2 entertainmentslm + 6 misc_slms2 cũ) sẽ mất ở scan kế tiếp, 6 hardcoded-credential wiremixin mất vì literal đã bị xóa. 2 findings `storage_manager.py` sẽ CÒN — cần đợt sweep chuyên trách.
- Full suite T03 đang có 39 fail liên quan threat/audit routes từ working tree chung — cần agent phụ trách xác nhận (S2 chỉ chứng minh không phải do diff của mình).
- Các test flow dùng live API (một số fail baseline do 429/network — ví dụ NASA 429 trong run) — môi trường test có phụ thuộc mạng thật.
