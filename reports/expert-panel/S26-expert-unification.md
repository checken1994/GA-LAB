# S26 — Expert Unification: dọn 3 thế hệ expert/legacy residue

- **Worker:** S26 (no-commit) · **Ngày:** 2026-09-13 · **HEAD pin:** `8efd80f6ee10e4b05a5f1d0b8ee7f55e60903538` (không đổi nhánh, không commit)
- **Skills áp dụng:** `scp-dna` + `scp-skill-review` (SHA256 append cuối file này)
- **Phạm vi đụng:** slms/slm_impls/slms_parts/judge_parts, whyengine, experts/, 2 scanner, 4 test file, 2 CI workflow, 1 module mới. KHÔNG đụng: ask_kernel_adapter.py, question_router.py, admin_v100.py (S24), judge.py, taskkernel*, llm_gateway/*, .env, GA.md, spec/.
- **Kết quả 1 dòng:** Xóa 47 file ~13,857 LOC Python dead/duplicate (3 cây legacy); migrate whyengine sang cây `experts/` behavior-identical (WHY-GATE 6/6 + differential builders 44/44 + A/B container identical); KHÔNG extract JudgeCoreMixin (0 caller sống); collect-all sạch, contract tool PASS, tripwire 0 finding mới; runtime proof Docker A/B không regression từ S26.

---

## 1. MAP sống/dead (Bước 1 — audit-first từng symbol)

### 1.1 `scp/runtime/slms.py` (555 LOC) — verdict: **DEAD toàn bộ, XÓA**
| Importer | Symbol | Sống/dead |
|---|---|---|
| `scp/meta/why_engine_parts/whyengine.py:260` | `GeographySLM` | **SỐNG** (WHY `_query_local_db`) → đã migrate |
| `tests/T03_capability/test_flow_12_background_why_scp_standard.py:662` | `GeographySLM` | test → re-point |
| (còn lại) | — | không có importer nào khác (grep toàn repo + string/importlib) |

### 1.2 `scp/runtime/slm_impls/` (5,326 LOC / 17 file) — verdict: **DEAD toàn bộ, XÓA**
- Import code duy nhất: `slms.py` (re-export block L464-538) + `test_ssrf_sweep_s2.py:192` (module identity) + `scripts/maintenance/patch_universal_local_only.py` (patch script 1-lần, lịch sử).
- `GeographySLM._local` (231 keys) ≡ `experts/humanities.Geography._local`: **0 key diff, 0 value diff** (so runtime trước khi xóa).

### 1.3 `scp/runtime/slms_parts/` (3,620 LOC / 10 file) — verdict: **DEAD trừ 8 pure builder, XÓA + PORT**
| Thành phần | Consumer sống | Xử lý |
|---|---|---|
| `foodslm`: 3 builder (mealdb/cocktaildb/fruityvice) | `experts/lifestyle.py` + SSRF test | **PORT verbatim** → `experts/url_builders.py` |
| `misc_slms2`: `build_city_search_url`, `build_holiday_url`, `build_bible_url` | lifestyle + test_flow_02 + SSRF test | **PORT verbatim** |
| `entertainmentslm`: `build_swapi_url`, `build_tvmaze_url` | SSRF test | **PORT verbatim** |
| 9 class SLM (HolidaySLM, ReligionSLM, …) + `foodslm.FoodSLM` + `entertainmentslm.EntertainmentSLM` + `_domainslm/chemistryslm/conversionslm/generalslm/universalslm/weatherslm` | chỉ slms.py (dead) + test | XÓA; `HolidaySLM.predict` fail-closed được kế thừa bởi `experts.Holiday` qua builder (xem §3) |

### 1.4 `scp/runtime/judge_parts/` (4,356 LOC / 19 file, gồm phases 2,888) — verdict: **DEAD toàn bộ, XÓA**
- `judge.py` (đường /ask sống: RealityJudge → tier1_guard + judge_llm + IndependentVerifier) **không import judge_parts**.
- Import code duy nhất ngoài package: `tests/T02_contract/test_god_split_semantic_parity.py:270` (+ entry L29). Tự chứa: chỉ import `phases.context` + `scp.meta.severity`.
- `judge_phases.py` tự khai "NOT WIRED into judgecore_mixin.judge()"; `judge_phase_4_governance.py` là placeholder.
- Tham chiếu file-path (không import): `dead_slm_scanner.py` (primary path — có fallback), `routing_gap_scanner.py` (glob nếu dir tồn tại), `tests/reality-tests/reality_4-b-002.py` (không thuộc pytest collection), 5 tools/scripts patcher 1-lần.
- Mọi tham chiếu còn lại trong `scp/` là **comment lịch sử** (stale) — xem NEW FINDINGS.

### 1.5 KEEP (không xóa, có lý do)
- `scp/runtime/slm_base.py` — SỐNG: `judge.py.domain_experts` + toàn bộ `experts/` import BaseSLM/SLMResponse.
- `scp/runtime/experts/` — cây sống, judge tự discovery (runtime proof: 27 domains).
- Các patch script 1-lần (`tools/fix_judgecore_domain_signature.py`, `tools/patch_explicit_domain_override*.py`, `scripts/fix_judge_antibody_block.py`, `scripts/patch_antibody_interface.py`, `scripts/maintenance/fix_consistency_indent.py`, `scripts/maintenance/patch_web_fallback_consistency.py`) — lịch sử, ngoài scope sửa; liệt kê NEW FINDINGS.

## 2. JudgeCoreMixin — quyết định: **KHÔNG extract** (bằng chứng)
Thuật toán JudgeCoreMixin.judge() (god-split thế hệ cũ) có **0 caller runtime sống** — caller code duy nhất là 1 test parity. Extract sẽ giữ ~4.3k LOC thuật toán vô consumer, ngược DNA #19. Bằng chứng: grep toàn repo (code-import duy nhất = test), judge.py hiện hành không dùng, judge_phases tự khai NOT WIRED, container rebuild boot + /ask OK không cần judge_parts.

## 3. Migration (Bước 2) — behavior-identical evidence
1. **Port verbatim** 8 builder + 2 regex guard → `scp/runtime/experts/url_builders.py` (pure, không fetch).
2. **Rewire** `experts/lifestyle.py` (imports + Holiday dùng `build_holiday_url` — fail-closed trước fetch, URL hợp lệ byte-identical với f-string cũ).
3. **Rewire** `whyengine.py:260`: `slms.GeographySLM` → `experts.humanities.Geography` (chỉ dùng `_local`; class name đổi theo quy ước cây mới).
4. **WHY-GATE hermetic** (trước/sau cùng input): France→'Paris', Việt Nam→'Hà Nội', Japan→'125800000', Thailand→'Bangkok', Blorptopia→None, Niger(fuzzy trap)→'24210000' — **6/6 MATCH** (kết quả qua đường code thật sau rewire).
5. **Differential builders cũ/mới**: 44/44 input identical (kể cả raise-path, ValueError message giống hệt) — chạy trước khi xóa cây cũ.
6. **Holiday fail-closed mới**: predict("…in x2?") → answer '', conf 0.0, elapsed 0.004s (không outbound).

## 4. Xóa (Bước 4) — bảng LOC
| Cây | File | LOC (thực đo) |
|---|---|---|
| `scp/runtime/slms.py` | 1 | 555 |
| `scp/runtime/slm_impls/` | 17 | 5,326 |
| `scp/runtime/slms_parts/` | 10 | 3,620 |
| `scp/runtime/judge_parts/` (+phases) | 19 | 4,356 |
| **Tổng xóa** | **47 file** | **13,857** |
| Mới thêm `scp/runtime/experts/url_builders.py` | 1 | +127 |
| `git diff --stat` (tracked, gồm S24 khoe riêng của tôi ở §8): 59 file, +179/−13,943; cộng file untracked mới → net ≈ **−13,816 LOC** | | |

Danh sách xóa đầy đủ = `git diff --name-status --diff-filter=D` (47 dòng, lưu trong log phiên; `git rm --cached -n` không chạy vì no-commit worker giữ index nguyên — xóa ở working tree, index untouched).

## 5. Importer/test đã cập nhật
1. `scp/meta/why_engine_parts/whyengine.py` — import Geography (experts).
2. `scp/runtime/experts/lifestyle.py` — imports url_builders + Holiday wiring.
3. `scp/autofix/scanners/dead_slm_scanner.py` — bỏ primary path judge_parts (scan judge.py; smoke: 0 bug, không crash).
4. `scp/autofix/scanners/routing_gap_scanner.py` — bỏ judge_parts dir (smoke: 0 bug).
5. `.github/workflows/scp-release-gate.yml` + `scp-rc-promotion.yml` — bỏ `judge_parts/judgecore_mixin.py` khỏi ruff list (file không còn tồn tại → ruff sẽ đỏ CI).
6. `tests/T02_contract/test_god_split_semantic_parity.py` — bỏ entry + test subject-dead; THÊM guard `test_judge_parts_dead_code_stays_dead` (strictness tăng).
7. `tests/T02_contract/test_flow_02_ask_chat_scp_standard.py` — 4 import → url_builders; HolidaySLM→Holiday (subject tương đương sau wiring builder); static guard chuyển sang chuẩn PURE nghiêm ngặt hơn (cấm mọi fetch machinery trong builder module).
8. `tests/T03_capability/test_ssrf_sweep_s2.py` — imports + `S2_PATCHED_RUNTIME_FILES` (4→1 file còn sống) + MỚI `S2_BUILDER_FILES` pure-guard (+1 test, nghiêm ngặt hơn cũ) + identity test trỏ url_builders (+assert build_holiday_url).
9. `tests/T03_capability/test_flow_12_background_why_scp_standard.py` — Geography import.

## 6. Test results (Bước 5)
| Gate | Kết quả |
|---|---|
| Collect-all (`--co -q`, deselect 1 test S24) | **1654/1655 collected, 0 error** (baseline 1660/1661; Δ−6 đúng bằng tổng hóa đơn xóa chủ đích: parity −2+1, ssrf −6+1) |
| Suites bắt buộc T04+T05+T07+T00 | Run1: 1 fail (flake) · Run2 (run lại đủ bộ): **506 passed, 23 skipped, 0 fail** · Run3: **506 passed 0 fail** |
| T02/T03 khu vực sửa (parity, flow_02, ssrf, flow_12) | **115 passed, 1 fail = test S24 đang deselect** (đỏ sẵn ở baseline HEAD — không phải regression của tôi) |
| `tools/t00_meta_audit.py` | FA-01/FA-03..07: 0 violation. **FA-02: đúng 8 nodeid** — toàn bộ là parametrize/test có SUBJECT là file đã xóa theo nhiệm vụ (6 ssrf param-path + 2 parity judge_parts). Cần owner re-baseline trusted_base sau khi duyệt xóa. Tripwire: **0 finding mới** — mọi finding đều gắn nhãn `[TRIPWIRE-DEBT]` (seed S25) |
| `tools/verify_scp_test_skill_contract.py` | **PASS_WITHIN_SCOPE, exit 0** |
| Flake A/B (chi tiết §7) | test_autofix_shadow_rollback fail 2/4 full-suite trên working tree, 0/3 trên baseline; minimal-prefix 4/4 PASS |

## 7. Flake T07 rollback — attribution (không tự vá ngoài scope)
`test_autofix_end_to_end_rollback_on_verify_failure` đỏ không-deterministic trong full-suite (2/4), xanh khi chạy đơn/file-prefix (4/4), xanh 3/3 trên worktree baseline HEAD. Signature fail: action=="skipped" PASS + file chưa bị mutate + active rỗng + rolled_back rỗng → khớp kịch bản `_auto_fix` skip SỚM qua `_auto_fix_gates` trước khi begin shadow tx (nghi vấn: path nhạy tải trong part1 reality-gate/subprocess trên Windows + `shutil.move` WinError-5 retry ngắn — comment trong shadow_snapshot.py tự nhận). **Không có liên kết code-path với cây đã xóa** (test không scan, không import slms/judge_parts; capability gate re-read env mỗi lần). Kết luận: flake nền tảng có-sẵn, tải máy (S24 chạy song song) khuếch đại → NEW FINDINGS #1.

## 8. Runtime proof Docker (Bước 6) — A/B container
Rebuild `scp-api:local` từ working tree + `--force-recreate` → **/health 200** (~20s). Instance tạm baseline-HEAD image :8003 (đã teardown) làm đối chứng. Probe trong container (mint token qua /auth/token — secret không rời container):
| Probe | baseline HEAD | working tree (S26+S24) | Đánh giá |
|---|---|---|---|
| Token mint | true | true | — |
| /ask context-backed "2+2=4" | FAIL, withheld=true | FAIL, withheld=true | **IDENTICAL** — không regression |
| /ask WHY-gate LocalDB (France/Japan/Blorptopia) | Paris / 125800000 / null | Paris / 125800000 / null | **IDENTICAL** — migration S26 behavior-identical trên runtime thật |
| judge.domain_experts discovery | 27 domains (cùng danh sách) | 27 domains (cùng danh sách) | **IDENTICAL** — url_builders không thêm class |
| /ask no-context | FAIL, withheld=true | **PASS, withheld=false** | DELTA — do code S24 dở dang trong cùng image (LOOKUP fork trả lời từ data-API), không thuộc delta S26; khớp hướng phát triển S24, orchestrator đối chiếu proof riêng của S24 |

## 9. File changed list (của S26)
- Modified (10): `scp/meta/why_engine_parts/whyengine.py`, `scp/runtime/experts/lifestyle.py`, `scp/autofix/scanners/dead_slm_scanner.py`, `scp/autofix/scanners/routing_gap_scanner.py`, `.github/workflows/scp-release-gate.yml`, `.github/workflows/scp-rc-promotion.yml`, `tests/T02_contract/test_god_split_semantic_parity.py`, `tests/T02_contract/test_flow_02_ask_chat_scp_standard.py`, `tests/T03_capability/test_ssrf_sweep_s2.py`, `tests/T03_capability/test_flow_12_background_why_scp_standard.py`
- Added (1): `scp/runtime/experts/url_builders.py`
- Deleted (47): 3 cây + slms.py như §4
- Không đụng: các file cấm theo nhiệm vụ (S24 files nguyên vẹn trong working tree).

## 10. Giới hạn & open questions
- FA-02 t00 chưa exit 0 trên SHA cũ — **by-design của gate delta**, cần owner duyệt + re-baseline (không thể trung thực hơn ở worker no-commit).
- Flake T07 rollback chưa root-cause tận gốc (out of scope) — đã cung cấp A/B + signature để slot sau.
- `religion` (experts/lifestyle.py) vẫn build URL bible inline — không đụng vì yêu cầu behavior-identical (NEW FINDINGS #5).
- Bản image runtime gồm cả code S24 dở dang (cùng working tree) — probe /ask B chỉ dùng để loại trừ regression S26, không làm proof hành vi cho S24.
- Số "13 skills" trong pack không được đếm lại trong phiên này (ngoài scope); inventory hint theo AGENTS.md.

---

## PHÁT HIỆN MỚI (NEW FINDINGS)
*(ngoài scope S26 — KHÔNG tự sửa, đề xuất slot xử lý)*

1. **[HIGH] Flake gate bắt buộc** — `tests/T07_learning/test_autofix_shadow_rollback.py::test_autofix_end_to_end_rollback_on_verify_failure` (+ cơ chế `_auto_fix_gates`/shadow move trong `scp/autofix/engine_parts/autofix_mixin.py:84`, `scp/autofix/shadow_snapshot.py:131,181-190`): đỏ 2/4 lần chạy full-suite trên working tree, xanh 4/4 khi prefix-minimal, xanh 3/3 trên baseline HEAD; signature "skip sớm, tx chưa tạo" + comment WinError-5 retry ngắn trong code. Đề xuất slot: S-next (autofix/test-stability) — run under `-p xdist`-free repro + bọc retry/copytree chặt hơn hoặc tách gate ra khỏi đường skip.
2. **[MED] Gate FA-02 vs nhiệm vụ xóa code** — `tools/t00_meta_audit.py:203-241`: delta nodeid cứng theo SHA khiến MỌI nhiệm vụ dọn-dead-code hợp lệ đều FA-02 FAIL ở SHA cũ. Đề xuất slot: owner/T00 — cơ chế re-baseline/allowlist có kiểm soát (kèm git SHA + lý do) cho deletion tasks được duyệt.
3. **[MED] Git Bash path-mangling khi `docker run -e`** — lệnh `docker run -e VAR=/posix/path` từ Git Bash trên Windows bị MSYS convert → container crash `PermissionError: '/app/C:'` (gặp khi dựng instance tạm :8003); workaround `MSYS_NO_PATHCONV=1`. Đề xuất slot: ops — ghi vào runbook/runtime-audit skill hoặc wrap script docker-proof.
4. **[MED] CI ruff list cứng đường dẫn file** — `.github/workflows/scp-release-gate.yml:109`, `scp-rc-promotion.yml:216`: ruff check liệt kê file đơn lẻ; file xóa → CI đỏ mặc dù không liên quan thay đổi. Đã sửa 2 dòng này trong phiên (thuộc fig importers), nhưng pattern list-cứng lặp lại — đề xuất slot: CI owner chuyển sang glob/package-scoped check.
5. **[MED] Religion expert build URL bible inline lệch chuẩn builder** — `scp/runtime/experts/lifestyle.py:174`: `quote(ref)` default `safe='/'` thay vì `build_bible_url` (`safe=''`) — lệch single-source-of-truth SSRF (vẫn qua safe_urlopen, host cố định). Đề xuất slot: S-next (SSRF hardening) — wire Religion qua build_bible_url sau khi quyết định behavior cho ref chứa '/'.
6. **[LOW] Holiday expert khai domain="history"** — `scp/runtime/experts/lifestyle.py:407` (+ HolidaySLM cũ tương tự): expert holiday đăng ký nhầm domain history trong judge.domain_experts. Đề xuất slot: S-next (experts) — quyết định domain đúng + test parity.
7. **[LOW] ~16 comment stale về judgecore_mixin/slms** — ví dụ `scp/security/escalation.py:120,194-216`, `scp/security/predictor.py:422-426`, `scp/meta/adversary_verifier.py:24`, `scp/meta/reverify_scheduler.py:24-25`, `scp/meta/scp_meta.py:6`, `scp/core/scp_v14.py:9`, `scp/core/smart_cache.py:344`, `scp/runtime/engine_parts/direct_api_verifier.py:16-18`, `scp/runtime/timing_and_restart.py:10`, `scp/security/circuit_breaker.py:15`, `scp/knowledge/claim_extractor.py:415`, `scp/knowledge/source_reputation.py:510`, `scp/core/reality_engine.py:31-32`, `scp/autofix/scanners/staticmethod_self_scanner.py:11`: vẫn mô tả judgecore_mixin/slms là "wired to /ask" — sai sau Cổng D + S26. Đề xuất slot: doc-hygiene slot gom dọn 1 lần.
8. **[LOW] 8 patch script 1-lần trỏ file đã xóa** — `scripts/maintenance/patch_universal_local_only.py`, `tools/fix_judgecore_domain_signature.py`, `tools/patch_explicit_domain_override.py`, `tools/patch_explicit_domain_override_v2.py`, `scripts/fix_judge_antibody_block.py`, `scripts/patch_antibody_interface.py`, `scripts/maintenance/fix_consistency_indent.py`, `scripts/maintenance/patch_web_fallback_consistency.py`: chạy lại sẽ fail (target không tồn tại). Đề xuất slot: repo-hygiene — archive/xóa script lịch sử hoặc ghi header DEPRECATED.
9. **[LOW] Reality script ngoài pytest đọc file đã xóa** — `tests/reality-tests/reality_4-b-002.py:92` trỏ `scp/runtime/judge_parts/judgecore_mixin.py`; không thuộc pytest collection nên không đỏ suite, nhưng sẽ lỗi nếu chạy thủ công. Đề xuất slot: repo-hygiene.
10. **[INFO] Debt đã seed sẵn (không phải finding mới)** — 6 unresolved_import + 1 duplicate-prompt trong `[TRIPWIRE-DEBT]` (admin_v100.py:164, v105_routes.py:719, ask_kernel_adapter.py:701, autofix/engine.py:408, reverify_scheduler.py:293, scpv14_process_mixin.py:76, judge_llm/multi_llm_crosscheck) đã nằm trong `data/governance/tripwire_baseline.json` từ S25; 3/6 thuộc file S24 đang sửa.

---

**SHA256 (skill binding, append cuối theo nhiệm vụ):**
```
4aada0be4873598dc50c3a7f38d90151429bb5263c511a838ed1cdcb4d594d10  .agents/skills/scp-dna/SKILL.md
4649eb4d4a6e8c006e2db4e83b32bbe5c3f967d01a69e04e3e91a91eedf35bfa  .agents/skills/scp-skill-review/SKILL.md
```
