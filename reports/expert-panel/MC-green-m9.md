# MC-GREEN — M9 (Threat & Counter) closure progress log

Date: 2026-09-11. Branch: `audit/runtime-guard-AUDIT-20260909`. Worker: MC-GREEN.
Pin: `b4134ac416c8872cb0d654fe025dc9776ce9b570` (fix commit = sha_pin).

## PRODUCT_FAIL thật — root-cause + fix

- **Phát hiện:** `tests/reality-tests/reality_4-a-003.py` FAIL (script exit 1)
  tại threat_routes.py — pre-existing được M06 ghi gap G8, thuộc scope M9.
- **Root cause:** 4 endpoint threat được wrap qua `check_admin` local có nhanh
  `if type(tr.verify_admin).__name__ == "MagicMock": return True` — test hook
  nằm trong production auth path; đồng thời drift với pattern audit
  `Depends(verify_admin)` và với chính docstring của file. Harness THREAT-5 chỉ
  hoạt động nhờ hook (mock kép: verify_admin + get_ai_scan_stats, assert số
  liệu bịa `{total_scans, threats_found}`).
- **Fix `b4134ac` (smallest reversible, 2 file):**
  - threat_routes.py: 4 decorator → `dependencies=[Depends(verify_admin)]`;
    xóa wrapper + hook; docstring ghi path thật (`/ai-scan/*`, `/harm/*` —
    router không prefix; docstring cũ khai `/v105/threats/*` không tồn tại).
  - test_flow_09: THREAT-5 de-mock (auth thật SCP_AUTH_TOKEN_SECRET + Bearer,
    pattern T02/M6; handler thật; assert contract shape) + autouse reset
    rate-limit accounting.
- **Reality test sau fix:** reality_4-a-003 PASS 3/3 (script exit 0);
  flow_09 23/23 exit 0. Rollback: revert b4134ac.

## Kết quả D1–D8

- D1: flow_09 23 passed exit 0 tại pin; reality_4-a-003 exit 0. Lưu ý:
  reality test là script-style (pytest collection = "no tests ran" exit 5,
  không phải FAIL) — evidence là script run.
- D2: build + recreate tại pin, commit == pin, readiness ready.
- D3: 8/8 probe :8009 — 4×401 auth-first (verify_admin trực tiếp sau fix),
  4×200 golden real stats. 0 locked / 0 Traceback. Teardown xong.
- D6: PASS — 0 silent except:pass / 31 handler.
- D7: PASS_WITH_LIMITS — 0 TODO; docstring drift đã sửa trong fix; thiếu
  header STATUS + runbook.
- D4/D5: PASS_WITH_LIMITS — diff sau fix chưa deep scan lại; không reviewer
  riêng.
