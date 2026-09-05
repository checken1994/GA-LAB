# SCP COMPLETION MISSION QUEUE — điều phối hội đồng chuyên gia

> Master roadmap: SCP hiện tại (`128a44a`+) → Complete SCP (blueprint 12 hệ + 138 capabilities).
> Mỗi mission = 1 expert = 1 commit scope. Kết thúc mission phải: tests green (mới + cũ),
> coverage claims cập nhật đúng chuỗi, progress log đầy đủ, commit local (coordinator push).
> Quy tắc bất di bất dịch: PASS≠TRUE — cấm stub/mock/skip/weaken; fail-closed;
> capability chưa implement → test RED `BLOCKED_MISSING_IMPLEMENTATION` drives build.

## Trạng thái hiện tại (baseline điều phối)

- Đã C-level: S01 kernel core, S05 evidence store, S10 risk (4 authorities), X08 world-state (3 authorities), S04 firewall, S09 partial, governance drift/privacy, zero-cost $0 wall (service paths), coverage authority (47 claims)
- Đang chạy: Mission B (kernel P1), Mission C (T00 anti-Goodhart)
- Đã biết hỏng: AutoFix commit-leg (reality_test shallow + evidence_replay), epistemic runtime cutover, shadow canary dead

---

# WAVE 1 — Đóng vòng tự-tiến hóa + vá Goodhart (P0)

## M1 — AutoFix commit-leg THẬT
**Expert scope:** `scp/autofix/runner_phases/{reality_test,evidence_replay}.py`, `runner_phases/post_fix_verify.py`, `scp/autofix/engine_parts/autofix_mixin.py`, `tests/T09_golden_task/`
**Spec:**
1. `reality_test.py::run_reality_test(bug_id, file_path, exercise_callables)` — import module đã vá (importlib, KHÔNG cache sys.modules), enumerate callables public gần bug line (AST), gọi với args suy từ signature (str→"test", int→1, default→default, còn lại→None), **fail nếu callable bắt buộc raise**; không hardcode success; chưa exercise được → UNVERIFIED (rollback tiếp diễn — trung thực).
2. `evidence_replay.py` — `compute_bug_signature` = sha256(bug_type + file + context slice); `verify()` so bug signature với re-scan post-fix; `seed_gold_evidence()` chỉ gọi tay operator (xóa env-var magic).
3. Shadow canary + confidence ranker chạy thật: sửa `locals().get("ctx.pairs")` → `getattr(ctx, "pairs", [])`.
4. Part2: bind `filepath = Path(ctx.bug.file)` đầu hàm.
5. Route `_attempt_meta_repair` + XSS fast-path qua DriftGuard/`_is_protected_path` (đã expand 2026-09-03) — protected → proposal queue.
**Accept:** T09 4/4 green với verification thật (cosmetic patch vẫn không promote — completeness check phải bắt no-op patch); không mock còn sống (grep "simulated verification|mock_signature|seeded" = 0 hits).
**Binding:** epistemic.evidence nâng mức nếu đủ; self_improvement.bounded_autofix PARTIAL→CONTRACT nếu reality_test coverage khớp CE-S09 edges.

## M2 — T00 Anti-Goodhart (EXPERT C đang chạy)
**Spec:** `_node_exists` yêu cầu prefix `test_` + ≥1 assert/raises trong body; phát hiện `pytestmark = pytest.mark.skip/xfail` module-level (AST Assign) trong CẢ detector; skip-scan mở rộng 12/12 gates; zero-collected check thêm skip-state. Khai báo danh sách claim bị ảnh hưởng — KHÔNG xóa claim.

## M3 — Kernel P1 (EXPERT B đang chạy)
**Spec:** bridge replay catch `StorageIntegrityError`; orphan-sweep fence theo lease heartbeat/expires + ALLOWED_TRANSITIONS + version++; checkpoint `to_state=None`; heartbeat quanh awaited dispatch. Regressions: 4 test negative-control verified.

---

# WAVE 2 — Epistemic runtime cutover + Governance (P1)

## M4 — Production cutover sang epistemic stack
**Expert scope:** `scp/runtime/engine_parts/scpv14_process_mixin.py`, `scp/core/phase0.py`, `scp/epistemic/`
**Spec:** mọi `add_evidence/link_evidence/add_decision` trong production runtime route qua `EvidenceStore`/`LineageStore`/`TemporalAuthority` mới (cũ phase0 giữ read-only compat shim). Audit: grep toàn bộ caller cũ.
**Accept:** 1 E2E test — runtime action → EvidenceStore có record bitemporal + lineage UNKNOWN_INDEPENDENCE + tamper fail-closed; legacy store ghi 0 record mới.

## M5 — Immutability hoàn chỉnh
**Spec:** DELETE trigger cho evidence/calibration/capability_proofs/identity_links/sources; `record_hash` keyed (HMAC với key từ SecretBroker — không hardcode); `record_proof` validate `kind=TEST_RESULT` + `tested_sha == git rev-parse HEAD` (từ git, không tin caller).
**Accept:** tamper detection test với keyed-hash; proof với tested_sha sai → REJECTED.

## M6 — Governance runtime (S11: 5 caps)
**Spec:** `external_authority` connector REPORT_ONLY default (contract: event types, risk ceiling, credential ref, approval, evidence required, post-submit verify); `human_comprehension` (high-stakes approval phải kèm bundle + contradiction + unknowns); `license_copyright` + `dangerous_knowledge` (SAFE/RESTRICTED/HIGH_RISK/PROHIBITED classification + không route vào execution).
**Accept:** connector không configured → bundle only; approval-gated → WAITING_APPROVAL; forbidden edge test (`RiskAuthority -> Tool`, `raw_secret -> prompt`).

---

# WAVE 3 — Subsystem runtime còn thiếu (S03/S06/S07/S08/S12)

## M7 — S03 Acquisition runtime
**Scope:** `scp/epistemic/acquisition.py` (source_registry runtime + acquisition scheduler + URL guard + safe fetcher bounded + free API qualifier).
**Accept:** 1 URL được acquisition theo policy → source_identity + evidence occurrence + quarantine check; resource budget vượt → WAIT_RESOURCE.

## M8 — S06 Knowledge runtime
**Scope:** retrieval index (FTS5; vector = accelerator không authority), gold lifecycle (promote/demote/review_after), temporal revalidation runtime.
**Accept:** claim CORROBORATED chỉ khi independent_lineages >= threshold; GOLD có review_after + demote khi contradiction.

## M9 — S07 Experience runtime
**Scope:** episode store (problem→action→outcome→lesson), failure memory (planner hỏi trước khi lặp lỗi), reasoning pattern distill.
**Accept:** 1 failure episode → planner truy vấn được → tránh lặp action; episode không đủ fields → DISCUSSION_ONLY.

## M10 — S08 Reasoning runtime
**Scope:** causal store (HYPOTHESIS default, confounders, counterfactual), experiment engine (small/bounded/reversible/information-gain), question memory runtime (durable qua restart).
**Accept:** question sống qua restart; causal không tự nâng CAUSES; experiment có rollback.

## M11 — S12 Self-awareness runtime
**Scope:** blindspot registry + doubt audit (định kỳ → output thành TASK) + capability evidence recompute runtime.
**Accept:** doubt audit sinh task trong kernel; capability evidence thiếu tested_sha → UNKNOWN.

---

# WAVE 4 — Cross-cutting X01–X07 (P2)

- **M13 X01 Identity/Trust:** actor registry (human/agent/model/sensor), trust dimensions, root-of-trust non-self-modifiable.
- **M14 X02 Observability:** trace_id→task→attempt→step→observation→verifier→artifact chain + evidence refs, không log secret.
- **M15 X03 Resource Governor:** priority P0>P1>P2>P3>P4; low-resource → pause curiosity; quota budget runtime.
- **M16 X04 Supply chain:** dependency inventory + QUARANTINE→SCAN→TEST→BOUNDED ROLLOUT.
- **M17 X05 DR:** backup + ACTUAL restore test cho kernel/evidence/knowledge; corrupt → restore → reconcile → no duplicate side effect.
- **M18 X06 Simulation:** sandbox runtime cho patch/policy; simulation PASS ≠ production Reality (trigger).
- **M19 X07 Multi-agent:** roles + bounded turns + no-circular-approval + shared state qua kernel/evidence.

---

# WAVE 5 — Evidence + Freeze

## M20 — EVIDENCE_VERIFIED runtime
**Spec:** mỗi required capability: chạy bound tests tại HEAD → `EvidenceStore.observe(kind=TEST_RESULT, content=results_json, tested_sha=HEAD)` → claims upgrade với snapshot_sha + evidence_refs. Level B-capability: unit evidence đủ; C-capability: cần E2E flow evidence.
**Accept:** verifier PASS khi required_capabilities all EVIDENCE_VERIFIED (hiện FORBIDDEN).

## M21 — Golden C E2E
**Spec:** acquisition tin tức thật (hoặc fixture offline) → risk assessment → containment qua kernel → bundle. Hermetic fixture offline bắt buộc; live provider chỉ supplemental.

## M22 — Freeze + Strict Checkpoint
**Điều kiện:** blocker=0, HARNESS_BROKEN=0, EVIDENCE_VERIFIED phủ required, T00 meta-audit green, working tree clean.
**Trình tự:** freeze SHA → T00-T11 strict → security/mutation/acceptance → manifest SHA/DNA/Skills → verdict: "verified within P0 scope on SHA X".

---

# QUY TẮC ĐIỀU PHỐI (coordinator must-follow)

1. Concurrency: tối đa 2 expert nền song song; scope file rời nhau.
2. Mission xong → coordinator: full suite → merge/push → dispatch mission kế (dependency order trên).
3. Mọi mission: progress log `reports/expert-panel/<M-id>.md`; commit prefix "fix<M-ID>(scope): ".
4. Chặn tuyệt đối: stub/mock/skip/weaken/fail-open; "Close bằng fake" = vi phạm DNA #22 (đã xảy ra 1 lần — xem memory).
5. Capability chưa implement → test RED BLOCKED_MISSING_IMPLEMENTATION drives build (không đợi).
6. Mỗi mission hoàn tất → binding claims cập nhật đúng chuỗi UNPROVEN→PARTIAL→CONTRACT→(EVIDENCE_VERIFIED khi có runtime evidence).
