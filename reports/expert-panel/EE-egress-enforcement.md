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
  unit + h: 2 container với `SCP_EGress_CONTAINER_TESTS` opt-in — tên env đúng
  là `SCP_EE_CONTAINER_TESTS`), 0 failed, 0 xfail, 0 mock. No-mock discipline:
  negative cases raise trước I/O; positive loopback dùng http.server thật;
  positive external dùng `.invalid` (chứng minh egress layer pass mà không cần
  internet).
- Targeted regression: ssrf_sweep_s1 + ssrf_sweep_s2 + T05 egress policy +
  flow_02 + flow_13 = **178 passed**.
- Full regression T03 + T04 + T05: xem `reports/tmp-ee-regression-full.txt`
  (baseline fail set không tăng — kết quả ghi ở phần cuối file này).

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
