# S25 — T00-extension tripwire "code-cũ-lệch-thực tế"

- **Task**: Tool MỚI phát hiện TỰ ĐỘNG 4 loại code cũ/lech thực tế mà campaign 21-fix phải tìm bằng tay; wire vào `tools/t00_meta_audit.py` (add-only); test hermetic; report.
- **Worker**: S25 (no-commit). Branch không đổi.
- **HEAD lúc bắt đầu**: `b8fa536db7cc…`. **HEAD lúc kết thúc**: `1c0d0f29cfea…` — S23 commit `feat(discovery): FreeDiscoveryScheduler` trong lúc session chạy (không phải thay đổi của S25; phạm vi file của S25 không đụng vùng S23/S24).
- **Skills binding**: `scp-dna` + `scp-reality-verifier` (đã đọc; SHA256 ở cuối report).

## 1. Tool design (tools/stale_code_tripwire.py — file MỚI)

AST-based hoàn toàn (không grep ngây thơ), pathlib, 4 check fail-closed:

| # | Check | Cơ chế | FAIL khi |
|---|---|---|---|
| 1 | **Blueprint-vs-code** | `BLUEPRINT_MODULES` (hardcode có comment nguồn, xem §2) → file tồn tại trên đĩa + import probe bằng subprocess riêng (`python -c "import <mod>"`, `PYTHONPATH=root`, tên module phải khớp regex an toàn) | Module thiếu trên đĩa hoặc import lỗi |
| 2 | **Import class/module không tồn tại** | AST mọi `scp/**/*.py`: thu `from scp.X import Y` + `import scp.X` → resolve target trên đĩa (`scp/X.py` hoặc `scp/X/__init__.py`) → symbol index của target (top-level def/class/assign/ann-assign/import-bind, đi qua If/Try/With/For, tôn trọng `__all__`, re-export facade). Star-import được resolve tiếp 1 hop qua `star_sources`. | Module file không tồn tại (`missing_module`) hoặc symbol không bind được (`unresolved_import`). Dynamic (module có `__getattr__`/`importlib`/star nguồn không resolve được) → **SKIP có log**, không FAIL sai |
| 3 | **Logic trùng ≥2 bản** | (a) prompt-template literal: normalize f-string/implicit-concat (mỗi slot → `{?}`), dài >120 ký tự chứa đủ 3 marker `Question:`/`Context:`/`AI Answer:` → group theo template; (b) duplicate function body: hash `ast.dump` (docstring-stripped) của hàm >20 dòng | (a) template trùng ở ≥2 file → **FAIL** (kèm số lần xuất hiện/file); (b) → **WARN** (không FAIL để tránh ồn) |
| 4 | **Metric drift** | Đếm AST: `print()` bare-call + `except` handler body toàn `Pass` trong `scp/**` → so baseline `data/governance/tripwire_baseline.json` | Tăng >5% so baseline → FAIL. Baseline vắng → **TẠO** (schema: `schema_version`, `created_at` UTC, `git_sha`, `metrics`, `metrics_method`, `thresholds`, `known_findings`, `notes`) và PASS lần đầu. Baseline hỏng/thiếu metric → `baseline_invalid` FAIL, **không tự reset** |

**Modes**: CLI strict (mặc định, exit 1 nếu có FAIL — dùng proof-of-value/audit) + `--json`; `run_for_t00(root)` = **delta mode**: findings so fingerprint `(kind, file, detail)` với `known_findings` trong baseline — known → in `[TRIPWIRE-DEBT]` không chặn; new → violation fail-closed (same BASELINE_DEBT philosophy như FA-01/FA-04 của t00). Seed `known_findings` xảy ra đúng 1 lần lúc tạo baseline (từ findings hiện có của check 1–3).

**Wire vào t00 (add-only)**: thêm `run_stale_code_tripwire_check()` (load tool qua `spec_from_file_location`, **fail-closed**: tool crash ⇒ violation) + 1 dòng gọi trong `main()` trước verdict + 1 dòng informational print. Không sửa check cũ (2 dòng "deletion" trong diff chỉ là whitespace-trailing).

## 2. AUDIT-FIRST: nguồn blueprint list

- `scp.knowledge.warehouse` — `docs/getting_started.md` ("Knowledge warehouse with FAISS embeddings") + `.agents/skills/scp-learning-loop-guard/SKILL.md`.
- `scp.autofix.evidence_replay` — brief T00-extension + được autofix pipeline tham chiếu (`scp/autofix/engine.py`).
- `scp.meta.reverify_scheduler` — scheduler duy nhất của reverify; brief T00-extension.
- `scp.core.free_discovery_scheduler` — **tại HEAD b8fa536 tên này KHÔNG tồn tại ở bất kỳ đâu** (rg spec/ docs/ .agents/ scp/ tools/ = 0 hit) nên bị loại khỏi list; S23 build nó ở commit `1c0d0f2` (wired lifespan) → được thêm vào list với comment nguồn commit. Đây chính là hành vi mong muốn của check 1: chỉ guard module có evidence thiết kế thật.
- Không tìm thấy machine-readable blueprint list ("thiết kế phải có") trong `spec/` — `spec/scp_future_target_manifest.yaml` là *target spec tương lai*, không phải danh sách module hiện hành (read contract của nó cũng cấm suy ra implementation từ target).

## 3. KẾT QUẢ CHẠY THẬT TRÊN REPO (proof-of-value — quan trọng nhất)

Chạy: `python tools/stale_code_tripwire.py` (strict) tại HEAD `1c0d0f29cfea`, baseline vừa được tạo trong cùng lần chạy:

```
Check 1 blueprint-vs-code : 0 FAIL(s)          # 4/4 module tồn tại + import được
Check 2 unresolved import : 6 FAIL(s), 169 SKIP(s)
Check 3 duplicated logic  : 1 FAIL(s), 19 WARN(s)
Check 4 metric drift      : 0 FAIL(s)          # baseline created: print=836, silent_except=6
```

**Check 2 — 6/6 findings đã đối chiếu thủ công, đều TRUE POSITIVE:**

| Finding | Đối chiếu thực tế |
|---|---|
| `scp/api/routes/v105_routes.py:719: from scp.rag.canonical_retriever import HybridRetriever` | `canonical_retriever.py` chỉ có `CanonicalRetriever` — **đúng bug mục tiêu của brief** |
| `scp/ask_kernel_adapter.py:687: from scp.core.exception_policy import observe_nonfatal` | `scp/core/exception_policy.py` **không tồn tại** — nhánh observe Nonfatal chết lặng trong `try/except` (bug mới, ngoài HybridRetriever) |
| `scp/api/routes/admin_v100.py:164: from scp.release.evidence_authority import ReleaseEvidenceAuthority` | file chỉ có `class EvidenceAuthority` — sai tên class |
| `scp/autofix/engine.py:408: from scp.core.code_evolution_agent import _relative_repo_path` | `_relative_repo_path` là **method** của `CodeEvolutionAgent`, không phải module-level function |
| `scp/meta/reverify_scheduler.py:293: from scp.runtime.engine import RealityJudge` | `RealityJudge` nằm ở `scp/runtime/judge.py:61`, không phải `engine.py` |
| `scp/runtime/engine_parts/scpv14_process_mixin.py:76: from scp.runtime.judge import JudgeVerdict` | `JudgeVerdict` nằm ở `scp/runtime/judge_parts/types.py`, không phải `judge.py` |

⇒ Tripwire bắt được **6 latent-ImportError** trong đó 5 là phát hiện mới ngoài mục tiêu HybridRetriever — đây là bằng chứng giá trị trực tiếp (level A static, chưa chứng minh runtime path nào thực sự chạy vào — xem Limitations).

**Check 3 — bắt đúng 3 bản judge prompt**: `duplicate_prompt_template` — "3 occurrences in 2 files; sha256:dfea35babb98 → scp/runtime/judge_llm.py x2, scp/runtime/multi_llm_crosscheck.py x1" (khớp kỳ vọng brief). Kèm 19 WARN duplicate function body (cụm `runtime/experts/*` vs `slm_impls/*` — pattern copy-paste rõ, chỉ WARN).

**Check 4**: baseline đầu tiên ghi `{'print_calls': 836, 'silent_except_pass': 6}` @ git `1c0d0f29cfea`. Ghi chú phương pháp: 836 là số AST `Call(Name print)`; con số 858 trong brief là đếm text `rg "print\("` (bắt thêm attribute call/chữ trong string) — method được ghi trong baseline để so sánh nhất quán.

**SKIP có log**: 169 (relative import ngoài scope + target dynamic) — fail-open có kiểm soát đúng thiết kế.

## 4. Kết quả verify (reality checks)

| Lệnh | Kết quả |
|---|---|
| `python -m pytest tests/T00_integrity/test_stale_code_tripwire.py -q` | **12 passed** (case a–f theo brief + g dynamic-SKIP, h delta-mode known-vs-new, i t00-wiring, j drift-trong-ngưỡng, k star-facade resolve, l baseline hỏng fail-closed không bị ghi đè) |
| `python -m pytest tests/T00_integrity/ -q` | **84 passed** (74 cũ + 12 mới + …; chạy lại sau commit S23) |
| `python tools/t00_meta_audit.py` | **exit 0** — tripwire chạy bên trong (SKIP log + 7 dòng `[TRIPWIRE-DEBT]` trong BASELINE_DEBT phase), 0 new regression, không làm đỏ hiện trạng |
| `python tools/verify_scp_test_skill_contract.py` | **exit 0**, `status: PASS_WITHIN_SCOPE` |
| Chạy lần 2 của t00 | exit 0, không seed lại, debt ổn định (delta mode idempotent) |

Bug process đáng chú ý mà test bắt được: module load qua `spec_from_file_location` mà không đăng ký `sys.modules` làm `@dataclass` crash (`AttributeError` trong dataclasses) — đã sửa ở cả test harness và t00 wiring (register trước `exec_module`). Không có skip/xfail mới; không hạ chuẩn.

## 5. File changed (no-commit — commit do orchestrator)

```
 tools/t00_meta_audit.py | 36 ++++++++++++++++++++++++++++++++++--
 1 file changed, 34 insertions(+), 2 deletions(-)   # 2 deletion = whitespace-trailing
```
File MỚI (untracked):
- `tools/stale_code_tripwire.py` (tool 4 check)
- `tests/T00_integrity/test_stale_code_tripwire.py` (12 test hermetic, tmp-tree fixture)
- `data/governance/tripwire_baseline.json` (baseline lần đầu — **bị `.gitignore:26 **/data/` bỏ qua**; nếu orchestrator muốn version nó: `git add -f data/governance/tripwire_baseline.json`; nếu không, mỗi môi trường mới tự tạo baseline lần đầu rồi so từ đó)
- `reports/expert-panel/S25-t00-tripwire.md` (file này)

Không đụng bất kỳ file nào của S23/S24.

## 6. Limitations (DNA #22/#23 — còn mở)

- Bằng chứng là **static (level A)** + integration ở mức tool-within-t00. 6 import lỗi chưa được chứng minh bằng runtime path nào thực sự hit (một số nằm trong `try/except ImportError` hoặc module không được import ở boot) — "code-cũ-lệch" có thật, mức độ nghiêm trọng runtime cần triage riêng.
- 169 SKIP (relative import ngoài scope, dynamic provider) = mù cố ý để tránh FAIL sai; blind-spot chung của check 2.
- Check 3 WARN chỉ so `ast.dump` normalized — hai bản duplicate đã bị sửa nhẹ (đổi tên biến) sẽ không bị bắt.
- Baseline bị gitignore ⇒ không cứng trên CI/máy khác; nếu ai xóa file baseline, lần chạy sau sẽ tạo lại (logged với git SHA) — không fail-open trên drift cũ, nhưng lịch sử debt sẽ được re-seed từ hiện trạng.
- Fingerprint known-findings không chứa git SHA — một finding đã-seed được fix rồi tái phạm sẽ tiếp tục bị coi là debt (không re-FAIL). Đây là đánh đổi để tránh ghi baseline trong lúc chạy (race với worker song song).
- `python tools/t00_meta_audit.py` hiện in cảnh báo `[L4] tools/t00_meta_audit.py` — pre-existing behavior cho protected path, do chính wire-point này; GitHub server-side ruleset mới là authority.
- Mimosa de-shape: tool chỉ dùng AST/pathlib/json; subprocess duy nhất = `git rev-parse` + import probe với tên module khớp regex `^[A-Za-z_][\w.]*$`; không network, không eval/exec, không tainted sink.
- Không in secret; không skip/xfail; không đổi branch.

## 7. Verdict

`PASS_WITHIN_SCOPE` — tripwire hoạt động đúng thiết kế trong phạm vi đã test: 4 check fail-closed, chạy thật trên repo bắt được **6 unresolved/missing import (đã đối chiếu từng cái) + 3 bản judge prompt trùng**, t00 giữ exit 0 với debt được track. Không claim hệ thống sạch/production-ready.

---

## SHA256 append (skill binding + artifacts, AGENTS.md contract)

```
git HEAD (khi chạy cuối): 1c0d0f29cfea0b712f0c7d233d698aed042c4084
4aada0be4873598dc50c3a7f38d90151429bb5263c511a838ed1cdcb4d594d10  .agents/skills/scp-dna/SKILL.md
a9d65ce53b18f8310ceeb302b18b341a0e1b8b19cddc7f46d4fa6ee99432269e  .agents/skills/scp-reality-verifier/SKILL.md
9484c80e8a2b1344b8ba251b140549363b9711512e02bab357c354d93666d7fa  tools/stale_code_tripwire.py
3c350c1161eb134274641cef7b17c5f5f56ff21fd777b0f3af2275b8ac2406ed  tools/t00_meta_audit.py
88ca0b34e24d3ab810126043f70719d28f7c3386d852af78d15976b90458de4e  tests/T00_integrity/test_stale_code_tripwire.py
3f0c9f5f1dabd21131b3bec2d338cef350b5db7514f06d8aba1d1459e00adce6  data/governance/tripwire_baseline.json
```
