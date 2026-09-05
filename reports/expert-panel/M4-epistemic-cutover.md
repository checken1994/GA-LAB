# M4 — Epistemic Cutover (runtime → immutable evidence stack)

- Expert: M4 | Repo: `C:\Users\check\Downloads\scp` | Branch: `main` (local commit only, NO push)
- Mission: cut over the production runtime evidence writes from the legacy
  mutable phase0 store (`UPDATE evidences SET verification_status=...`) to the
  immutable epistemic stack (`EvidenceStore.observe` + `GovernedEvidenceWriter`
  + `PrivacyWriteGate` + `LineageStore`), with backward-compatible deprecated
  phase0 facade.
- Scope files: `scp/epistemic/runtime_bridge.py` (new),
  `scp/runtime/engine_parts/scpv14_process_mixin.py`,
  `scp/core/phase0.py`, `scp/epistemic/__init__.py`,
  `tests/T06_verifier/test_runtime_bridge_cutover.py` (new),
  `reports/expert-panel/M4-epistemic-cutover.md`. NOT in scope: kernel,
  gateway, autofix, other experts' `.agents/` workspaces.

## Evidence baseline (recon, trước khi sửa — commit c2d0fd2)

- `scp/runtime/engine_parts/scpv14_process_mixin.py:553-596` — Step 8 gọi
  `self.phase0.add_conclusion/add_evidence/link_evidence/add_decision`.
- `scp/core/phase0.py:214-232` — `Phase0Store.add_evidence`: INSERT vào bảng
  `evidences` (append-only, chưa vi phạm); nhưng class `EvidenceStore` tại
  `scp/core/phase0.py:348-428` (`verify`/`fail`/`supersede`) làm in-place
  `UPDATE evidences SET verification_status=...` — vi phạm invariant
  immutable/supersede (authority mutable đang sống song song).
- **Missing piece phát hiện thêm (DNA #19):** `SCPV14ProcessMixin` KHÔNG được
  import bởi bất kỳ module nào trong repo; `self.phase0` không bao giờ được
  gán (grep toàn repo: 0 kết quả). Host `SCPV14` thật (`scp/runtime/engine.py`)
  đã là stub delegate sang TaskKernel. ⇒ Path "live" trong audit thực chất là
  path được tham chiếu nhưng chưa có host gán attribute; mọi consumer ngoài
  repo gán `self.phase0 = Phase0Store()` vẫn rơi vào path mutable.
- `scp/epistemic/`: `evidence_store.py` (immutable, trigger
  `evidence_no_update`, record_hash, blob CAS, `supersede()` tạo evidence mới
  + relation `SUPERSEDES`), `evidence_writer.py` (`GovernedEvidenceWriter`
  hiện có, enforce `PrivacyWriteGate`), `lineage.py` (`LineageStore`,
  default `UNKNOWN_INDEPENDENCE`, UNKNOWN contributes zero).
- Production caller duy nhất của epistemic stack: `scp/llm_gateway/free_catalog.py:98-112`
  (`EvidenceStore(data/foundation/epistemic.sqlite)` + `PrivacyWriteGate(spec/data_policies.yaml)`).
- `LineageStore`, `TemporalAuthority`: 0 production caller (chỉ tests).
- Tests: không có test nào import `scp/core/phase0.py` (grep tests/ = 0 file).
- Policy: `spec/data_policies.yaml` — INTERNAL raw_storage_allowed=true;
  SECRET/SENSITIVE redacted-only; gate tự redact PII/secret + compose severity.
- **BASELINE TEST FACT (commit c2d0fd2):** `python -m pytest tests/ -q --tb=no`
  → **411 passed** in 141.22s, 0 failed.

## Thiết kế cutover (small, reversible, rollback = git revert 1 commit)

1. **`scp/epistemic/runtime_bridge.py` (mới)** — `RuntimeEvidenceBridge`:
   - `build_epistemic_stack()` + `get_runtime_bridge()` (singleton, thread-lock):
     `EvidenceStore(data/foundation/epistemic.sqlite, .../evidence_objects)` +
     `GovernedEvidenceWriter(store, PrivacyWriteGate(spec/data_policies.yaml))` +
     `LineageStore(data/foundation/lineage.sqlite)`.
   - Mapping ngữ nghĩa: `slm_response → MODEL_RESPONSE` (chỉ chứng minh "model
     nói X"), `reality_check/conclusion/decision → RUNTIME_OBSERVATION`,
     verification outcome → `TEST_RESULT`.
   - Payload nhạy cảm (question/answer/raw) đi qua `content` (được gate
     redact/deny); metadata chỉ chứa hash/verdict/confidence/cycle — không
     đặt raw question vào metadata vì metadata KHÔNG qua gate.
   - `record_conclusion(...)` gọi `LineageStore.ensure_relation` cho mọi cặp
     nguồn + `assess_independent_support(sources)` → metadata `lineage`
     (conservative: UNKNOWN = 0 independent support).
2. **Mixin Step 8** — gọi bridge trực tiếp; không còn `self.phase0.*`;
   legacy mirror bị ngắt để tránh double-record.
3. **`scp/core/phase0.py` facade** — `add_evidence/add_conclusion/
   link_evidence/add_decision/EvidenceStore.verify/fail/supersede` giữ chữ ký
   cũ, log DeprecationWarning, route authority qua bridge (best-effort,
   không raise), legacy INSERT/UPDATE chỉ còn là deprecated read-model.
4. Tests mới `tests/T06_verifier/test_runtime_bridge_cutover.py`.

## Progress log (bổ sung liên tục)

- [t0] Baseline 411 passed (c2d0fd2). Recon xong, missing piece #19 ghi trên.
- [t1] Tạo `scp/epistemic/runtime_bridge.py` (~370 LOC):
  - `build_epistemic_stack()`/`get_runtime_bridge()` (singleton thread-safe):
    EvidenceStore + GovernedEvidenceWriter(PrivacyWriteGate) + LineageStore.
  - API runtime: `record_model_response` (MODEL_RESPONSE), `record_reality_check`
    (RUNTIME_OBSERVATION), `record_conclusion` (+ lineage assessment),
    `record_decision` (+ DECIDES), `supersede`, `record_verification`
    (TEST_RESULT + VERIFIES), `link`, `link_legacy_pair`,
    `register_legacy_mapping`, `has_evidence`.
  - `KIND_BY_LEGACY_TYPE`: slm_response→MODEL_RESPONSE, reality_check→
    RUNTIME_OBSERVATION; collector `scpv14-runtime`/`phase0-compat`.
- [t2] Cutover `scpv14_process_mixin.py` Step 8 (556-630): bridge trực tiếp,
  không còn `self.phase0.*`. **Fix-at-failure (DNA #26):** import
  `JudgeVerdict` từ `scp.runtime.judge` bị ImportError có sẵn (module broken,
  0 test nào import nó nên baseline vẫn xanh) → sửa thành
  `scp.runtime.judge_parts.types` (canonical Task 19-A, giữ nguyên class).
- [t3] `scp/core/phase0.py`: facade deprecated —
  `Phase0Store.add_evidence/add_conclusion/link_evidence/add_decision` +
  mutable `EvidenceStore.verify/fail/supersede` giờ `_warn_deprecated()` +
  route authority qua bridge (best-effort, không raise); legacy INSERT/UPDATE
  chỉ còn là read-model sync (verification outcome authority = TEST_RESULT
  mới + relation VERIFIES/SUPERSEDES, target không bao giờ bị edit).
- [t4] Tests mới `tests/T06_verifier/test_runtime_bridge_cutover.py` (7 test):
  occurrence/content identity, immutability trigger, SUPERSEDES không edit,
  verification là evidence mới, phase0 facade routing + DeprecationWarning,
  PrivacyWriteGate redact secret, mixin không còn path phase0 mutable.
  → **7/7 passed**. 2 lần fail đầu đã sửa: (a) test gọi thiếu bước link/
  content lệch do raw_data khác; (b) assertion dính comment literal —
  KHÔNG có test nào bị skip/xoá/hạ chuẩn.
- [t5] Smoke import: mixin, epistemic, phase0 — OK.

## Reality check & remaining scope

- **FULL SUITE FACT:** `python -m pytest tests/ -q --tb=short` (sau cutover,
  trên working tree @ c2d0fd2+changes) → **418 passed in 175.58s, 0 failed**
  (= 411 baseline + 7 test mới; không test nào bị delete/skip/xfail/hạ chuẩn).
- Snapshot được commit locally (KHÔNG push): **commit `ca889a5`** trên branch
  checkout hiện tại `experts-4.0.3-434green` (repo không đứng trên literal
  `main` lúc thực thi; không switch branch để không phá workspace expert khác)
  — rollback path: `git revert ca889a5` (1 commit, không đụng file ngoài scope).
- Runtime path MỚI (authority): `scpv14_process_mixin.process` Step 8 →
  `get_runtime_bridge()` → `GovernedEvidenceWriter.observe` (PrivacyWriteGate)
  → `EvidenceStore` (immutable, trigger `evidence_no_update`) + `LineageStore`.
- Compat path CŨ (deprecated): `scp/core/phase0.py` facade giữ nguyên chữ ký,
  DeprecationWarning + route qua bridge; legacy UPDATE chỉ còn read-model sync.

### Remaining scope (không claim "hoàn tất toàn phần" — DNA #22/#23)

1. `self.phase0` chưa bao giờ được gán trong repo (host SCPV14 là stub):
   nếu sau này phục hồi host engine đầy đủ, Step 8 mới đã sẵn sàng; Phase0Store
   facade vẫn deprecated. Cần quyết định kiến trúc: xoá hẳn mixin legacy hay
   gắn lại host.
2. Dữ liệu CŨ trong bảng `evidences/conclusions` legacy không được migrate
   sang epistemic store (out of scope, cần migration script riêng nếu muốn
   audit cross-store).
3. `TemporalAuthority` (scp/world_state) vẫn 0 production caller — ngoài
   scope M4 (M-expert khác/ W2 sau).
4. Deprecation facade vẫn ghi legacy read-model; kế hoạch xoá hẳn khi không
   còn consumer (cần audit dashboard/SQL ngoài repo).
5. `phase0-compat` routing là best-effort (không raise) — nếu epistemic stack
   lỗi, legacy vẫn ghi read-model; monitoring nên cảnh báo log
   "phase0 compat: epistemic routing failed".

### Bằng chứng lệnh đã chạy

- Baseline: `python -m pytest tests/ -q --tb=no` → 411 passed (141.22s) @ c2d0fd2.
- Sau cutover: `python -m pytest tests/T06_verifier/test_runtime_bridge_cutover.py -q --tb=short`
  → 7 passed (0.82s).
- Full: `python -m pytest tests/ -q --tb=short` → 418 passed (175.58s), exit 0.
- Smoke: import `scpv14_process_mixin`, `scp.epistemic`, `scp.core.phase0` — OK
  (trước fix, mixin ImportError ngay tại module level).

