# S15 — CI Green cho PR #40 (audit/runtime-guard-AUDIT-20260909 → main)

## Claim
Đưa PR #40 qua required checks GitHub (ubuntu-latest, `SCP_EGRESS_MODE=deny`):
15 test fail trên CI được root-cause + fix đúng điểm, không hạ chuẩn (không
delete/skip/xfail trái phép, không hạ assertion, không fail-open).

## Scope
| Trường | Giá trị |
|---|---|
| Base commit/snapshot | 9b357916c43ace92c55a5c175e24c40f491cc88c (nhánh `audit/runtime-guard-AUDIT-20260909`) |
| Skill binding | scp-dna SHA256 `4aada0be4873598dc50c3a7f38d90151429bb5263c511a838ed1cdcb4d594d10`; scp-reality-verifier SHA256 `a9d65ce53b18f8310ceeb302b18b341a0e1b8b19cddc7f46d4fa6ee99432269e` |
| Test profile | `pytest -q -p no:cacheprovider tests/ scp/tests/` (đúng lệnh `scripts/enforce_baseline.py`) |
| Env mô phỏng CI | `SCP_JWT_SECRET/SCP_ADMIN_KEY` (giá trị CI), `SCP_PRODUCTION_MODE=0`, `SCP_SKIP_STARTUP_GATE=0`, `SCP_EGRESS_MODE=deny`, `PYTHONUTF8=1`, Python 3.12 |
| Thời điểm | 2026-09-12 |

## Root cause + fix theo nhóm

| # | Nhóm (CI fail) | Root cause | Fix (file:line) |
|---|---|---|---|
| 1 | `test_flow_04::test_web_browse_requires_token` — `EgressDeniedError` | EE-G1 thêm `enforce_egress_policy` trước I/O trong `browse_public`; deny mode chặn `https://example.com` là CONTRACT ĐÚNG, test cũ kỳ vọng browse luôn chạy | `tests/T03_capability/test_flow_04_control_hands_scp_standard.py:422` — mode-aware: dùng chính `enforce_egress_policy` làm oracle; deny → assert raise `EgressDeniedError` (strict hơn); không deny → giữ 200/503 |
| 2 | `test_pc_controller_*` ×3 — `powershell.exe` không tồn tại trên Linux | Executor của PCController là `powershell.exe` (Windows-only by design); Linux trả `success=False` | OS-conditional skip theo T00 rule (a) (`platform.system()`): `test_pc_controller_token_pep.py:98,340`; `test_flow_04_...py:152` — leg 403 PEP vẫn assert mọi OS, chỉ leg 200 thực-thật là Windows-conditional |
| 3 | `test_flow_14`/`test_flow_19` audit_engine — "directory should exist" / import fail | `git ls-files scp/audit_engine/` = 0 file: package **chưa từng được commit** trên main/PR branch (source chỉ tồn tại ở commit lạc nhánh 4772cbd). Local Windows "xanh" chỉ nhờ namespace package + `__pycache__` stale; CI checkout sạch không có thư mục | Restore 8 file từ 4772cbd (không APIRouter/background-job, pass REINT-14 isolation) + `scp/audit_engine/__init__.py` mới (docstring isolation contract). 81 passed (flow_14 + flow_19 + deadzone) |
| 4 | `test_playwright_backend::test_backend_status_and_lifecycle_contract` — playwright not importable | `start()` import playwright; test này không nhận fixture `chromium_ready` như các test browser khác | Gắn fixture `chromium_ready` (declared infra-skip theo entry allowlist sẵn có của file; không cần sửa JSON) `tests/T03_capability/test_playwright_backend.py:172` |
| 5 | `test_security_sweep_s4` ×2 — `no attribute '_safe_output_path'` | Repo có 2 runner benchmark: root `benchmark/` (có guard S4) và `scp/benchmark/` wrapper (KHÔNG có guard). Trên CI `import benchmark.run_benchmark_v2` resolve về wrapper → AttributeError | Thêm `_safe_output_path` vào `scp/benchmark/run_benchmark_v2.py:55` (cùng semantics: reject traversal + boundary repo-tree) — harden wrapper, contract giữ nguyên ở cả 2 resolution |
| 6 | `test_llm_egress_policy` + `test_provider_failover` ×2 — `None == 'ok'/'deepseek answers'/'waiting_free_quota'` | 2 lớp policy mâu thuẫn: LLM gate đọc `SCP_LLM_EGRESS_ALLOWLIST` (pass) nhưng generic EE-G1 gate đọc `SCP_EGRESS_ALLOWLIST` (deny) trên cùng request | `scp/security/url_safety.py:97` — `enforce_egress_policy(..., extra_allowed_hosts=None)`: chỉ WIDEN nhánh allowlist cho call-site truyền vào; deny mode vẫn fail-closed toàn bộ non-loopback. `scp/llm_gateway/client.py:348` truyền LLM allowlist; `scp/llm_gateway/egress_policy.py:34` helper `llm_egress_allowlist_hosts()` |
| 7 | `test_autofix_shadow_rollback` ×2 — is_ok=True khi pytest gate crash/regression | Pytest gate trong `_verify_fix` **skip silent** khi target nằm ngoài repo tree (tmp workspace): walk-up không thấy `tests/` → fail-OPEN, mâu thuẫn contract fail-closed mà test pin | `scp/autofix/engine_parts/verify_mixin.py:211` — khi không tìm thấy tests-root, gate vẫn chạy pytest trên chính file được patch (fallback như case "no targets"); crash → `pytest verify error (fail-closed)`, regression → ROLLBACK. 12 passed |
| 8 | `test_golden_b_verified_fix_commits_to_durable_state` — base phase "module import failed: ValueError" | `_try_import_module` dùng `Path(file).relative_to(_SCP_ROOT.parent)` → **ValueError** cho file patch trong tmp workspace (ngoài repo tree) → base phase UNVERIFIED → rollback mọi generic fix | `scp/autofix/runner_phases/post_fix_verify.py:66` — file ngoài repo tree → import via `spec_from_file_location` với tên throwaway (compile+exec thật, dọn sys.modules). 4 passed. KHÔNG OS-specific — tái hiện y hệt message CI trên Windows |
| 9 | `test_security.py::test_webnavigator_revalidates_private_redirect...` — regex not matched | EE-G1 gate raise ở hop ĐẦU (public URL) dưới deny, che mất redirect-revalidation mà test pin | Harness fix: test chạy dưới allowlist tường minh hẹp (`SCP_EGRESS_ALLOWLIST=public.example.test`) — egress policy vẫn active, redirect leg tới loopback bị `validate_url` từ chối → regex vẫn bắt private-redirect. `scp/tests/external_audit/test_security.py:258` |
| 10 | T00 no-skip gate ×2 (pre-existing trên HEAD, không thuộc danh sách 15 nhưng chặn green) | `test_egress_enforcement.py` có 4 `pytest.skip("docker not available"/"image not built")` chưa declared (policy A) | Khai báo policy A: entry mới trong `tests/T00_integrity/declared_infra_skips.json` (env_guard `SCP_EE_CONTAINER_TESTS`, patterns khớp reason thật) + cập nhật pin `test_meta_audit.py::_KNOWN_DECLARED_INFRA_SKIP_COUNTS` (7→8 files) |

## Mô phỏng CI env + kết quả

1. **Venv sạch** (chỉ `scp/requirements-dev.txt`, không playwright/global extras):
   - `pip check` → "No broken requirements found" (exit 0) → startup fail KHÔNG phải dependency conflict.
2. **Full suite mô phỏng CI** (venv sạch + env đúng ci.yml + `SCP_EGRESS_MODE=deny`):
   `pytest -q -p no:cacheprovider tests/ scp/tests/` → **1502 passed, 32 skipped, 0 failed (3:51), exit 0**.
   32 skips = declared infra-skips (playwright absent, docker opt-in, PG DSN unset).
3. **Before/after theo nhóm** (deny env, trước fix): flow_04 1F; gateway 3F; autofix 2F; golden_b 1F; external_audit 1F; T00 2F (pre-existing); audit_engine 2F trên fresh checkout. Sau fix: toàn bộ xanh.

## CI Baseline (ci.yml, non-authoritative) — chẩn đoán startup

- Workflow tham chiếu `scripts/enforce_baseline.py` + `scp/requirements-dev.txt`: **cả hai tồn tại** tại HEAD; pip check sạch trên venv tươi → không thấy lỗi "file không tồn tại" hay dependency conflict.
- `enforce_baseline.py` chạy FULL suite với `timeout=900`; suite có 15 fail (trước fix) → exit 1 "baseline is broken" trên MỌI push kể cả docs-only. Sau fix, mô phỏng local full suite exit 0 trong ~4 phút (dưới timeout 15 phút).
- Không truy được log GitHub từ máy local; nếu Baseline vẫn đỏ sau PR này với thời lượng ~giây thì cần log thực để phân biệt (các step checkout/setup-python không phụ thuộc repo content).

## Commit per-group
Xem git log của PR (mỗi nhóm 1 commit, ghi rõ file:line trong message).

## Open questions / giới hạn bằng chứng (PASS_WITHIN_SCOPE)

1. **`scp/autofix/evidence_replay.py` là STUB**: `EvidenceReplay.verify()` luôn trả `{"ok": True, "status": "VERIFIED"}`, `classify_evidence()` trả "mock reason", `compute_bug_signature()` trả "mock_signature". Chân "verified fix commits to durable state" của golden B hiện được promote bởi verifier mô phỏng khi `SCP_SEED_GOLD_EVIDENCE=1` (env chỉ set trong test). Rủi ro FA-04 (simulated VERIFIED) — cần task riêng xây evidence-replay thật trước khi coi commit-leg là proven.
2. "semantic_equiv: no backup file — skipped (fail-open per DNA #7)" vẫn xảy ra: backup semantic không được ghi tại apply-time (đã nêu trong message PRODUCT_BLOCKED cũ của test). Không chặn green nhưng là gap thật.
3. Không tái hiện được local: cơ chế chính xác khiến `import benchmark` resolve về `scp/benchmark` trên Linux (regular package thắng namespace portion khi inner `scp/` vào sys.path). Fix Group E cho đúng ở CẢ HAI resolution nên không phụ thuộc cơ chế này; nhưng cần CI run thật để confirm.
4. Linux-only behavior (powershell vắng mặt, case-sensitive fs) không chạy được trên Windows — được bọc bằng OS-conditional/restore-from-git, nhưng lần CI đầu tiên cần xem lại log.
5. `pytest-timeout` không có trong requirements-dev nhưng gate autofix truyền `--timeout=60` (exit 4 → được xử lý như pass-through). Không ảnh hưởng green nhưng nên thêm dep hoặc bỏ flag trong task sau.
