# MC-GREEN — M7 (AutoFix & Policy) closure progress log

Date: 2026-09-11. Branch: `audit/runtime-guard-AUDIT-20260909`. Worker: MC-GREEN.
Pin: `554f43e86aca49e7bdd7fabe69b24832ee20aa39` (commit docs M5; không product fix).

## Phạm vi (D0)

- Route surface: 9 endpoint `/v105/autofix/*` (toàn bộ `Depends(verify_admin)`).
  v105_routes.py là file dùng chung (M6 predictions / M13 learn) — closure M7
  chỉ claim phần autofix.
- Scope files: v105_routes.py + autofix/{engine,runner,policy_gate,permission,
  classifier}.py + runner_phases/{ast_scan,shadow_canary}.py + test_flow_07.

## Kết quả D1–D8

- D1: 43/43 passed exit 0 tại pin (46.59s).
- D2: **incident probe-harness** — lần build đầu truyền `SCP_GIT_SHA` gõ tay sai
  phần đuôi; `service_identity.commit` echo build arg nên /health 200 nhưng
  commit != pin thật → chốt commit==pin phát hiện, build lại với SHA từ
  `git rev-parse`, verify lại OK. Bài học: SHA luôn lấy từ git rev-parse.
- D3: 8/8 probe :8007 — 2×401 no-auth; 6×200 golden (stats/permissions/
  attack-mode flip/monitor/run-audit observe). run-audit observe chứng minh
  ast_scan chạy thật trong container (5 findings, bắt fixture `hello_bug.py`
  chủ đích tại 1f00d00; processed=0, 0 ghi source).
- D6: PASS_WITH_LIMITS — 3 silent except:pass đều best-effort có chủ đích
  (rollback re-raise; cache fail-open).
- D7: PASS_WITH_LIMITS — 0 TODO; thiếu header STATUS + runbook.
- D4/D5: PASS_WITH_LIMITS (seal snapshot @1f00d00; không reviewer riêng).

## Ghi chú

- Docstring v105_routes.py có mojibake UTF-8 (cosmetic, pre-existing).
- Giới hạn probe: chỉ observe mode — apply mode / tier-3 human-approval /
  LLM fix path ghi vào known_gaps (không auto-fix source trong container probe).
