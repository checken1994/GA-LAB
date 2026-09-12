# SCP Reality Verification — S-B1c fail-loudly (lô CUỐI, còn lại của scp/)

## Claim

Toàn bộ silent `except` trong phần còn lại của `scp/` (ngoại trừ `core/`, `meta/`,
`autofix/`, `runtime/` — đã xong bởi S-B1a/S-B1b — và `scp/tests/` out-of-scope)
được sửa fail-loudly bằng log-only insert, KHÔNG đổi behavior; pytest baseline
không suy giảm; census cuối = 0 SILENT in-scope.

## Scope

| Trường | Giá trị |
|---|---|
| Branch | `audit/runtime-guard-AUDIT-20260909` |
| Commit đầu S-B1c | `554bba2` (tiếp sau `7949b7f` của S-B1b) |
| Commit cuối (snapshot) | `0dc578f` |
| Test profile | `tests/T02_contract/` + `test_flow_09_threat_analysis_scp_standard.py` + `test_flow_13_free_api_learning_scp_standard.py` (pytest -q) |
| Thời điểm | 2026-09-12 |
| Skill DNA | `4aada0be4873598dc50c3a7f38d90151429bb5263c511a838ed1cdcb4d594d10` (.agents/skills/scp-dna/SKILL.md) |
| Skill Reality Verifier | `a9d65ce53b18f8310ceeb302b18b341a0e1b8b19cddc7f46d4fa6ee99432269e` (.agents/skills/scp-reality-verifier/SKILL.md) |

## Census (scripts/diagnostics/census_silent_except.py, scope override S-B1c)

Scopes: security, knowledge, api, api_server_parts, hands, pc_control,
web_control, world_state, risk_intelligence, governance, foundation,
persistence, benchmark, brain, self_model, audit_engine, consolidator,
prediction, learning + root `scp/*.py`. Dedup theo (file, line) — census thô
2718 bị double-count do scope `scp/` rglob chồng scope con; baseline/final
dưới đây là số DEDUP.

| Trạng thái | Baseline | Final |
|---|---:|---:|
| Handlers (dedup) | 2266 | 2266 |
| OK (has log/raise) | 1945 | 2117 |
| INTENTIONAL (silent-by-design) | 142 | 142 |
| SILENT in-scope | 172 | **0** |
| SILENT scp/tests (out-of-scope) | 7 | 7 |

Delta OK = +172 = đúng số handler đã fix. Baseline JSON:
`reports/expert-panel/S-B1c-census-baseline.json`; final snapshot:
`reports/expert-panel/S-B1c-census-final.json`.

## Fix pattern (commit per-module)

- Log-only insert làm FIRST statement của handler: `logger.warning` cho
  bare/`Exception`/`BaseException`; `logger.debug` cho narrow expected types
  (fallback có chủ ý). Handler chưa gán tên dùng `exc_info=True`.
- File thiếu logger → inject `import logging` + `logger = logging.getLogger(__name__)`
  sau import block cuối (module-level).
- Không re-raise (tránh đổi behavior — rollback/security path giữ nguyên control flow).
- Tool: `scripts/diagnostics/fix_silent_except_sb1c.py` (giữ nguyên EOL CRLF/LF,
  rewrite one-liner `except X: pass`, idempotent theo census JSON).

## Evidence chain — commits

| Module | SILENT fix | Files | Commit |
|---|---:|---:|---|
| tool fixer | — | 1 | `554bba2` (+ regex fix `0dc578f`) |
| scp/rag | 1 | 1 | `546e299` |
| scp/world_state | 1 | 1 | `57522ea` |
| scp/security | 44 | 19 | `b168817` |
| scp/hands | 24 | 5 | `ebb89f3` |
| scp/benchmark | 17 | 9 | `d0dbaa7` |
| scp/api (routes log-only, shape giữ nguyên) | 14 | 5 | `fcdb043` |
| scp root (api_server, ask_kernel_adapter, kernel_storage, __main__) | 13 | 4 | `5d76781` |
| scp/llm_gateway | 11 | 4 | `e53689c` |
| scp/data_sources | 7 | 7 | `a537c26` |
| scp/api_server_parts (_ask_impl, M2 shape untouched) | 5 | 1 | `05eeb15` |
| scp/knowledge | 4 | 4 | `1302dc1` |
| scp/pc_control | 3 | 1 | `b42c046` |
| scp/foundation | 3 | 1 | `e8c2ccb` |
| scp/brain | 3 | 1 | `3b93099` |
| scp/experience | 3 | 1 | `43dbc50` |
| scp/history | 3 | 1 | `abe190a` |
| scp/observability | 3 | 1 | `4c3016a` |
| scp/web_control | 2 | 2 | `6536e0b` |
| scp/governance | 2 | 1 | `8e1b378` |
| scp/self_model | 2 | 1 | `ecf7028` |
| scp/capabilities | 2 | 1 | `d551b71` |
| scp/consolidator | 1 | 1 | `11d74a6` |
| scp/learning | 1 | 1 | `1661c3e` |
| scp/calibration | 1 | 1 | `f05f5ad` |
| scp/forecast | 1 | 1 | `5139112` |
| scp/release | 1 | 1 | `fe163bd` |
| **Tổng** | **172** | **76** (+2 tool) | |

## Postconditions

| Điều kiện | Quan sát | Verdict |
|---|---|---|
| py_compile từng file đã fix | PASS toàn bộ (per-module + chốt) | VERIFIED |
| Import runtime từng module đã fix | PASS 60+ module (dummy `SCP_CAPABILITY_SECRET` chỉ cho smoke-import — secret thật không bị chạm tới) | VERIFIED |
| pytest baseline TRƯỚC | `205 passed in 41.96s`, EXIT=0 (run thật, DNA #26) | VERIFIED |
| pytest SAU (commit cuối) | `205 passed in 38.11s`, EXIT=0 — fail không tăng | VERIFIED |
| Census cuối SILENT in-scope | 0 (dedup) | VERIFIED |
| Behavior không đổi | diff chỉ thêm log lines / thay `pass`; không đổi return/raise/status code/shape | VERIFIED (static, scope diff) |
| L3 token shape sạch | không thêm token shape vào comment; log strings chỉ `%s`/exc_info | VERIFIED (static) |

## Limitations

- Kiểm chứng là static + integration-level (import/compile/pytest profile hẹp);
  KHÔNG phải end-to-end runtime proof cho mọi code path đã thêm log (cấp B,
  không tự nâng cấp lên C).
- `scp/tests/` còn 7 SILENT — out-of-scope theo ràng buộc task.
- Handler trùng logic-log có sẵn nhưng không khớp shape census
  (vd `logging.getLogger(...).warning(...)` inline) được census đánh SILENT và
  nay dùng logger module-level — hành vi log tương đương.
- Level warning/debug là heuristic theo loại exception; review người vẫn nên
  scan nhanh các `warning` mới trong `scp/security/` (44 handler) nếu muốn
  nâng một số lên re-raise cho rollback path.
- pytest output có noise `ValueError: I/O operation on closed file` từ
  OpenTelemetry ConsoleSpanExporter thread — có từ baseline TRƯỚC mọi thay đổi
  của S-B1c, không ảnh hưởng exit code hay kết quả pass.

## Final verdict

`VERIFIED_WITHIN_SCOPE`: 172/172 SILENT in-scope đã fail-loudly, 0 regression
trên test profile, census cuối = 0. Không claim "toàn hệ thống sạch silent
except" ngoài scope đã nêu (core/meta/autofix/runtime là scope của S-B1a/S-B1b;
scp/tests còn 7).
