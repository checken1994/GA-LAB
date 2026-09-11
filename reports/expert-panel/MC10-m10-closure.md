# MC10 — M10 (Streaming) closure progress log

Date: 2026-09-11. Branch: `audit/runtime-guard-AUDIT-20260909`. Worker: MC10.
Session start HEAD: `05c7b01` (M6 pin commit). Guard `git branch --show-current`
checked at session start and before every commit: OK throughout. 3 file WIP
của stream khác (`test_test_infrastructure_fail_closed.py`,
`test_flow_11_admin_import_scp_standard.py`, `test_security_sweep_s6.py`) không
bị chạm, không stash.

## Baseline

- `INVENTORY/M10.txt`: 5 failed / 7 passed (exit 1).
- Bài học M06 áp dụng ngay: 6/7 "passed" là test `pass` TRẮNG
  (`TestFlow10StreamingCausalCoverage` — 6 causal placeholder, FA-01 violation
  của harness cũ); chỉ STREAM-1 là test thật.
- 5 đỏ cùng một họ lỗi HARNESS: patch attribute KHÔNG TỒN TẠI
  (`stream_routes.stream_llm_response`, `stream_routes.LLMGateway`) hoặc patch
  `verify_admin` theo kiểu module-attribute mà `Depends(verify_admin)` đã
  capture lúc decorate → patch không bao giờ được FastAPI quan sát
  (STREAM-5 kỳ vọng 422 nhưng nhận 401 auth-first — hành vi đúng).

## Root-cause (đầy đủ trong `M10-closure.json` → `root_causes`)

| # | Phân loại | Nội dung |
|---|---|---|
| RC-1 | HARNESS | STREAM-2/3/6 patch `stream_llm_response` — attribute không tồn tại → AttributeError trước mọi assert |
| RC-2 | HARNESS | STREAM-4 patch `LLMGateway` — contract phát minh; failover thật nằm trong judge pipeline |
| RC-3 | HARNESS | STREAM-5 patch `verify_admin` vô dụng với `Depends()`; case `model: ""` là contract phát minh (StreamAskRequest không có field model) |
| RC-4 | PRODUCT | **`ask_stream` đọc `verdict.verdict`… dạng attribute trong khi `RealityJudge.judge()` trả dict thuần** → AttributeError trên MỌI request → mọi stream chết ở `step:error`, frame judge-done + final không bao giờ emit, client thấy 200 + lỗi im lặng (fail-silently, trái D6). Chết 100% từ ngày tao ra, không test nào thấy vì harness patch attribute ảo |
| RC-5 | HARNESS (FA-01) | 6 causal `pass` trắng → de-vacuous thành 6 test thật, mỗi test một nhánh causal riêng |
| RC-6 | CROSS-CIRCUIT (không sửa, ghi nhận) | `scp/runtime/judge.py` sync path (~dòng 117) gọi `cross_verify` async KHÔNG await → coroutine chết + TypeError nuốt im lặng → multi-LLM crosscheck DEAD trên mọi sync caller (RuntimeWarning quan sát được trong D1). judge.py dùng chung (M2/M6 domain) → ngoài scope M10, cần owner của judge.py xử lý |

## Fixes (commit pin `1691f7fcbcd1c21305f79ee06c28d572ab5e0b35`)

- `scp/api/routes/stream_routes.py`: đọc dict-contract của judge (`.get`),
  `domain` lấy từ classify step (judge result không có domain), evidence
  isinstance-dict guard; bình luận [M10-FIX] ghi rõ contract. Rollback: revert
  1 hunk. Không thay đổi surface, auth, hay thứ tự frame.
- `tests/T03_capability/test_flow_10_streaming_scp_standard.py`: viết lại toàn
  bộ — **0 mock** (không import unittest.mock), admin auth thật
  (SCP_AUTH_TOKEN_SECRET env + Bearer, pattern T02/M6), HTTP thật qua
  `client.stream` + parse SSE thật, judge thật offline (SCP_EGRESS_MODE=deny),
  autouse rate-limit accounting clear (chỉ accounting), crawl-thread
  suppression (pattern T02/M6, có lý do), 12 test thật (0 skip/xfail):
  STREAM-1..6 + 6 causal de-vacuous.

## Kết quả D1–D8

- D1: 12/12 passed exit 0 tại pin (chạy x3 lần 1: 4.98s/4.92s/5.98s; re-run sau
  anomaly G9: 6.12s — deterministic); regression
  `scp/tests/external_audit/test_security.py` (stream-contract live +
  sync-judge-offload): 9 passed / 2 skipped / 0 failed với
  SCP_CAPABILITY_SECRET default (nuance env standalone — pre-existing, ghi
  trong evidence). Evidence: `M10-evidence/D1-T10-pytest.txt`,
  `D1-T10-regression.txt`.
- D2: build `SCP_GIT_SHA=<pin>`: lần 1 EXIT=0; re-run sau G9 lần đầu EXIT=1
  (transient TLS handshake timeout fetch metadata docker.io) → retry 1 lần
  theo mission → EXIT=0; image `sha256:26189a52…`; force-recreate main
  deployment; /health 200 + `service_identity.commit` == pin; /readiness
  ready. Evidence: `D2-docker.txt`, `D2-docker-build.txt`.
- D3: 12/12 probe **chạy 2 lần độc lập** trên `scp-m10-probe` :8005
  (full-profile, egress deny, token probe per-session không in): 5×401
  negative (no/wrong/scheme auth); adversarial 429 lockout sau 5 fail
  (designed, tự hồi phục ~65s, token hợp lệ cũng bị chặn trong lockout —
  limiter không leak validity); golden path streaming THẬT qua httpx: 200
  `text/event-stream; charset=utf-8`, 6 SSE frame với arrival timestamp tăng
  dần (lan 1 [0.079→0.125]s, lan 2 [0.031→0.093]s) — data chảy thật qua
  chunked HTTP; final frame `step=final/status=complete` có verdict; 2 stream
  liên tiếp 200/200; 422 schema; burst song song 2 stream + health
  200/200/200. Log scan (cả 2 lần): 0 "database is locked", 0 bypass, grep
  stream_routes = 0; 3 Traceback đều là AutoFix (M7 domain) tự vá file
  read-only — pre-existing, fail-closed, 0 liên quan stream. Evidence:
  `D3-m10-runtime.json`, `D3-runtime-setup.txt`.
- D4: reference seal `sha256:4a66b279…` HIGH=0 @1f00d00 (cùng mốc M2/M3/M4/M6);
  diff M10 chưa deep scan riêng (known gap; patch không thêm attack surface).
- D5: chưa có reviewer độc lập artifact cho diff M10 (Agent V 1f00d00 chỉ phủ
  sweep) — PASS_WITH_LIMITS, tuân thủ không self-approve.
- D6: AST scan 0 except:pass trong scope (`D6-ast-scan.txt`); lỗi fail-silently
  lớn nhất của M10 (RC-4) đã được sửa tại điểm lỗi.
- D7: 0 TODO/FIXME/XXX/HACK (`D7-todo-scan.txt`); STATUS-LEDGER dòng M10 cập
  nhật; thiếu module STATUS header + runbook riêng (known gap, như M4/M6).
- D8: `M10-closure.json` (sha_pin `1691f7f…`, falsification_status
  PARTIALLY_FALSIFIED_AT_PIN, 9 known_gaps) + file này.

## ⚠️ Anomaly G9 — mất evidence cuối session (nguyên nhân UNPROVEN)

Sau khi toàn bộ D1–D8 hoàn tất lần đầu (evidence đã được sha256sum xác nhận
tồn tại), khoảng thời gian ngắn trước commit: `M10-evidence/` (6 file),
bản `M10-closure.json` đầu tiên và 3 edit STATUS-LEDGER.md BIẾN KHỎI DISK —
STATUS-LEDGER quay về đúng trạng thái HEAD. Đã kiểm tra: không container nào
mount `reports/` (scp-scp-api-1 dùng named volume; stack scp_v2-* chỉ mount
/tmp/active); không có git operation nào chạy xóa file; dung lượng disk bình
thường (64G free). Nguyên nhân KHÔNG được xác minh — không suy diễn thành
chắc chắn (DNA #26/#31).

Phản ứng theo DNA (không im lặng, không bịa nguyên nhân):
1. Giữ nguyên hiện trạng, ghi nhận anomaly.
2. TÁI TẠO toàn bộ evidence bằng RE-RUN THẬT (không copy file cũ): D1 suite +
   regression, D2 build (retry 1 lần sau transient failure) + recreate +
   health/readiness, D3 full probe matrix trên container mới (12/12 PASS lần 2
   — deterministic), D6/D7 scan lại.
3. Backup evidence ra ngoài repo (`%TEMP%/m10probe/backup/`).
4. Commit NGAY sau khi verify file tồn tại, để bất biến hóa trong git.

## Probe-harness corrections (không đổi product)

- Git Bash (MSYS) tự chuyển `-e SCP_PC_WORKING_DIR=/var/lib/scp` thành
  `C:/Program Files/Git/var/lib/scp` → container crash `/app/C:`; chạy docker
  với `MSYS_NO_PATHCONV=1`. Lần 2: `/var/lib` root-owned trong khi image chạy
  uid 10001 → chuyển sang `/app/data` + `/app` (writable).
- Probe script lần đầu crash do harness truncation 120 ký tự làm JSON cụt —
  sửa probe script, chạy lại toàn bộ matrix.

## Guard status

- Branch check đầu phiên + trước mỗi commit: OK.
- `git add` theo đường dẫn cụ thể; 3 file WIP giữ nguyên modified; stash
  không bị đụng; không in secret (token probe random per-session, đã xoá file
  token sau teardown).

## Giới hạn còn lại

Đọc `M10-closure.json` → `known_gaps` (G1..G8): route 404 trên deployment
chính profile=core; step:error fault-injection không test được nếu không mock;
seal là snapshot @1f00d00; chưa có reviewer độc lập; sync crosscheck dead
(cross-circuit); offline semantic only; regression env nuance; thiếu
header/runbook. Verdict: **CLOSED_WITH_KNOWN_GAP** — không đọc thành
"streaming production-ready".
