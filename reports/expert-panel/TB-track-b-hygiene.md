# TB Track B Hygiene Record (B2 + skill bindings)

- Agent: TB (Track B nhanh: B2 + B4 + B5)
- Repo: `C:\Users\check\Downloads\scp`, branch `audit/runtime-guard-AUDIT-20260909`
- Ngày: 2026-09-12

## Mandatory skill bindings (SHA256)

| Skill | Path | SHA256 |
|---|---|---|
| scp-dna | `.agents/skills/scp-dna/SKILL.md` | `4aada0be4873598dc50c3a7f38d90151429bb5263c511a838ed1cdcb4d594d10` |
| scp-reality-verifier | `.agents/skills/scp-reality-verifier/SKILL.md` | `a9d65ce53b18f8310ceeb302b18b341a0e1b8b19cddc7f46d4fa6ee99432269e` |

## B2 — Dead/artifact cleanup decisions (audit-first)

### 1. `scp/api/_lifespan.py` (764 LOC) → DELETED

Evidence tìm được (grep `api._lifespan`, `import.*_lifespan`, `_lifespan` trên `scp/ tests/ tools/`):

- **Không có import Python thật** của `scp.api._lifespan` ở bất kỳ đâu trong
  `scp/`, `tests/`, `tools/`. Các hit `from scp.api import ...` đều là
  `_shared`/`chat`, không phải `_lifespan`.
- `scp/api_server.py:38` import `scp.api_server_parts.lifespan` (lifespan THẬT
  được bind vào app) — KHÔNG phải `api/_lifespan.py`.
- `scp/tests/external_audit/test_security.py:29`: `API_LIFESPAN = SCP_ROOT /
  "api_server_parts" / "lifespan.py"` — test cũng trỏ vào file thật.
- `tests/T01_boot/test_flow_01_boot_background_scp_standard.py`: chỉ nhắc tên
  file trong docstring/history (dòng 3, 80-81, 125 — "the dead module",
  "used to exist"), không import.
- `scp/autofix/runner_phases/ast_scan.py:56`: path trong `PROTECTED_PATHS` —
  GIỮ NGUYÊN làm tombstone (ngăn autofix tự tái tạo file tại path này; xóa
  entry sẽ là giảm diện bảo vệ, trái DNA #7/#9). Không phải caller thật.
- Comments TODO ở `scp/security/escalation.py:438`,
  `scp/knowledge/domain_store.py:370`, `scp/meta/external_trust.py:226` gọi
  `_lifespan.py` là owner — đã cập nhật trỏ sang
  `scp/api_server_parts/lifespan.py` (file thật) để TODO không treo vào file đã xóa.

Verdict: dead code, không caller thật → XÓA. Test T01 boot: 27 passed sau xóa.

### 2. `scp/hello_bug.py` → GIỮ tại path + thêm header canary

- `rg -l "hello_bug"`: không có tham chiếu nào trong code/tests — probe M7 là
  runtime/dynamic (ast_scan quét scp/).
- M07 closure pin theo path: `reports/circuit-closures/M07-closure.json`
  (`scp/hello_bug.py`, probe commit `1f00d00`) + evidence
  `reports/circuit-closures/M07-evidence/D3-m7-probe.txt`. Move sang
  `tests/fixtures/` làm gãy khả năng tái hiện closure M07 → chọn phương án an
  toàn hơn: thêm header `INTENTIONAL CANARY FIXTURE — DO NOT FIX, DO NOT MOVE,
  DO NOT DELETE.`
- Reality test sau sửa: `_scan_file(Path('scp/hello_bug.py'))` vẫn trả về
  finding `PossiblyUndefinedName` (line 7 sau khi thêm header) → probe M7 vẫn
  hoạt động. CANARY OK.

### 3. `scp/core/smart_classifier.py.tier3bak` → DELETED

- Legacy single-backup của pre-R8-5 rollback. Fallback legacy trong
  `scp/api/routes/v105_routes.py:595` chỉ có nghĩa khi tồn tại audit-log entry
  cho file đó: grep `smart_classifier` trong `data/autofix_audit.jsonl` +
  `data/tier3_auto_audit.jsonl` → 0 entry, mọi `rollback_token` là `"n/a"` →
  fallback không bao giờ dùng được cho file này.
- "Clean Workspace mandate: zero .tier3bak files left in the source tree"
  (`tests/T07_learning/test_autofix_shadow_rollback.py` item 7) ủng hộ việc xóa.
- Git history giữ nguyên bản (`git rm`). Grep lại `find scp/ -name "*.tier3bak"`
  → 0 file còn lại (chỉ còn logic `.tier3bak.{token}` trong v105_routes.py).

## Reality checks

- `python -m pytest tests/T01_boot/test_flow_01_boot_background_scp_standard.py -q`
  → **27 passed in 8.52s**.
- `python -m pytest scp/tests/external_audit/test_security.py -q` → 1 failed,
  8 passed, 2 skipped; failure `test_pc_read_only_allowlist_rejects_command_chains`
  do thiếu env `SCP_CAPABILITY_SECRET` — tái hiện y nguyên trên HEAD sạch
  (git stash → cùng kết quả) → **pre-existing, không do B2**.

## Scope limits

- B2 chỉ xóa/relocate dead code + fixture canary; không đụng GA.md,
  circuit-closures, dashboard/, mini-services/, my_fixes.patch,
  PROMPT_INJECTION_GAP_REPORT.md, .hypothesis, .mimosa.
- PASS = không thấy failure trong scope test đã nêu; không claim rộng hơn.
