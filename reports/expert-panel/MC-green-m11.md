# MC-GREEN — M11 (Admin/Import) closure progress log

Date: 2026-09-11. Branch: `audit/runtime-guard-AUDIT-20260909`. Worker: MC-GREEN.
Pin: `8fc35604ce73dea7c9b8a8317bcdacfd67390d86` (fix commit = sha_pin).

## Guard WIP

`tests/T03_capability/test_flow_11_admin_import_scp_standard.py` là 1 trong 3
file WIP cam: chỉ CHAY suite (không đọc diff, không sửa, không commit).
D6/D7 chỉ scan 3 file product; test file bị loại khỏi scan (ghi rõ).

## PRODUCT_FAIL thật — root-cause + fix

- **Phát hiện qua D3 probe** (không phải suite): POST `/import/jsonl` với
  question hợp lệ + **judge thật** trong container →
  `errors=1, error='dict' object has no attribute 'verdict'`, HTTP 200.
- **Root cause:** import_routes.py đọc `v.verdict/v.confidence/v.evidence`
  dạng ATTRIBUTE trong khi `RealityJudge.judge()` trả dict thuần
  (judge.py:71 `-> dict[str, Any]`) → mọi question chết AttributeError →
  endpoint **không bao giờ** trả verdict. Cùng lớp bug dict-contract M10.
- **Fix `8fc3560`:** đọc dict-contract qua `.get()`; giữ fallback attribute
  CHỈ cho legacy shape — vì harness flow_11 (HEAD + WIP) mock judge trả
  MagicMock attribute-contract phát minh, và file là WIP cấm sửa.
  Sau fix: flow_11 35/35 exit 0; golden probe verdict thật (UNKNOWN +
  ESCALATE, errors=0 — fail-closed offline đúng). Rollback: revert 8fc3560.
- HANDOFF (known_gap G3): stream sở hữu test_flow_11 nên đổi mock sang
  dict-contract rồi bỏ fallback attribute trong product.

## Kết quả D1–D8

- D1: 35 passed exit 0 tại pin trước fix (4f5e1bf) VÀ tại fix pin (8fc3560).
  Caveat: suite chạy trên dirty tree có WIP file của stream khác.
- D2: build ×2 (trước/sau fix), recreate, commit == pin, readiness ready.
- D3: 8/8 probe :8010 tại fix pin — 3×401 no-auth; v98/v100 status 200;
  antibodies/check chạy thật (flagged=1, bắt "2+2=5"); import/jsonl golden
  verdict thật. 0 locked / 0 Traceback. Teardown xong.
- D6: PASS — 0 silent except:pass / 3 handler (3 product files).
- D7: PASS_WITH_LIMITS — 0 TODO; thiếu header STATUS + runbook.
- D4/D5: PASS_WITH_LIMITS — diff sau fix chưa deep scan; không reviewer riêng.
