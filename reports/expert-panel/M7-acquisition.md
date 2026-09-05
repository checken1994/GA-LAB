# M7 — S03 Internet Acquisition Runtime Progress Log

Expert: M7 (S03 Internet Acquisition) — branch `experts-4.0.3-434green`.
Scope: 4 authority theo spec `spec/scp_future_cause_effect_matrix.yaml`
S03_INTERNET_ACQUISITION (CE-S03-01, CE-S03-02), triển khai trong MỘT module
`scp/epistemic/acquisition.py`:

1. `AcquisitionScheduler` (WHEN: pull vs curiosity + information_gain + budget)
2. `SourcePolicy` (allowlist/blocklist, rate limit per source, freshness)
3. `AcquisitionPipeline` (fetch → quarantine → evidence → identity → lineage → claim trigger)
4. `FreeAPIQualifier` (DISCOVERED → HTTPS/auth → health probe → schema → VERIFIED_FREE_API)

Off-limits tôn trọng: `scp/autofix/`, `scp/task_kernel*`, `scp/governance/`,
`tests/T04_kernel/`, `tests/T09_golden_task/`. AI_SHARED_BOARD.md có thay đổi
của coordinator — KHÔNG đụng, không commit cùng.

## Reality check trước khi viết code (evidence-first)

- Spec hiện hành: S03_INTERNET_ACQUISITION, capabilities `world.acquisition`,
  `world.source_registry`, `world.discovery`, `world.monitor_policy`,
  `world.free_api_qualification` (mục tiêu M4/P2). Forbidden paths:
  `crawler -> direct_knowledge`, `discovered_host -> automatic_egress_allow`,
  `curiosity -> unbounded_monitoring`. must_not_effect CE-S03-02:
  `budget_self_increase`, `paid_provider_switch`, `unqualified_api_dispatch`.
- Reuse inventory đã đọc nguyên văn: `scp/core/url_fetcher.py` (SSRF-safe,
  per-hop revalidation, SCP_EGRESS_MODE default deny),
  `scp/core/top_systems_learning.py` (`inspect_untrusted` — 24 quarantine
  patterns, `TokenBucket` cơ học), `scp/epistemic/evidence_store.py`
  (append-only + record_hash), `evidence_writer.py` (GovernedEvidenceWriter +
  PrivacyWriteGate), `source_identity.py` (SourceStore, canonicalize_url),
  `lineage.py` (LineageStore, DB-default UNKNOWN_INDEPENDENCE),
  `runtime_bridge.py` (EpistemicStack).
- `grep` chưa có `acquisition.py` nào trong `scp/` → không cần cutover registry;
  `scp/epistemic/__init__.py` export 8 symbol cũ.
- Fetcher duy nhất: pipeline ủy quyền cho `scp.core.url_fetcher._safe_fetch_url`
  (không tạo impl thứ 3 — đúng ràng buộc của module đó).

## Thay đổi

- [x] `scp/epistemic/acquisition.py` (mới, ~930 dòng):
  - `AcquisitionBudget` (dòng 98): cap CỐ ĐỊNH (max_fetches, max_total_bytes)
    khóa tại construction — KHÔNG tồn tại API tăng cap
    (`budget_self_increase` bị cấm ở cấp cấu trúc). Reserve nguyên tử
    thread-safe, kế toán theo ATTEMPT (fetch fail vẫn tốn slot — chống retry
    vô hạn); fetch cap trả về = min(remaining_bytes, ABSOLUTE_MAX_FETCH_BYTES=2MB)
    nên byte budget không bao giờ bị vượt.
  - `AcquisitionScheduler` (dòng 180): `information_gain` — PULL = 1.0
    (nhu cầu tường minh), CURIOSITY = uncertainty × novelty (clamp 0..1);
    gain < `min_curiosity_gain` (0.15) → `SKIPPED_LOW_GAIN` tường minh;
    curiosity bị cap cứng `curiosity_max_items=1`
    (`curiosity -> unbounded_monitoring` forbidden); pre-check budget →
    `WAIT_RESOURCE` + `pending_need_preserved` (CE-S03-02), không silent skip.
  - `SourcePolicy` (dòng 262): default-DENY — blocklist > allowlist (exact
    host), host lạ bị chặn (`discovered_host -> automatic_egress_allow`
    forbidden); URL có credentials → reject; rate limit per-domain dùng lại
    `TokenBucket` (hết token → RuntimeError → WAIT_RESOURCE); freshness
    per-domain (`min_refresh_seconds`) → re-fetch trong window →
    `SKIPPED_FRESH` tường minh; `register_qualified_api` là cổng DUY NHẤT để
    host API vào allowlist và chỉ `FreeAPIQualifier` gọi được.
  - `AcquisitionPipeline` (dòng 419): chuỗi CE-S03-01 — policy gate →
    freshness → TokenBucket → budget reserve → bounded fetch (cap truyền xuống
    fetcher) → `inspect_untrusted` → `SourceStore.register` (canonical
    identity) → lineage `ensure_relation` (DB-default UNKNOWN_INDEPENDENCE cho
    mọi peer, `assess_independent_support` vào metadata) → evidence occurrence
    qua `GovernedEvidenceWriter` (kind HTTP_RESPONSE, data_class PUBLIC, privacy
    gate vẫn redact/deny) → claim trigger CHỈ cho content không quarantine
    (`crawler -> direct_knowledge` forbidden — pipeline không tự ghi knowledge).
    Quarantined: vẫn lưu evidence provenance với `quarantined=True` + reason
    (đúng chuẩn C1 của top_systems_learning) nhưng
    `claim_extraction=SUPPRESSED_QUARANTINE`. Mọi trạng thái tường minh:
    ACQUIRED / QUARANTINED / WAIT_RESOURCE / BLOCKED_POLICY / SKIPPED_FRESH /
    SKIPPED_LOW_GAIN / FAILED.
  - `FreeAPIQualifier` (dòng 739): state machine DISCOVERED → HTTPS_CHECK →
    AUTH_CHECK (402 → payment_required; 401/403 → auth_required_cannot_prove_free;
    probe lỗi → fail) → HEALTH_PROBE (bounded 64KB) → SCHEMA_OBSERVATION
    (JSON object bắt buộc) → POLICY_REGISTRATION. `advertised_free` từ nguồn
    discovery chỉ là DATA, không phải authorization; bước đầu tiên thất bại
    hoặc UNKNOWN → QUARANTINE, KHÔNG ghi evidence, KHÔNG đăng ký policy
    (`unqualified_api_dispatch` forbidden). Chỉ sau khi toàn bộ step OK mới
    ghi schema evidence + cho host vào allowlist kèm provenance.
- [x] `scp/epistemic/__init__.py`: export 9 symbol acquisition mới.
- [x] `tests/T03_capability/test_acquisition_runtime.py` (mới, 19 test):
  4 acceptance criteria của mission + fail-closed contracts (mục riêng bên
  dưới).

## Test evidence

Lệnh chạy trên working tree (HEAD docs 3464456, code M7 chưa commit khi chạy):

```text
python -m pytest tests/T03_capability/test_acquisition_runtime.py tests/T03_capability/ -q
  → 86 passed (19 test M7 mới + 67 test T03 sẵn có), 2.81s
python -m pytest tests/T00_integrity/ -q
  → 63 passed, 11.01s
python -m pytest tests/T06_verifier/test_source_identity_lineage.py
  tests/T06_verifier/test_runtime_bridge_cutover.py
  tests/T06_verifier/test_evidence_store.py tests/T02_contract/ -q
  → 122 passed, 17.78s (không phá foundation epistemic hiện có)
python -m pytest --collect-only -q
  → 534 tests collected, 0 error (không break import của gate khác)
```

19 test M7 ánh xạ acceptance:

- Pull acquisition (question → bounded fetch → quarantine scan → evidence
  occurrence + source identity + lineage UNKNOWN_INDEPENDENCE):
  `test_pull_acquisition_produces_evidence_identity_and_unknown_lineage`.
- Injection content → QUARANTINED, trigger suppressed:
  `test_injection_content_is_quarantined_and_never_enters_knowledge`.
- Budget exhausted → WAIT_RESOURCE (pending preserved, không self-increase):
  `test_resource_budget_exhausted_returns_wait_resource_not_silent_skip`,
  `test_byte_budget_bounds_the_fetch_cap_passed_to_fetcher`,
  `test_rate_limited_source_returns_wait_resource`.
- Free API unverified → QUARANTINE (không auto-trust):
  `test_unverified_free_api_host_is_quarantined_and_never_trusted`,
  `test_unreachable_free_api_host_is_quarantined`,
  `test_http_base_url_fails_https_gate`,
  `test_qualification_requires_observable_schema`;
  full chain → `test_full_observed_chain_yields_verified_free_api`.
- Scheduler/policy contracts: `test_curiosity_below_gain_threshold_*`,
  `test_pull_gains_max_and_curiosity_items_are_capped`,
  `test_freshness_window_skips_refetch_explicitly`,
  `test_policy_default_denies_unknown_hosts_and_blocklist_wins`,
  `test_policy_blocklist_overrides_allowlist`,
  `test_policy_rejects_url_with_embedded_credentials`,
  `test_fetch_failure_is_explicit_failed_per_item`,
  `test_request_requires_question_and_urls`, `test_budget_rejects_non_positive_caps`.

Hai bug test mình tự mắc khi chạy đầu tiên (không phải bug product, sản phẩm
đúng thiết kế): (1) quên `max_items=2` cho request 2 URL — scheduler cap về 1
đúng thiết kế; (2) assert `claims == []` sau lần acquire đầu đã TRIGGERED.
Đã sửa test tại điểm lỗi, không hạ chuẩn assertion nào.

## Còn mở / scope hạn chế (PASS ≠ TRUE)

- PASS ở đây = 19 test mới + toàn bộ T03/T00/T02/T06 liên quan xanh trong scope
  hermetic (fake fetcher/prober, egress test môi trường). CHƯA có end-to-end
  ra internet thật (SCP_EGRESS_MODE=deny mặc định) — runtime evidence thật
  thuộc T08/T09 gate, không phải mission này.
- `FreeAPIQualifier` mặc định probe `/` và `/openapi.json`; API có schema path
  khác cần cấu hình `schema_path` (chưa có registry per-API). Auth check hiện
  KHÔNG thể chứng minh "key miễn phí" — 401/403 fail-closed QUARANTINE, đúng
  ý "unknown → không trust", nhưng đồng nghĩa nhiều free-API cần key sẽ phải
  human review (thiên an toàn, chấp nhận trade-off).
- `SourcePolicy` fresh-state và bucket in-memory (per-process); persistence
  đa tiến trình thuộc X03_RESOURCE_GOVERNOR (module khác).
- `inspect_untrusted` là regex baseline v1 — poisoning tinh vi vượt regex
  vẫn phụ thuộc tầng S04/ThreatScanner phía sau (không nằm trong scope M7).
- Chưa wiring vào scpv14 runtime/dashboard (chỉ export qua
  `scp.epistemic`); caller tích hợp cần tự cấp fetcher/prober khi egress mở.
