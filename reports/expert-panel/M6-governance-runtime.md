# M6 — Governance Runtime Progress Log

Expert: M6 (S11 governance runtime) — branch `experts-4.0.3-434green`.
Scope: 4 capabilities còn thiếu của S11_GOVERNANCE:

1. `governance.human_comprehension` → `scp/governance/comprehension.py`
2. `governance.license_copyright` → `scp/governance/license.py`
3. `governance.dangerous_knowledge` → `scp/governance/dangerous_knowledge.py`
4. `governance.external_authority` (W2 skip) → `scp/governance/external_authority.py`

Off-limits (other experts): `scp/autofix/`, `scp/task_kernel*`, `scp/hands/`,
`tests/T04_kernel/`, `tests/T09_golden_task/`, `scp/epistemic/`, `scp/self_model/`,
`scp/calibration/`. Already-done (không đụng): `drift_guard.py`, `privacy.py`,
`retention.py`.

## Reality check trước khi sửa (evidence-first)

- Spec hiện hành: `spec/scp_future_cause_effect_matrix.yaml` S11_GOVERNANCE,
  edges CE-S11-01/03/05 (effective 4.0.2 compose qua
  `spec/scp_future_target_manifest.yaml`).
- Forbidden paths liên quan: `license_unknown -> unrestricted_redistribution`,
  `dangerous_content_as_executable_instruction`, `unconfigured_external_write`,
  `implicit_ALLOW_on_UNKNOWN`, `approval_as_only_control`,
  `human_approval -> bypass_sandbox`, `learned_content -> governance_override`.
- `grep` toàn `scp/`: chưa có reference tới 4 capability IDs trên → không có
  registry nào cần cutover; `scp/governance/__init__.py` chỉ export DriftGuard.
- `tests/T03_capability/` có 9 file test sẵn; convention: pytest thuần,
  import từ `scp.governance.*`, assertion fail-closed.

## Thay đổi

- [x] `scp/governance/comprehension.py` (mới, 240 dòng):
  - `HumanComprehensionGate.build_bundle` (dòng 109): 7 trường bắt buộc
    (action/resource/consequence/evidence/contradictions/unknowns/rollback_plan);
    thiếu bất kỳ trường nào → `ValueError` (fail-closed, không thể approve);
    rollback chưa verified tự sinh unknown `U-rollback`.
  - `evaluate` (dòng 170): re-validate bundle; digest-bound approval
    (`BLOCKED_STALE_APPROVAL` khi approval gắn bundle khác); mọi concern
    (contradiction + unknown) phải được acknowledge tường minh, không thì
    `BLOCKED_RUBBER_STAMP` (dòng 213/225) — không implicit_ALLOW_on_UNKNOWN.
  - `ComprehensionResult.grants_capability` là hằng số `False` (dòng 94):
    approval_as_only_control bị cấm ở cấp cấu trúc, understanding không phải
    capability.
- [x] `scp/governance/license.py` (mới, 279 dòng):
  - Bảng SPDX family (permissive/attribution/sharealike/copyleft weak-strong/
    noncommercial/no_derivatives/proprietary) × 4 usage
    (INGESTION/REDISTRIBUTION/EXECUTION/EXTERNAL_RELEASE) →
    ALLOW/RESTRICT/REQUIRE_HUMAN/QUARANTINE/DENY.
  - License KHÔNG nằm trong bảng (`unknown`, dòng 201-207) → QUARANTINE cho
    mọi usage; `assert_no_forbidden_effect` (dòng 257) raise
    `ForbiddenLicensePath` khi ai thử gắn effect "unrestricted" lên license
    unknown/denied.
  - Thiếu provenance (source) → tối thiểu REQUIRE_HUMAN; bundle lấy worst-case.
- [x] `scp/governance/dangerous_knowledge.py` (mới, 205 dòng):
  - `classify` (dòng 102): signal scan 3 tầng — PROHIBITED_RAW (raw payload
    `curl|sh`, ransomware builder, shellcode, bioweapon synthesis) >
    ACTIONABLE_HIGH_RISK (mimikatz/credential dumping, reverse shell recipe,
    destructive command, PoC) > RESTRICTED_REFERENCE (CVE, pentest methodology,
    dual-use tooling) > SAFE_REFERENCE. Label do caller khai báo chỉ được ghi
    nhận, không bao giờ override content signals.
  - `execution_eligible` (dòng 81) derived CHỈ từ danger class: chỉ
    SAFE_REFERENCE là True. `route` tới "execution" cho class cao hơn raise
    `ForbiddenExecutableRoute` (dòng 171) — dangerous_content_as_executable_instruction
    bị cấm. PROHIBITED_RAW → BLOCK_NO_STORAGE.
- [x] `scp/governance/external_authority.py` (mới, 283 dòng):
  - Không configured → `BUNDLE_ONLY` (dòng 147), write_authorized=False —
    unconfigured_external_write không thể xảy ra;
    `assert_no_unconfigured_write` (dòng 220) raise khi receipt xuất hiện ở
    decision phi-send.
  - Contract connector: allowed_event_types, risk_ceiling (0-100),
    credential_ref (opaque ref thôi, raw secret bị từ chối), mode mặc định
    REPORT_ONLY (không bao giờ send dù có approval).
  - SEND_ALLOWED vẫn cần evidence bundle (REQUIRE_EVIDENCE) +
    comprehension-certified approval → WAITING_APPROVAL → APPROVED_TO_SEND;
    `record_submission` (dòng 234) post-submit verification + dedupe
    submission_id (idempotent, không gửi trùng).
- [x] `scp/governance/__init__.py`: export symbols mới của 4 module.
- [x] `tests/T03_capability/test_governance_runtime.py` (mới): 24 test
  (comprehension 5, license 6 (1 parametrize ×4 usage), dangerous_knowledge 6,
  external_authority 7... tổng 24 passed), phủ cả forbidden paths.

## Test evidence

Lệnh chạy trên SHA làm việc (pre-commit):

```text
python -m pytest tests/T03_capability/test_governance_runtime.py tests/T03_capability/ -q
  → 67 passed (24 test mới + 47 test T03 sẵn có), 1.25s
python -m pytest tests/T00_integrity/ -q
  → 63 passed, 9.85s
python -m pytest --collect-only -q
  → 493 tests collected, 0 error (không break import nào)
```

Chưa chạy toàn bộ tests/ (mission scope: T03 + T00); collect-only toàn repo
xanh xác nhận không phá collection của gate khác.

## Còn mở / scope hạn chế

- Classification của `dangerous_knowledge` là deterministic regex baseline,
  không phải ML: là tầng governance fail-closed (false positive an toàn hơn
  false negative), có thể nâng cấp scanner phía sau mà không đổi contract.
- License table là danh sách SPDX phổ biến; license lạ đi vào QUARANTINE
  (fail-closed) chứ không đoán. Mở rộng bảng là thay đổi dữ liệu thuần.
- `external_authority` mới ở tầng governance (decision + verification);
  connector transport thật (SMTP/webhook client) và cutover vào runtime
  engine chưa nằm trong mission này.
- Chưa có bản pass trên golden task/T09 (ngoài scope của M6).
- Integration wiring (gọi các gate này từ pipeline ActionProposal) là bước
  tiếp theo; hiện các module là primitive có contract test riêng.
