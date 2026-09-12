# SCP Expert Panel — Agent EE (Egress Enforcement)

## Kết luận điều hành

Đóng known-gap cuối cùng M13 `G1_EGRESS_DENY_NOT_ENFORCED`: `SCP_EGRESS_MODE=deny`
nay được enforce tại một choke point duy nhất (`scp/security/url_safety.py`),
wire vào cả 3 fetcher chuẩn, kèm static regression gate chặn call-site bypass
mới. Falsification M13 (urllib ra internet HTTP 200 trong container deny) đã
được **RE-FALSIFIED-THEN-CLOSED** bằng container runtime proof trên image build
tại commit fix. Phạm vi claim: mọi fetch path đi qua 3 module gate; các call-site
`requests` nằm ngoài gate được inventory-pinned có lý do; KHÔNG claim hệ thống
production-ready tổng thể.

## Skill binding (SHA256, đọc đầu session 2026-09-12)

| Skill | SHA256 |
|---|---|
| `.agents/skills/scp-dna/SKILL.md` | `4aada0be4873598dc50c3a7f38d90151429bb5263c511a838ed1cdcb4d594d10` |
| `.agents/skills/scp-capability-security-review/SKILL.md` | `83f1633256756f8e4951471a11b9d45c1738d09f4db851df8ee91ee123a235ee` |
| `.agents/skills/scp-reality-verifier/SKILL.md` | `a9d65ce53b18f8310ceeb302b18b341a0e1b8b19cddc7f46d4fa6ee99432269e` |

## Thiết kế enforce (file:line tại commit EE docs)

- `scp/security/url_safety.py`
  - `EgressDeniedError(PermissionError, ValueError)` — diamond inheritance:
    PermissionError = capability semantics (theo task contract EE);
    ValueError giữ nguyên contract "policy violation raises ValueError" của
    fetcher chuẩn (mọi `except ValueError` fail path hiện có: graceful skip,
    no-retry — không phá caller denial-unaware).
  - `enforce_egress_policy(url) -> None` — pure check, idempotent (gọi 2 lần
    vô hại). Mode đọc từ `SCP_EGRESS_MODE`:
    - `deny|offline|disabled` → chỉ loopback (`localhost`, `127.0.0.1`, `::1`
      và IP-literal loopback qua `ipaddress.is_loopback`) được qua.
    - `allowlist` → loopback + host trong `SCP_EGRESS_ALLOWLIST`
      (comma-separated, exact-match sau normalize lower/strip-root-dot).
    - unset → không thêm hạn chế (giữ hành vi dev hiện tại; SSRF check sẵn
      vẫn chạy).
    - mode lạ → dev: không thêm hạn chế; production (`SCP_PRODUCTION_MODE`
      thuộc `{"1","true","yes","on"}`, mirror `production_guard._TRUE`):
      EgressDenied (fail-closed). Unset+production cũng fail-closed (hợp lệ
      vì `production_guard` vốn từ chối boot khi thiếu mode).
  - Loopback LUÔN được qua trong mọi mode (self-probe/internal services).
    Hostname KHÔNG được resolve trong gate (resolution-based SSRF blocking
    vẫn thuộc `validate_url`/`_resolve_public_ips`) — tránh double-DNS và
    TOCTOU.
  - `safe_urlopen` gọi `enforce_egress_policy` TRƯỚC `validate_url` (egress
    là lớp trong cùng, deterministic trước mọi DNS I/O).
- `scp/core/url_fetcher.py` `_safe_fetch_url` — gọi `enforce_egress_policy`
  trên MỌI redirect hop; giữ nguyên inline unset-default-deny có sẵn (không
  loosening behavior cũ).
- `scp/core/api_utils.py` `fetch_with_retry` — gọi `enforce_egress_policy`
  đầu hàm; EgressDenied là ValueError → rơi vào nhánh "policy violation →
  None, no retry" đúng contract.
- `scp/security/cisa_kev.py` `_open_cisa_feed` — raw `urllib.request.urlopen`
  (call-site raw duy nhất còn lại trong product) đổi sang `safe_urlopen`;
  host/path allowlist riêng giữ làm defense-in-depth.
- `scp/api/routes/batch_benchmark_routes.py` `_request_one` — enforce trước
  self-call (target bị `_validate_local_base_url` giới hạn loopback).

## Census + static gate (chống tái diễn — bài học M13)

AST census toàn bộ `scp/` (loại trừ 3 module gate) tại thời điểm bắt đầu:
10 call-sites / 7 files. Xử lý:

| Call-site | Xử lý |
|---|---|
| `scp/security/cisa_kev.py:51` urllib urlopen | FIX — route qua `safe_urlopen` |
| `scp/api/routes/batch_benchmark_routes.py:141` requests.post | enforce tại chỗ + PIN (loopback-only self-call, đã validate ở API boundary) |
| `scp/benchmark/*` (5 files, 8 sites) requests.get/post | PIN — operator CLI load-generator đánh vào URL server SCP do operator cấp (health/ask), không phải runtime product fetcher |

Gate tĩnh: `tests/T03_capability/test_egress_enforcement.py::
test_g_scp_tree_has_no_unpinned_raw_http_calls` — AST scan `scp/`, FAIL với
danh sách file:line cho MỌI call-site (file, kind) không nằm trong inventory
pinned có lý do; FAIL ngược nếu pin stale (call-site đã được fix nhưng pin
chưa gỡ). Các test `test_g_static_gate_*` chứng minh gate bắt file bẩn
(urllib/requests) và pass file sạch.

## Runtime proof — đảo ngược falsification M13 (evidence cấp C)

Image: `scp-egress-ee:<short-sha>` build từ Dockerfile với
`--build-arg SCP_GIT_SHA=<HEAD>`; build EXIT=0.

| # | Kịch bản | Kết quả quan sát được |
|---|---|---|
| A | Container `SCP_EGRESS_MODE=deny`, `safe_urlopen('https://example.com')` | `EE_EGRESS_BLOCKED` — EgressDeniedError trước mọi network I/O, exit 0 (M13: HTTP 200 thành công) |
| B | CONTROL container unset mode, cùng fetch | `EE_CONTROL_FETCH_OK status= 200` — internet container thật reachable; egress gate là differentiator; dev behavior giữ nguyên |
| C1 | Container deny full-profile, `/health` 127.0.0.1:8080 | READY 200 |
| C2 | Trong container deny: `safe_urlopen('http://127.0.0.1:8080/health', allow_internal=True)` | `EE_LOOPBACK_OK 200` — loopback luôn qua |
| C3 | Trong container deny: POST `/v104/learn/top-systems` (fetch GitHub+Wikipedia thật; M13 P6 = ok:true records=3) | `ok:false, records:0, deep_readmes:0`, errors chứa `EgressDeniedError` cho cả `api.github.com` và `en.wikipedia.org` — fail-closed, 0 external fetch |

Evidence files: `reports/circuit-closures/M13-evidence/EE-egress-container-reversal.txt`,
`EE-egress-endpoint-fail-closed.txt`, `EE-egress-pytest-suite.txt`.

## Test results

- `tests/T03_capability/test_egress_enforcement.py`: **18 passed** (a–g: 16
  unit + h: 2 container tests, opt-in `SCP_EE_CONTAINER_TESTS=1`), 0 failed,
  0 xfail, 0 mock. No-mock discipline: negative cases raise trước I/O;
  positive loopback dùng http.server thật; positive external dùng `.invalid`
  (chứng minh egress layer pass mà không cần internet).
- Targeted regression: ssrf_sweep_s1 + ssrf_sweep_s2 + T05 egress policy +
  flow_02 + flow_13 = **178 passed**.
- Full regression A/B (cùng máy, cùng untracked filesystem state, cùng pytest
  config; evidence `M13-evidence/EE-regression-ab.txt`):
  - A — baseline `e09edf3` (trước EE): **1009 passed, 23 skipped, 0 failed**.
  - B — EE HEAD `56a4566`: **1025 passed, 25 skipped, 0 failed**
    (+16 unit EE tests, +2 container skips opt-in). Fail set 0 → 0, không tăng.
  - Disclosure: 1 run T03+T04+T05 đầu có 1 FAILED hiện đại duy nhất
    (`test_flow_07...::test_auto_rollback_triggers_on_regression`); không tái
    hiện ở cả 2 run A/B đầy đủ và pass khi chạy đơn lẻ → flaky one-off, không
    liên quan egress (autofix rollback test, không chạm network).

## Commits (branch `audit/runtime-guard-AUDIT-20260909`)

| Commit | Nội dung |
|---|---|
| `61d068f` | fix(egress): choke point + wire 3 fetcher chuẩn + cisa_kev + batch_benchmark_routes |
| `da16d5d` | test(egress): EE suite + static raw-call-site gate (M13 latch) |
| (EE docs commit) | M13 closure resolution + evidence files + report này |

## Findings / gaps còn lại

| ID | Severity | Mô tả | Hướng xử lý |
|---|---|---|---|
| EE-G1 | Low | Gate tĩnh chỉ bắt `urllib.request.urlopen`, `requests.get/post`, `httpx.get/post` trực tiếp (theo spec); `requests.Session().get/post`, `httpx.Client()`, `socket`-level, subprocess curl nằm ngoài pattern. Session-based fetchers (`question_fetchers`) đã có sweep S1/S2 bắt `validate_url` riêng. | Mở rộng AST scan cho method-call trên biến Session khi cần |
| EE-G2 | Low | 8 call-sites `requests` trong `scp/benchmark/*` được PIN (operator CLI, không phải runtime fetcher) thay vì convert sang choke point — tránh đụng behavior tool benchmark ngoài scope. | Session sau convert nếu muốn uniform |
| EE-G3 | Info | `EgressDeniedError` là OSError-contract? — Không: là `PermissionError` (OSError subclass) + `ValueError`; caller dùng `except OSError` rộng có thể nuoot im lặng denial (fetch vẫn không xảy ra — fail-closed giữ nguyên, chỉ mất log). | Rà caller `except OSError` nếu muốn loud-fail |
| EE-G4 | Info | Abbreviated IPv4 (`http://127.1/`) KHÔNG được coi là loopback bởi `ipaddress` (Python 3.12 từ chối dạng rút gọn) → deny trong mode deny: fail-CLOSED (strict hơn), không phải leak. | Không cần sửa |
| EE-G5 | Info | Enforcement là application-layer (Python). Process tự viết raw socket / thư viện native ngoài 3 module gate vẫn thoát được ở tầng OS — đúng hạn chế chung của egress app-layer (cần proxy/netns riêng nếu muốn phủ OS-level). | Out of scope session này |

## Verdict

`PASS_WITHIN_SCOPE` cho claim: "SCP_EGRESS_MODE=deny/allowlist được enforce
fail-closed trên mọi fetch path đi qua 3 fetcher chuẩn SCP, kèm gate tĩnh chặn
call-site bypass mới; M13 G1 đã đảo ngược bằng container runtime proof."
KHÔNG mở rộng thành "hệ thống egress hoàn chỉnh/production-ready" (EE-G1→G5).

## V-EE verification + S13 remediation (2026-09-12)

Agent V-EE verify lại bằng chứng EE trên runtime và phát hiện **2 residual
Session-bypass** — call-site `requests.Session` không đọc `SCP_EGRESS_MODE`,
ngoài pattern của static gate (đúng như EE-G1 đã dự báo). Agent S13 vá theo
task contract; skill binding đọc đầu session:

| Skill | SHA256 |
|---|---|
| `.agents/skills/scp-dna/SKILL.md` | `4aada0be4873598dc50c3a7f38d90151429bb5263c511a838ed1cdcb4d594d10` |
| `.agents/skills/scp-capability-security-review/SKILL.md` | `83f1633256756f8e4951471a11b9d45c1738d09f4db851df8ee91ee123a235ee` |

### Findings V-EE → fix S13

| ID | Finding | Fix (file:line tại commit S13) | Contract giữ nguyên |
|---|---|---|---|
| V-EE-1 | `scp/core/question_fetchers/_common.py::_http_get_json` — nhánh chính `_SESSION.get` chỉ qua `validate_url` (SSRF), KHÔNG đọc `SCP_EGRESS_MODE`; nhánh urllib fallback đã gate sẵn bên trong `safe_urlopen` | `enforce_egress_policy(url)` TRƯỚC `validate_url` (cùng thứ tự với `safe_urlopen`) — phủ CẢ 2 nhánh bằng 1 gate (`_common.py:108`, import `:17-20`; commit `91076a6`) | `EgressDeniedError` là ValueError subclass → rơi vào `except Exception → None` fail-closed có sẵn: contract docstring "Returns None on error" giữ nguyên; loopback không bị siết thêm (gate không chặn loopback; SSRF layer vẫn chặn như cũ) |
| V-EE-2 | `scp/runtime/engine_parts/direct_api_verifier.py::_session_get` — raw `requests.Session().get` KHÔNG qua gate nào; wired vào /ask judge path (judgecore_mixin V13 UNKNOWN fallback, engine.py:132) | `enforce_egress_policy(url)` là statement đầu tiên — PEP ngay trước driver, fail-closed trước cả việc tạo session/import requests (`direct_api_verifier.py:73`, import `:38`; commit `38cf2fc`) | Mọi caller `_verify_*` bọc `except Exception → verdict UNKNOWN`; denial surface thành UNKNOWN graceful cho /ask — không đổi behavior nào khác |

### Tests (section (i), commit `4ffd15b`)

5 test mới trong `tests/T03_capability/test_egress_enforcement.py`, no-mock
discipline (negative raise trước mọi I/O; positive dùng sentinel session ghi
 nhận call, không chạm network):

- deny chặn `_http_get_json` nhánh requests: `None` + **0 fetch attempt**
  (contract None được pin đúng sau gate).
- loopback vẫn mở ở egress layer dưới deny + pin layering: ValueError cho
  loopback URL đến từ SSRF `validate_url`, KHÔNG từ gate egress mới.
- unset mode: gate no-op, fetch đi tới Session (chống over-tightening).
- `DirectAPIVerifier._session_get` raise `EgressDeniedError` (ValueError
  contract) dưới deny; `verify()` đầy đủ vẫn UNKNOWN graceful (integration
  nhẹ đường /ask judge); không tạo session dưới deny.
- 4 host domain (restcountries/pubchem/coingecko/wikipedia) bị deny trước
  I/O; loopback exception vẫn đúng.

### Kết quả chạy thật (S13, working tree sau `4ffd15b`)

- `tests/T03_capability/test_egress_enforcement.py`: **21 passed, 2 skipped**
  (2 skips = container tests opt-in `SCP_EE_CONTAINER_TESTS=1`, declared).
- Regression `tests/T03_capability` đầy đủ: **777 passed, 2 skipped, 0
  failed** — fail không tăng (baseline 0F).
- Targeted: `test_ssrf_sweep_s2.py` + `tests/T05_gateway`: **73 passed**.

### Commits S13 (branch `audit/runtime-guard-AUDIT-20260909`)

| Commit | Nội dung |
|---|---|
| `91076a6` | fix(egress): Session bypass V-EE-1 — `_http_get_json` đọc `SCP_EGRESS_MODE` |
| `38cf2fc` | fix(egress): Session bypass V-EE-2 — `_session_get` sau egress gate |
| `4ffd15b` | test(egress): pin closure V-EE-1/2 (section i) |
| (docs commit) | ledger EE rows + section này |

### Scope còn lại (trung thực)

- Static gate EE-G1 vẫn CHƯA scan method-call trên biến Session — 2 bypass
  vừa vá được phát hiện bằng review thủ công của V-EE, không phải bởi gate
  tự động. Việc mở rộng AST scan cho `*.Session.get/post` vẫn là việc cần
  làm nếu muốn latch tự động cho lớp call-site này.
- Claim của S13: "2 residual Session-bypass được vá fail-closed, contract
  caller giữ nguyên, suite T03 0F". KHÔNG claim "mọi call-site HTTP trong
  scp/ đã qua gate" (EE-G1/G5 còn mở: Session scan tự động, subprocess curl,
  raw socket, OS-level egress).

## S14 — đóng gap EE-G1: static gate mù với method-call trên biến Session/Client (2026-09-12)

Agent S14 mở rộng static gate cho LỚP bypass mà raw direct-spelling gate không
thấy: `s = requests.Session(); s.get(url)`. V-EE-1/2 thuộc đúng lớp này và chỉ
được phát hiện bằng review thủ công — census + gate mới làm nó machine-detectable.

Skill binding đọc đầu session S14:

| Skill | SHA256 |
|---|---|
| `.agents/skills/scp-dna/SKILL.md` | `4aada0be4873598dc50c3a7f38d90151429bb5263c511a838ed1cdcb4d594d10` |
| `.agents/skills/scp-capability-security-review/SKILL.md` | `83f1633256756f8e4951471a11b9d45c1738d09f4db851df8ee91ee123a235ee` |

### Thiết kế census/gate dùng chung (commit `09d1764`)

- `scp/security/egress_static_scan.py` — AST walker (không regex source):
  - track biến/attribute được gán từ client constructors: `requests.Session()`
    /`requests.session()`, `httpx.Client()`/`httpx.AsyncClient()`,
    `urllib.request.build_opener()`/`OpenerDirector()`, `aiohttp.ClientSession()`
    (kèm alias import `import requests as rq`, `from httpx import AsyncClient`);
  - bắt cả `with ... as client` (sync/async), walrus, chain `self._session`
    /`Cls._session` (mọi method, không chỉ `__init__`), alias `s = session`,
    inline `requests.Session().get(url)`, và one-hop interprocedural: truyền
    client vào hàm cùng file → track param tương ứng (fixpoint);
  - flag method `get/post/put/delete/patch/head/options/request/stream/send/
    open/urlopen` gọi TRỰC TIẾP trên client (không flag `session.cookies.get`,
    `session.headers.update`, `dict.get` — receiver là attribute CỦA client);
  - exemption fail-closed: site chỉ "gated" khi function scope chứa call
    `enforce_egress_policy` tại dòng <= dòng call. `validate_url`/SSRF KHÔNG
    được exempt — V-EE-1 đã chứng minh "SSRF-only + Session.get" là bypass.
- `tools/ee_g1_census.py` — runner ghi
  `reports/expert-panel/EE-G1-client-method-census.json` (file:line, method,
  receiver, function, gated/ungated). Gate và census dùng MỘT implementation
  (không thể drift).

### Census ban đầu (tại `f4b61b0`, trước S14 fix): 10 call-site UNGATED

| # | Site (census) | Function | Lỗi | Fix S14 |
|---|---|---|---|---|
| 1 | `scp/meta/logical_auditor.py:204` `client.post` | `_call_llm` | OpenRouter judge path — client truyền qua param, KHÔNG đọc SCP_EGRESS_MODE (authorize_outbound là zero-cost PEP, không phải egress) | `enforce_egress_policy(self._base_url)` đầu try → except → None → UNKNOWN graceful |
| 2 | `scp/runtime/notifications.py:245` `client.post` | `_send_webhook._send` | webhook = external WRITE không gate | enforce trước async-with → outer except → False |
| 3 | `scp/web_control/web_navigator.py:75` `client.stream` | `browse_public` | SSRF validate mỗi hop nhưng không đọc egress mode | enforce trước fetch đầu + RE-GATE mỗi redirect hop |
| 4 | `scp/web_control/internet_search.py:124` `client.get` | `search` | DuckDuckGo/Bing không gate | enforce per-provider → errors[] graceful |
| 5 | `scp/knowledge/scheduled_crawler.py:191` `client.get` | `_crawl_entity` | crawler external không gate | enforce trước khi mở client → result.error |
| 6 | `scp/security/threat_detector.py:198` `client.get` | `refresh_tor_exits` | feed Tor exit list (URL constant, external) không gate — nhất quán với CISA KEV đã gate | enforce → best-effort skip |
| 7 | `scp/security/threat_intel.py:169` `client.get` | `_fetch_with_retry` | threat-intel fetch không gate; except tuple không bắt EgressDenied | enforce per-attempt → None NGAY (không retry) — contract "None on failure" giữ nguyên |
| 8 | `scp/llm_gateway/client.py:355` `self._client.post` | `_call_model_once` | chỉ có llm_egress_allowed (list riêng SCP_LLM_EGRESS_ALLOWLIST), thiếu generic gate | enforce URL thật → denial map sang sentinel `egress_denied` có sẵn (không retry, breaker không ghi failure) |
| 9 | `scp/llm_gateway/free_catalog.py:49` `client.get` | `_fetch_catalog_models` | catalog fetch thiếu generic gate | enforce đầu try → None |
| 10 | `scp/web_control/browser_session.py:39` `client.get` | `targets` | loopback CDP self-call | enforce thêm để đồng bộ PEP (loopback được allow mọi mode → runtime no-op) |

`PINNED_CLIENT_CALL_SITES` trong gate hiện RỖNG: mọi site đã qua
`enforce_egress_policy` trong scope nên không cần pin (khác raw gate nơi
scan không nhìn thấy enforce). Cơ chế pin vẫn sẵn sàng cho site tương lai có
lý do (mẫu batch_benchmark).

### Static gate mới (section g2, commit cuối S14)

`test_g2_scp_tree_has_no_unpinned_client_method_calls`: scan toàn `scp/`
(loại trừ 3 module gate), FAIL trên bất kỳ site ungated không pin, kèm
anti-drift/anti-stale như raw gate + sanity `gated >= 12`. 4 unit test kèm
chứng minh scanner: (1) flag đúng pre-fix V-EE-1 shape, (2) with-binding +
param-passing, (3) không false-positive với dict/cookie-jar/mount/close,
(4) site có enforce trong scope = gated.

### Regression fail mới do EE lộ ra + harness fix (commit `de1e405`)

T03 full suite fail ổn định 3 lần: `test_web_browse_requires_token` —
`EgressDeniedError: host 'example.com' not in SCP_EGRESS_ALLOWLIST
(mode=allowlist)`. Root cause (audit hook + import-bisect): import test module
nào kéo `scp.api_server` → `load_selected_env()` (api_server.py:12) nạp
`<repo>/.env` lúc COLLECTION → `.env` chứa `SCP_EGRESS_MODE=allowlist` +
`SCP_PRODUCTION_MODE=1` → CẢ suite âm thầm chạy dưới egress policy server.
Trước EE, web_navigator không đọc mode nên pollution vô hình — EE enforcement
đã lộ nó (đúng hành vi, sai môi trường test). Fix harness tại điểm lỗi:
`tests/conftest.py` snapshot env cha và restore CHÍNH XÁC 3 egress keys sau
collection (pytest_collection_finish) — chỉ XÓA nguồn policy ngẫu nhiên,
không thêm policy nào, không sửa assertion/test case.

### Kết quả chạy thật (S14, working tree sau `de1e405`)

- `tests/T03_capability/test_egress_enforcement.py`: **26 passed, 2 skipped**
  (2 skips = container opt-in, declared).
- Regression T03 đầy đủ: trước fix **781 passed, 1 failed** (3 lần tái hiện) →
  sau harness fix **782 passed, 0 failed, 2 skipped** (fail không tăng so với
  baseline S13 0F).
- Regression T04_kernel: **205 passed, 0 failed, 23 skipped**.
- Census cuối (HEAD `de1e405`): **12/12 client call-sites gated, 0 ungated**;
  raw direct-spelling: 9 sites khớp PINNED_RAW_CALL_SITES (không drift).
- `py_compile` OK cho 12 file chạm/sửa.

### Commits S14 (branch `audit/runtime-guard-AUDIT-20260909`)

| Commit | Nội dung |
|---|---|
| `09d1764` | feat(egress): shared AST client-tracking scanner + census runner |
| `2540e83` | fix(egress): gate LLM/judge client call-sites (logical_auditor, free_catalog, llm client) |
| `77467aa` | fix(egress): gate security-intel + webhook call-sites (threat_detector, threat_intel, notifications) |
| `015b3d6` | fix(egress): gate web-control + crawler call-sites (internet_search, web_navigator, browser_session, scheduled_crawler) |
| `de1e405` | fix(test-harness): isolate suite from .env egress keys loaded at collection |
| (docs commit) | gate g2 + census JSON cuối + mục S14 + M13 G1 note |

### Scope còn lại (trung thực)

- Scanner per-file: client tạo ở module A, import sang module B không được
  track xuyên import; constructor SUBCLASS (`class S(requests.Session)`) chưa
  track. Cả hai là hạn chế đặt tên, không phải claim "bắt được hết".
- Exemption là function-scope + line-order, chưa phải dataflow URL chính xác —
  bù bằng việc census in `function` + `receiver` cho review thủ công.
- Vẫn ngoài scope EE-G1 (đã ghi từ trước): subprocess curl, raw socket,
  OS-level egress (G5), non-HTTP scheme fetch.
- Claim S14: "mọi method-call trên biến HTTP client trong scp/ hiện đọc
  SCP_EGRESS_MODE qua enforce_egress_policy, và latch g2 chặn tái diễn lớp
  này". KHÔNG claim "mọi đường egress trong scp/ đã được chặn" (xem scope trên).
