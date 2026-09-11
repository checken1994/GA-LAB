# S5b — Security Sweep bổ sung: 9 HIGH findings còn lại của `dashboard/`

- **Agent:** S5b (Worker Agent, chạy độc lập)
- **Ngày:** 2026-09-10
- **Branch:** `audit/runtime-guard-AUDIT-20260909` (KHÔNG commit — thay đổi để review)
- **Snapshot HEAD khi làm:** `067e636`
- **Nguồn findings:** `C:\Users\check\.mimosa\security-scans\project-362369a5effad96dedf43711\scan-2026-09-09T19-17-22.715Z-b3d7d688beca\findings.json` — 9 finding HIGH tại `dashboard/` mà report S5 §4 đã liệt kê chờ owner (8× SSRF CWE-918 + 1× path-traversal CWE-22). Đã verify lại từng finding ID trong findings.json trước khi sửa.
- **Skill áp dụng:** `scp-dna` (evidence-first, smallest reversible patch, reality test) + `scp-capability-security-review` (PEP đặt ngay trước sink, deny-by-default, không tự nâng UNKNOWN thành ALLOW).
- **Tái sử dụng helper S5:** toàn bộ 8 route SSRF dùng lại `dashboard/src/lib/probe-allowlist.ts` (export `isAllowedProbeTarget` có sẵn) — **không viết logic allowlist mới**; chỉ thêm 1 export nhỏ thuần túy `parseHostList` (split/trim/lowercase) để 8 route không copy-paste parse env.

## 1. Kết luận điều hành

Verdict: **9/9 findings trong phạm vi S5b đã xử lý xong, có bằng chứng static + runtime.** Cả 8 route SSRF giờ có PEP `isAllowedProbeTarget(...)` ngay trước từng `fetch` sink; route status có boundary containment trước mọi fs access. Output shape của mọi route giữ nguyên (blocked target đi vào catch/cấu trúc lỗi có sẵn của route). Không đụng phần uncommitted của worker khác trong 3 file v3 (khối `X-SCP-PC-Token` nguyên vẹn — xem diff).

**Giới hạn bằng chứng (DNA #22/#23):** đây là fix + test ở mức static-wiring (guard đứng trước sink trong source) + behavioral (verdict allowlist là function call thật) + runtime 1 route đại diện qua bun. KHÔNG claim "toàn dashboard không còn SSRF": còn các sink khác ngoài 9 file này (vd `tools/scp_dashboard_bridge.py:10` — cùng findings.json, ngoài scope S5b); cần re-scan Mimosa sau khi merge.

## 2. Fix theo finding (file:line)

### 2.1. 8× SSRF (CWE-918) — taint: env (`SCP_API_URL` / `SCP_BASE_URL`, mặc định `http://127.0.0.1:8000`) → `fetch`

Không route nào lấy URL từ request body/user (đã đọc code từng file: ask/call-session/voice/v3-* chỉ đẩy payload hoặc GET thuần) → theo pattern S5: gate defense-in-depth với allowlist mặc định (loopback/RFC1918/docker.internal) để không phá chức năng; mở rộng operator qua env mới `SCP_API_ALLOWED_HOSTS` (comma-separated, exact match — không có collision với env nào cũ, đã grep).

| File | Finding ID | Gate (dòng) | Fetch sink (dòng) |
|---|---|---|---|
| `dashboard/src/app/api/scp/ask/route.ts` | finding:bef96113f10d8d384e8eb8b7 | 56 | 60 |
| `dashboard/src/app/api/scp/call/session/route.ts` | finding:146d9582759f68e194bcfe39 | 31 | 35 |
| `dashboard/src/app/api/scp/v3/hands/planner/status/route.ts` | finding:944f0defee5ec19d2e219f1a | 17 | 21 |
| `dashboard/src/app/api/scp/v3/hands/status/route.ts` | finding:968c8577f544bc8904ddb298 | 24 | 28 |
| `dashboard/src/app/api/scp/v3/pc/status/route.ts` | finding:d98b7e1d81c1d89ff6980f03 | 24 | 28 |
| `dashboard/src/app/api/scp/v3/web/search/route.ts` | finding:80dc4479ea912ff4fe33731f | 21 | 25 |
| `dashboard/src/app/api/scp/v3/web/status/route.ts` | finding:e16066ae760cc30140c14b69 | 24 | 28 |
| `dashboard/src/app/api/scp/voice/route.ts` | finding:b513a9623aaa0d9c033801c3 | 41 | 45 |

- **PEP tại sink:** mỗi route thêm `const guard = isAllowedProbeTarget(\`${base}/...\`, EXTRA_API_HOSTS)` ngay trước `await fetch(...)`; nếu `!guard.allowed` → `throw` vào **catch có sẵn** → response đúng shape lỗi cũ của route đó, không request nào rời process:
  - v3 GET routes: `{version, planner:"offline", planCount, activePlan, states, error}` (200) / `{hands:"offline", version:"3.2", error}` / `{controller:"offline", error}` / `{navigator:"offline", orchestrator:"offline", error}` (503) — nguyên shape.
  - ask/voice/call-session: `{error: message.slice(0,300)}` (502) — nguyên shape.
- **`parseHostList` (export mới của `probe-allowlist.ts`):** parse env thành list host exact-match cho tham số `extraHosts` của `isAllowedProbeTarget` — pure, never throws, có test behavioral.
- **Bug tự phát hiện qua reality test:** 4 file v3 ban đầu bị sai depth import relative (5 `../` thay vì 6) — node test không bắt được (chỉ đọc source), nhưng `tsc --noEmit` bắt TS2307 ở đúng 4 file → sửa thành `../../../../../../lib/probe-allowlist`. DNA #26: reality (tsc) có quyền cuối.

### 2.2. `dashboard/src/app/api/scp/status/route.ts:81` — path-traversal (CWE-22) — finding:1827bf0d8e92358bde84bc24

- **Phân tích:** `computeAutofixLoc(relPath)` đọc `scp/autofix/*.py` qua `path.join(SCP_ROOT, relPath)` + `statSync/readFileSync`. `relPath` hiện là **compile-time constant** từ bảng `V4_MODULES` (12 path, đều `scp/...`, không có request/user input nào chạm hàm này) → không exploit được thực tế, nhưng scanner đúng ở chỗ không có root boundary tường minh.
- **Remediation (resolve + containment, không phải reword FP):** thay `path.join` bằng `path.resolve(rootAbs, relPath)` + điều kiện `abs === rootAbs || abs.startsWith(rootAbs + path.sep)`; vi phạm → `throw` vào fallback path có sẵn (`LAST_VERIFIED_FALLBACK_LOC`, hoặc `loc=0/live=false` nếu không có) — behavior với 12 path hiện tại **không đổi** (tất cả resolve vào trong root). Bonus: `path.resolve` neutralize luôn absolute-path traversal (absolute `relPath` sẽ thay base rồi fail `startsWith`). Boundary chạy **trước cả `statSync` lẫn `readFileSync`** (route.ts:92–98).

## 3. Bằng chứng verify (lệnh + kết quả thật)

| # | Verify | Lệnh | Kết quả |
|---|---|---|---|
| 1 | Test sweep (29 cũ + 14 mới) | `node tests/T03_capability/test_security_sweep_s5.mjs; echo EXIT=$?` | **43 passed, 0 failed, EXIT=0** (chạy lại lần 2 sau khi sửa import depth — vẫn 43/43) |
| 2 | Typecheck | `cd dashboard && ./node_modules/.bin/tsc --noEmit` | **TSC_EXIT=0, 0 error TS** (binary local, không `npx tsc` theo lưu ý S5; lỗi TS2307 depth import x4 đã bắt và sửa ở vòng 1) |
| 3 | Runtime route đại diện | `bun run` script tạm import `v3/pc/status/route.ts` + gọi `GET()` thật 2 lần | **Path A (allow):** `SCP_API_URL=http://127.0.0.1:9` → `status=503`, `controller="offline"`, error là lỗi connect (KHÔNG chứa "probe allowlist") → gate cho loopback qua, backward compat giữ nguyên. **Path B (deny):** `SCP_API_URL=http://dashboard-ssrf-deny-test.example.invalid` (RFC2606 .invalid, không resolve được — nếu gate hỏng thì fetch fail vì DNS, không bao giờ tới host thật) → `status=503`, error=`"SCP endpoint blocked by probe allowlist: host dashboard-ssrf-deny-test.example.invalid not in probe allowlist"` → **gate DENY trước fetch** (error là message của guard, không phải DNS error). `BUN_EXIT=0` |
| 4 | Grep cuối 8 route SSRF | `grep -n "isAllowedProbeTarget(\`\|await fetch(\|parseHostList(process.env"` từng file | 8/8 route: **fetch_count=1, gate_count=1, gate line < fetch line** (bảng §2.1); env `SCP_API_ALLOWED_HOSTS` wired đủ 8/8 |
| 5 | Grep cuối status route | `grep -n "path.resolve(rootAbs\|startsWith(rootAbs\|statSync(\|readFileSync("` | containment ở dòng 92–93, đứng **trước** `statSync` (98) và `readFileSync` (102) |
| 6 | Phạm vi file | `git diff --stat` (9 route) + `git status` | Đúng 9 route flagged (+16/-0 line S5b tại 3 file v3 vẫn tách bạch với khối `X-SCP-PC-Token` của worker khác — đã xem diff) |

**Test mới (14 check S5b, tổng file 43):** (a) 3 behavioral `parseHostList` + 1 combo feed vào `isAllowedProbeTarget` (operator host được phép, không có extension thì DENY — deny-by-default); (b) 8 wiring check — mỗi route 1 check: gate call (`isAllowedProbeTarget(\`` — needle khớp đúng call-site, không khớp dòng import) phải đứng **trước** `await fetch(`, env extension wired, deny reason có mặt; (c) 2 check status route: containment resolve+startsWith phải đứng trước mọi fs access + toàn bộ 12 path module là relative constant dưới `scp/` không chứa `..`; (d) 1 checkAsync runtime `v3/pc/status` (degrade INFO dưới node vì `next/server` không import được — evidence runtime thật lấy qua bun, bảng #3). Không có mock của guard — mọi verdict đều là function call thật.

## 4. File thay đổi (toàn bộ, KHÔNG commit)

| File | Thay đổi |
|---|---|
| `dashboard/src/lib/probe-allowlist.ts` | +18 dòng — export `parseHostList` (pure helper cho `extraHosts`, policy allowlist KHÔNG đổi) |
| `dashboard/src/app/api/scp/ask/route.ts` | +14 — import + `EXTRA_API_HOSTS` + gate trước fetch |
| `dashboard/src/app/api/scp/call/session/route.ts` | +14 — như trên |
| `dashboard/src/app/api/scp/voice/route.ts` | +14 — như trên |
| `dashboard/src/app/api/scp/v3/hands/planner/status/route.ts` | +15 — như trên |
| `dashboard/src/app/api/scp/v3/hands/status/route.ts` | +16 (S5b) — như trên; khối `X-SCP-PC-Token` của worker khác giữ nguyên |
| `dashboard/src/app/api/scp/v3/pc/status/route.ts` | +16 (S5b) — như trên; khối `X-SCP-PC-Token` giữ nguyên |
| `dashboard/src/app/api/scp/v3/web/search/route.ts` | +15 — như trên |
| `dashboard/src/app/api/scp/v3/web/status/route.ts` | +16 (S5b) — như trên; khối `X-SCP-PC-Token` giữ nguyên |
| `dashboard/src/app/api/scp/status/route.ts` | +16/-1 — containment resolve+startsWith trong `computeAutofixLoc`, fallback behavior giữ nguyên |
| `tests/T03_capability/test_security_sweep_s5.mjs` | +14 check S5b (section 6–8) + cập nhật docstring scope |
| `reports/expert-panel/S5b-dashboard-sweep.md` | **mới** — báo cáo này |

Rollback: `git checkout --` 9 route + reverting phần thêm của `probe-allowlist.ts`/test (2 file này untracked, rollback = revert edit trong session S5b). Không có migration/data change; không secret nào được in (env chỉ đọc tên biến, không giá trị).

## 5. Open questions / missing pieces

1. **Re-scan Mimosa** cần chạy lại để xác nhận 9 finding này đóng và không có regression mới; findings.json hiện tại còn chứa finding cũ (static snapshot) — không thể claim "HIGH=0 dashboard" chỉ dựa trên fix.
2. `tools/scp_dashboard_bridge.py:10` (SSRF, cùng findings.json) vẫn chưa có owner — ngoài scope dashboard/ của S5b.
3. Env `SCP_API_ALLOWED_HOSTS` (và `SCP_HEALTH_ALLOWED_HOSTS`/`LLM_EGRESS_ALLOWED_HOSTS` của S5) chưa có trong `.env.example` — nên thêm commented khi merge (ngoài ràng buộc "chỉ sửa file flagged" của S5b).
4. Gate cho phép RFC1918 + docker.internal theo allowlist mặc định của S5 — nếu dashboard deploy ở network untrusted, nên siết bằng `SCP_API_ALLOWED_HOSTS` positive-list + không set `SCP_API_URL` rộng.
5. Scanner taint trên env var là defense-in-depth heuristic: các route này chỉ fetch base từ env operator — nếu tương lai có route fetch URL từ request, cần gate chặt hơn (loopback-only) theo đúng luật trong task.
