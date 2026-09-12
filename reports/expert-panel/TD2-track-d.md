# TD-2 — Track D Report (D1 + D2)

- Agent: SCP Worker Agent TD-2 (Track D cuối)
- Nhánh: `audit/runtime-guard-AUDIT-20260909`
- Ngày: 2026-09-12
- Commits:
  - D1: `e0d60a2` — feat(web): Playwright backend opt-in for web_control (D1)
  - D2: `6d93c25` — feat(mcp): MCP stdio server exposing hands tools through capability PEP (D2)
  - style: `3335466` — ruff autofix cho test D1 (import order, stale noqa)

## Skill binding (bắt buộc)

| Skill | File | SHA256 |
|---|---|---|
| scp-dna | `.agents/skills/scp-dna/SKILL.md` | `4aada0be4873598dc50c3a7f38d90151429bb5263c511a838ed1cdcb4d594d10` |
| scp-web-orchestration-safety | `.agents/skills/scp-web-orchestration-safety/SKILL.md` | `2a4c98023709c441aa7720b8f3765083e8f5bec231899f952d8cb5d7134377a6` |
| scp-reality-verifier | `.agents/skills/scp-reality-verifier/SKILL.md` | `a9d65ce53b18f8310ceeb302b18b341a0e1b8b19cddc7f46d4fa6ee99432269e` |

(Đã load + áp dụng: evidence-first loop, anti-honeypot rules, mức bằng chứng A–D,
`PASS_WITHIN_SCOPE` thay cho claim tuyệt đối.)

## D1 — Playwright backend opt-in cho web_control

### Backend interface map

File mới: `scp/web_control/playwright_backend.py` — class `PlaywrightBackend`.

| Method | Kiểu | Contract |
|---|---|---|
| `start()` / `stop()` | async | lifecycle khai báo; browser chạy per-call nên không giữ process bền. `start()` fail-closed ngay nếu thiếu package playwright (RuntimeError kèm hướng dẫn cài `scp/requirements-optional-web.txt`). |
| `browse(url, max_chars=100_000)` | async | trả `{success, url, title, text_content (trim + cap), text (alias), status, method: "playwright-ephemeral", timestamp}`. |
| `search_public(query, max_results=10)` | async | navigate GET tới HTML search endpoint (không fill form, không submit), extract anchor hiển thị; trả dict cùng shape `InternetSearch.search` (`results` list); thất bại → `success: False` (không fallback âm thầm). |
| `navigate_and_read(url)` | async | shape tương thích `BrowserSession.navigate_and_read` cho `WebNavigator.browse_logged_in`. |
| `status()` / `targets()` | async | status backend; `targets()` trả `[]` (không có DevTools session dùng chung). |
| `validate_url(url)` | sync | scheme http/https, chặn credentials, chặn `..` (kể cả `%2f`-decoded), canonical SSRF `scp.security.url_safety.validate_url`; loopback chỉ đi qua khi `allow_internal=True` tường minh (cùng quy ước `safe_urlopen`). |
| `type_and_submit` / `cdp_command` / `open_visible` | sync | raise `NotImplementedError` — backend read-only (anti-honeypot: cấm tương tác form/submit). |

Pattern concurrency: navigator là async → backend dùng `playwright.sync_api` qua
`asyncio.to_thread`; mỗi call launch một Chromium headless ephemeral profile
(state independence giữa các task theo skill web-orchestration-safety) và luôn
đóng trong `finally` (không rò rỉ process).

### Anti-honeypot / safety giữ nguyên

- Hard timeout cơ học: playwright navigation timeout (default 20s, clamp 1–30s,
  env `SCP_WEB_PLAYWRIGHT_TIMEOUT_SECONDS`) + outer `asyncio.wait_for` (timeout+5s)
  → `TimeoutError` fail-closed; không bao giờ chờ network idle
  (`wait_until="domcontentloaded"`).
- Content size cap: `text_content` trim + cap `max_chars` (clamp 1–1_000_000).
- Chỉ trích `document.body.innerText` (text hiển thị) bằng biểu thức JS hằng số
  (không nội suy chuỗi untrusted) → node ẩn (display:none/honeypot) không tới caller.
  Test chứng minh: honeypot ẩn bị loại khỏi kết quả.
- Read-only: không fill/submit/click; mọi URL qua validate trước khi navigate.

### Opt-in contract

- `SCP_WEB_BACKEND=playwright` (exact, sau trim) → `WebNavigator` tự dùng
  `PlaywrightBackend` cho `browse()` / `search_public()` / `status()` /
  `browse_logged_in()` (qua `self.browser`).
- `SCP_WEB_BACKEND_ALLOW_INTERNAL=1` → cho phép loopback (chỉ dùng cho test/local);
  mặc định chặn như navigator cũ.
- Env unset/rỗng/giá trị khác (kể cả `Playwright`, `playwright2`) → behavior cũ
  GIỮ NGUYÊN: `self.browser` là `BrowserSession`, `self.search_engine` là
  `InternetSearch`, không import playwright ở module scope (lazy import trong nhánh opt-in).
- Inject tường minh `WebNavigator(browser=...)` luôn thắng env.
- `browse_public()` (đường httpx SSRF-safe) không đổi — chỉ `browse()` đi qua backend.
- Fail-closed khi thiếu playwright: constructor navigator vẫn tạo được (lazy),
  call-time raise `RuntimeError` với message rõ (kiểu caller đã xử lý:
  `RuntimeError` là convention hiện có của `browser_session.py`).

### Dependency

- File mới `scp/requirements-optional-web.txt`: `playwright==1.61.0` (pin ==
  version đã verify cùng chromium cache cục bộ) — KHÔNG thêm vào main requirements.
- Môi trường local: playwright 1.61.0 + chromium đã có sẵn → test thật chạy đủ.

### Kết quả test D1 — `tests/T03_capability/test_playwright_backend.py`

29 passed. Điểm chính:
- (a) opt-off: env unset/rỗng/`Playwright`/`playwright2`/… → `BrowserSession` +
  `InternetSearch` + `_playwright_backend is None`; inject tường minh thắng env.
- (b) opt-on + chromium thật (local ThreadingHTTPServer, port 0): title/text khớp,
  status 200, `text_content` bounded; honeypot ẩn KHÔNG xuất hiện trong kết quả;
  shape `navigate_and_read` tương thích.
- (c) traversal/egress: `file://`, `..`, `..%2f`, credentials, `ftp://`,
  `javascript:` → ValueError TRƯỚC khi navigate (không cần browser); loopback
  SSRF bị chặn khi không có allow_internal (cả đường navigator opt-in).
- (d) timeout: server local treo 30s + timeout 1s → fail-closed < 20s, server
  vẫn healthy sau đó (postcondition); thiếu playwright (mô phỏng bằng import
  machinery thật: `sys.modules[...] = None`) → RuntimeError rõ ràng; navigator
  opt-in thiếu playwright fail-closed tại call time.
- Không infra-skip nào phát sinh: chromium cài được nên (b)(d) chạy thật.

## D2 — MCP stdio server cho hands tools

### Protocol choice

Tự implement JSON-RPC 2.0 line-delimited qua stdio (stdlib only), method
`initialize` / `ping` / `tools/list` / `tools/call` — KHÔNG dùng package `mcp`.
Lý do (ghi theo yêu cầu):
1. MCP stdio là newline-delimited JSON-RPC 2.0; 4 method này chỉ ~400 dòng,
   auditable trong 1 file, không phát sinh dependency/supply-chain mới
   (không cần pin thêm package).
2. Phần security-sensitive (transport-token guard, capability PEP) phải nằm
   trong fail-closed code của repo, không chôn trong SDK thứ ba.
3. Stdio only, KHÔNG mở port mới; log chỉ đi stderr, stdout là protocol channel
   thuần (JSON ensure_ascii).

### Tools list (từ Action Registry thật của hands)

| Tool | Authz path | Hành vi |
|---|---|---|
| `hands_status` | transport token (arg `transportToken` ≡ header `X-SCP-PC-Token`) qua `hmac.compare_digest` với `SCP_PC_CONTROLLER_TOKEN`; không cấu hình/missing/sai → deny | mirror GET `/v3/hands/status`: `HandsExecutor.status()` + `planner.status()` |
| `hands_plan` | transport token | mirror POST `/v3/hands/plan`: `ActionRegistry.policy_preview(action, capabilityLevel, approved)`; unknown action → `success: False` |
| `hands_execute` | transport token + capability token (arg `capabilityToken` ≡ field `capabilityToken` của `HandsActionRequest`) | mirror POST `/v3/hands/execute`: `parse_capability_token` → `TaskKernelHandsBridge.execute(...)` — CÙNG PEP, KHÔNG có executor path riêng; `PermissionError`/`InvalidTokenSignatureError` → error result PermissionError-shape |

Deny-by-default: thiếu transport token → `{errorType: "PermissionError", code:
"permission_denied"}` với `isError: true`; thiếu capability token → bridge raise
`CapabilityRequiredError … (FA-05)` TRƯỚC khi resolve action/mutation kernel
(zero kernel state — test kiểm chứng bằng đếm row `tasks` trong sqlite).

Isolation cho local run: `SCP_MCP_HANDS_DATA_DIR` (hands data dir) +
`SCP_PC_WORKING_DIR` (workspace PC) — mặc định không set dùng đúng data dir chuẩn
như hands_routes. `SCP_CAPABILITY_SECRET` thiếu → server từ chối start (GAP-09
fail-closed, exit != 0, stderr nêu rõ).

### Authz evidence (NO-MOCK, subprocess thật)

Test `tests/T03_capability/test_mcp_server.py` spawn `python -m scp.mcp_server`
(Popen thật, env隔离 tmp) và nói chuyện qua stdin/stdout pipe thật: 16 passed.
- initialize + tools/list → đúng 3 tools, có inputSchema.
- `hands_execute` không token nào → PermissionError-shape, file side-effect KHÔNG tồn tại.
- Có transport token, thiếu capability token → `CapabilityRequiredError (FA-05)`,
  không file, zero kernel task row.
- Transport token sai → PermissionError-shape (status tool cũng bị deny).
- Fixture token: `CapabilityAuthority(state file CÙNG data dir với server, secret
  trùng env subprocess).issue("hands:pc.status")` → `hands_execute` chạy thật
  end-to-end (`success: true`, `verification.passed: true`).
- Token sai scope → `CapabilityScopeMismatchError (INV-AUTH-02)`, không file.
- `dryRun` → success nhưng không mutate.
- Protocol: unknown tool `-32602`, unknown method `-32601`, tools/list trước
  initialize `-32002`, JSON malformed `-32700`.
- Startup thiếu secret → process exit != 0.

Hai bug trong TEST đã sửa trong quá trình chạy (không phải product): (1) helper
chờ response cho notification (`notifications/initialized` — chuẩn MCP không trả
response); (2) fixture token ký bằng secret conftest thay vì secret của subprocess.

## Verify cuối

- Baseline trước thay đổi: `tests/T03_capability/` = **709 passed, 0 failed** (89.63s, commit trước D1).
- Sau D1+D2: `tests/T03_capability/` = **754 passed, 0 failed** (96.75s) — fail count không tăng (709 cũ + 45 test mới).
- File mới: D1 29 passed, D2 16 passed.
- `py_compile` OK cho toàn bộ file mới/sửa:
  `scp/web_control/playwright_backend.py`, `scp/web_control/web_navigator.py`,
  `scp/mcp_server/__init__.py`, `scp/mcp_server/__main__.py`, `scp/mcp_server/server.py`,
  `tests/T03_capability/test_playwright_backend.py`, `tests/T03_capability/test_mcp_server.py`.

### Mimosa normal scan (HEAD = 3335466)

- scanId: `scan-2026-09-12T13-55-41.689Z-f5863cb40540`
- Seal: `sha256:cbf69e7791e71d3d5b00f0204a188ed714190ea7ecbbab9a05f9a101eb6edd0e`
- Kết quả: **HIGH = 0** (không tăng), medium = 15, low = 98, businessLogic = 0, verdictEffect = none.
- Attribution: **0 findings** chạm vào các file mới/sửa của nhiệm vụ này
  (`playwright_backend.py`, `web_navigator.py`, `mcp_server/*`, 2 test file,
  `requirements-optional-web.txt`). 15 medium thuộc file có sẵn
  (reports/circuit-closures/M04-evidence/_probe_http.py ×7,
  mini-services/llm-bridge/core.ts ×4, scp/autofix/evolution.py ×2,
  scp/autofix/scanners/xss_scanner.py ×2) — pre-existing, ngoài phạm vi TD-2.
- Hạn chế bằng chứng (ghi trung thực): coverage của scan là `partial`
  ("source manifest collection incomplete, some files not included",
  runStatus `inconclusive`) — kết quả HIGH=0 là trong phạm vi đã scan, không
  khẳng định tuyệt đối cho toàn repo.
- Comment hygiene đã tự kiểm: không thêm `requests.get(`/`eval(` hay token
  shape vào comment mới; không in secret thật (chỉ test-secret fixture).

## Scope & hạn chế (PASS_WITHIN_SCOPE)

- D1 đổi behavior CHỈ khi env opt-in; mặc định byte-identical (chưa kiểm chứng
  byte-level bằng diff output runtime — kiểm chứng bằng contract test kiểu/shape).
- Egress của browser: URL validation tại PEP là lớp chặn hiện có của navigator;
  chưa tích hợp egress proxy nội bộ cho Chromium (gap đã biết của repo, không
  phải regression mới).
- D2: MCP server single-threaded tuần tự; chưa có notification server-side
  (listChanged=false), chưa có resource/prompt capability — đúng phạm vi 3 tools.
- Search qua Playwright phụ thuộc selector của search engine công khai (untrusted
  data; fail-closed khi parse rỗng).
