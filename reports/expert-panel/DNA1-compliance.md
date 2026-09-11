# Agent DNA-1 — Compliance DNA/Skill Log

Chiến dịch compliance: FIX 1 (M12 G2 — DNA #22 violation trong product) +
FIX 2 (T00 test isolation) + land 3 file WIP stream cũ.

## Mandatory skill bindings (SHA256)

| Skill | SHA256 |
|---|---|
| `.agents/skills/scp-dna/SKILL.md` | `4aada0be4873598dc50c3a7f38d90151429bb5263c511a838ed1cdcb4d594d10` |
| `.agents/skills/scp-reality-verifier/SKILL.md` | `a9d65ce53b18f8310ceeb302b18b341a0e1b8b19cddc7f46d4fa6ee99432269e` |

DNA áp dụng: #22 (PASS ≠ TRUE — trọng tâm FIX 1), #12 (small reversible), #26 (reality authority).

## Scope

| Trường | Giá trị |
|---|---|
| Branch / base | `audit/runtime-guard-AUDIT-20260909` @ `833bc9e` |
| Thời điểm | 2026-09-12 |
| Test profile | `python -m pytest` (pytest.ini, basetemp = system temp) |
| Input | `ai_answer=""` / `ai_answer="   "` / source value `""`, single-source plan |

## FIX 1 — M12 G2: empty evidence auto-PASS (DNA #22)

- File: `scp/meta/why_execute_plan.py`, hàm `execute_plan`, nhánh single-source
  (trước fix: dòng 129-130; sau fix: khối `empty_evidence` + `elif` mới).
- Contract TRƯỚC: `if source_val and (source_val in ai_val or ai_val in source_val
  or norm_source in norm_ai or norm_ai in norm_source)` — `"" in x` vacuously True
  → `ai_answer=""` (cả `execute_pending_plans` truyền `ai_answer=''`) hoặc giá trị
  norm rỗng → tự động PASS.
- Contract SAU: `if not source_val or not ai_val:` → `UNKNOWN`, conf 0.0, reason
  `empty_evidence: ...`; nhánh match chỉ chạy khi `norm_source and norm_ai` (chặn
  `"" in x` qua đường normalize); match thật vẫn PASS 0.85.
- Lý do chọn UNKNOWN (đúng chuẩn mandate cho phép FAIL/UNKNOWN): rỗng = không thể
  xác minh, không phải mâu thuẫn — nhất quán với nhánh "no sources → UNKNOWN" ngay
  trên trong cùng hàm.
- Test: `tests/T03_capability/test_flow_12_background_why_scp_standard.py` ::
  `test_why_engine_empty_evidence_is_not_a_pass` (WHY-ENG-4) — 3 case qua đường
  product thật (local HTTP fixture + LocalDB thật), zero mock/patch, kèm control
  assert match thật vẫn PASS.

### Evidence chain

| Bước | Evidence | Kết quả |
|---|---|---|
| Repro pre-fix | `execute_plan(plan, ai_answer="")` với source "Paris" | **PASS 0.85** (violation tái hiện) |
| Post-fix | cùng input | UNKNOWN 0.0, `empty_evidence: cannot verify — ai_answer is empty/whitespace-only` |
| Post-fix whitespace | `ai_answer="   "` | UNKNOWN 0.0 |
| Control post-fix | match thật "The capital of France is Paris" | PASS 0.85 (không over-tighten) |
| Full flow_12 suite | 27 test cũ + 1 mới | **28 passed, EXIT=0** |

## FIX 2 — T00 test isolation (artifact-in-repo)

- File: `tests/T00_integrity/test_test_infrastructure_fail_closed.py`,
  `test_mutation_zero_mutants_is_error` + `test_mutation_pytest_collection_error_is_not_counted_as_kill`.
- TRƯỚC (WIP V2): target dir = `Path.cwd() / "temp_mutation_target"` — thư mục cố
  định trong repo root (artifact-in-repo, collide khi chạy song song).
- SAU: `tempfile.mkdtemp()` (system temp, ngoài repo) + `monkeypatch.chdir(target_dir)`:
  engine fail-closed (`mutation_engine._resolve_inside`) bắt buộc target VÀ test
  path phải nằm trong campaign root (resolve từ cwd), nên root của campaign chính
  là isolated temp dir; file test thật được `shutil.copy2` vào root với vai trò
  test path được tham chiếu. Mọi assertion + 2 monkeypatch seam (`generate_mutants`,
  `subprocess.run`) giữ nguyên; cleanup `finally` (+ `os.chdir(repo_root)` trước
  `rmtree` để tránh Windows cwd-lock).
- Ghi chú lệch so với mô tả mandate: mkdtemp đơn thuần (không chdir) KHÔNG chạy được
  — `_resolve_inside` raise `MutationRunError("target must stay inside repository
  root")`, mismatch với `match="no supported mutants"`. Giữ nguyên guard (không
  nới lỏng — fail-closed) và cho campaign root = temp dir là cách duy nhất thỏa
  đồng thời: ngoài repo + pass + không weaken.
- Evidence: `8 passed, EXIT=0`; không còn `temp_mutation_target*` trong repo root.

## WIP landed (stream cũ)

- Commit `b816f63` — `chore(test): land V2-stream hygiene (llm-bridge assertions
  + __main__ removals)`: `test_supervisor_child_env.py` (Ollama→llm-bridge),
  `test_flow_11_admin_import_scp_standard.py` (xóa `__main__`),
  `test_security_sweep_s6.py` (xóa `__main__`). Tests đã PASS sẵn trước khi land.

## Commits

| Commit | Nội dung |
|---|---|
| `b816f63` | chore(test): land V2-stream hygiene |
| `e05c885` | fix(T00): mutation tests use system temp instead of repo-root dirs |
| (xem git log) | fix(M12): empty evidence must not PASS + test WHY-ENG-4 + log này |

## Final pytest (mandate gate)

`python -m pytest tests/T00_integrity/test_test_infrastructure_fail_closed.py
tests/T01_boot/test_supervisor_child_env.py
tests/T03_capability/test_flow_12_background_why_scp_standard.py -q` → exit 0
(kết quả chi tiết trong report trả về coordinator).

## Limitations / Open items (DNA #23, #25)

1. **Multi-source branch vẫn có cùng class violation**: `why_execute_plan.py` dòng
   ~176 (sau fix): `if list(unique)[0] in ai_val or ai_val in list(unique)[0]` —
   `ai_val=""` → `"" in agreed` → PASS. Hành vi này đang được PIN bởi test hiện hữu
   `test_why_engine_verifies_past_decisions` (`# 2 agreeing sources, empty answer
   -> PASS`, flow_12 dòng ~447) và là đường sống của background loop
   (`execute_pending_plans` truyền `ai_answer=''`). Sửa nhánh này = đổi hành vi
   production của toàn bộ background WHY verification (mọi verdict PASS khi sources
   agree sẽ thành UNKNOWN/FAIL) + phải đổi expectation test đã pin — ngoài scope
   mandate (mandate chỉ định dòng 130 + "27+1 giữ xanh"). Cần quyết định riêng.
2. PASS_WITHIN_SCOPE: toàn bộ kết quả gắn với commit cụ thể + pytest profile ở trên;
   không mở rộng thành "product sạch hoàn toàn".
3. Không đụng GA.md, reports/circuit-closures, dashboard, mini-services (theo mandate).
