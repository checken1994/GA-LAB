# MC-GREEN — M5 (Agent/Call) closure progress log

Date: 2026-09-11. Branch: `audit/runtime-guard-AUDIT-20260909`. Worker: MC-GREEN.
Session start HEAD: `6cdb424` (pin của M5). Guard `git branch --show-current`
kiểm ở đầu phiên + trước mỗi commit: OK.

## Phạm vi (D0)

- Route surface: `/v3/agent/*` (8 endpoint; `_guard` internal/PC-token 403,
  `/autofix/apply` thêm `Depends(verify_admin)` 401) + `/v3/call/*` (2 endpoint,
  `verify_admin` 401). Group profile: `agent`=standard, `call`=full.
- Scope files: agent_routes.py, call_routes.py, agent_orchestrator.py,
  call_session_hub.py, request_run_ledger.py, test_flow_05_*.
- Không sửa product trong mạch này (suite xanh sẵn, probe không lộ bug thật).

## Kết quả D1–D8

- D1: 35/35 passed exit 0 tại pin (3.08s) — khớp baseline. Evidence:
  `M05-evidence/D1-T05-pytest.txt`.
- D2: build `SCP_GIT_SHA=6cdb424…` EXIT=0; image `sha256:0390f8eb…`;
  force-recreate main; /health 200 + commit == pin; /readiness ready.
- D3: 8/8 probe trên `scp-m5-probe` :8006 (full-profile, egress deny, token
  per-session không in): N1-N3 401 auth-first; N4 403 guard; G1-G4 golden 200
  (status online / plan PLAN_READY + trace_id / call session tạo call_id /
  run dry-run PLAN_READY). Join token ngắn hạn trong response G3 đã REDACT
  khỏi evidence. Teardown xong (container + volume riêng scp-m5-data).
- D6: PASS_WITH_LIMITS — 9 silent except:pass đã phân loại (6 instrumentation
  isolation trong request_run_ledger.py có chủ đích + có invariant "do not hide
  the original exception"; 1 WS disconnect expected; 1 best-effort read có field
  quan sát; 1 harness negative-probe). Không có khối nào nuốt failure state.
- D7: PASS_WITH_LIMITS — 0 TODO dangling; thiếu header STATUS + runbook riêng.
- D4/D5: PASS_WITH_LIMITS — seal 4a66b279 là snapshot @1f00d00; không reviewer
  độc lập riêng cho M5 (gap chuẩn nhóm D1_PASS, trung với M2–M6).

## Probe-harness findings (không phải product bug)

1. Git Bash MSYS path conversion biến `-e VAR=/unix/path` thành Windows path khi
   gọi docker.exe → container chết `PermissionError: '/app/C:'`. Fix probe:
   `MSYS_NO_PATHCONV=1`.
2. Image chạy non-root (uid 10001), raw `docker run` không mount volume ghi được
   → `PermissionError: '/var/lib/scp'`. Fix probe: named volume riêng cho probe.
3. `request_run_ledger.py` có mixed CR/LF line endings (777 logical vs 388 `\n`)
   — cosmetic, pre-existing, ast.parse OK.
