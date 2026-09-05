# M5 — Immutability Enforcement Progress Log

Expert: M5 (epistemic immutability) — branch `experts-4.0.3-434green` (base c298dad).
Scope: complete append-only enforcement on ALL epistemic tables + keyed record_hash + record_proof HEAD binding.
Off-limits (other experts): `scp/autofix/`, `scp/task_kernel*`, `tests/T04_kernel/`, `tests/T09_golden_task/`.

## Reality check trước khi sửa (evidence-first)

- Audit gap #1 đã **stale một phần**: `world_assertions_no_delete` ĐÃ tồn tại
  (`scp/world_state/temporal_authority.py:47`) và T09 golden test đã expect raise "append-only".
  Không cần sửa world_assertions; chỉ bổ sung regression test ở T02.
- FoundationDB (`scp/persistence/db.py:65-79`) checksum từng migration: **sửa list
  migration đã applied sẽ BLOCK startup (fail-closed)**. Vì vậy mọi trigger mới phải là
  migration MỚI (`0002_*`/`0003_*`), không được sửa list `0001_*`.
- Runtime DB thật tồn tại: `data/foundation/epistemic.sqlite` (135 MB) với record_hash
  plain `sha256:` → HMAC phải **opt-in** (param > env `SCP_EVIDENCE_HMAC_KEY`), không
  auto-key, kèm scheme-dispatch fail-closed (store keyed từ chối record_hash unkeyed).
- `sources` có UPDATE hợp lệ (`last_observed_at` advance trong `register()`), nên chỉ
  chặn DELETE, không chặn UPDATE.
- Không có code path nào DELETE các bảng epistemic (grep toàn repo: chỉ
  `live_knowledge_cache` và 2 test ngoài scope — T09 đã expect raise).

## Thay đổi

- [x] `scp/epistemic/evidence_store.py`:
  - migration `0002_evidence_append_only`: trigger `*_no_delete` cho `evidence`,
    `content_blobs`, `evidence_links` (loại trừ lifecycle: `evidence_payload_state`,
    `retention_events` theo mission).
  - HMAC record_hash opt-in: `hmac_key` param > env `SCP_EVIDENCE_HMAC_KEY` > plain
    sha256 (backward compatible). Prefix `hmac-sha256:`; `derive_repo_identity_key()`
    cho key suy từ repo identity (documented: defense-in-depth, KHÔNG phải trust root).
  - `verify_integrity()` scheme-dispatch fail-closed.
- [x] `scp/calibration/ledger.py`: migration `0002_calibration_append_only`
  (`calibration_predictions_no_delete`, `calibration_resolutions_no_delete`).
- [x] `scp/self_model/capability_map.py`: migration `0002_capability_proofs_append_only`
  (`capability_proofs_no_delete`, `self_model_blindspots_no_delete` — blindspots không
  thuộc lifecycle trừ hai bảng được mission loại trừ).
- [x] `scp/epistemic/source_identity.py`: migration `0003_sources_append_only`
  (`sources_no_delete`; UPDATE last_observed_at vẫn hợp lệ).
- [x] `scp/world_state/temporal_authority.py`: migration `0003_identity_links_immutable`
  (`identity_links_no_update` + `identity_links_no_delete` — trước đây KHÔNG có trigger nào).
- [x] `record_proof` hardening: tested_sha phải == `git rev-parse HEAD` của repo chứa
  reference spec, trừ khi `archived=True` (override tường minh cho proof lưu trữ);
  metadata evidence phải khai báo `capability_id` khớp capability được chứng minh.
  Git unavailable → fail-closed ValueError.
- [x] Tests mở rộng: test_evidence_store.py (DELETE rejection + HMAC tamper + scheme
  dispatch + env key), test_calibration_ledger.py, test_self_model_capability_map.py
  (real HEAD sha, archived override, capability_id mismatch, DELETE), 
  test_source_identity_lineage.py, test_world_state_temporal_contract.py.

## Kết quả test (đã chạy thật, exit 0)

- `python -m pytest tests/T06_verifier/ tests/T02_contract/test_foundation_db.py -q`
  → **53 passed** (bao gồm 12 test M5 mới).
- `python -m pytest tests/T00_integrity/ -q` → **63 passed**.
- Kiểm tra lan tỏa (các test khác import module bị sửa):
  `tests/T02_contract/test_world_state_temporal_contract.py` +
  `test_knowledge_control_db.py` → 13 passed; `test_doubt_engine.py` +
  `tests/T03_capability/test_privacy_write_gate.py` +
  `tests/T05_gateway/test_zero_cost_guard.py` → 11 passed.

### Harness fix trong quá trình chạy (giữ/tăng strictness, không hạ chuẩn)

- `tests/T02_contract/test_doubt_engine.py`: fixture gọi `record_proof` với sha
  giả `"abc1234"` + metadata thiếu `capability_id` → sau khi harden API, fixture
  ĐÃ bị fail (đúng thiết kế fail-closed). Fix harness: dùng sha thật từ
  `git rev-parse HEAD` và thêm `capability_id` vào metadata — fixture giờ đi
  qua đúng đường validation thật, không có assertion nào bị nới lỏng.
- `test_self_model_capability_map.py`: các test dùng sha giả được viết lại để
  dùng HEAD thật hoặc `archived=True` tường minh cho proof lịch sử.
- Ghi đúc thực tế: pytest basetemp nằm TRONG repo (`reports/pytest-basetemp/`)
  nên `git config remote.origin.url` trả cùng identity cho mọi path con — test
  derive-key đã sửa để dùng thư mục ngoài repo.

## Commit

- Local commit trên `experts-4.0.3-434green`, prefix `featM5(immutability):`,
  KHÔNG push. `AI_SHARED_BOARD.md` bị sửa bởi luồng khác trong working tree →
  cố tình KHÔNG stage (ngoài scope M5).

## Open questions / remaining scope

- `self_model_blindspots` có lifecycle `status` (OPEN/MITIGATED/CLOSED) nhưng hiện chưa
  có API cập nhật status; chỉ chặn DELETE, không chặn UPDATE.
- Keyed-store migration: bật `SCP_EVIDENCE_HMAC_KEY` trên DB legacy sẽ fail-closed toàn
  bộ row unkeyed cũ (cố ý, fail-closed); cần cutover có chủ ý.
- "kind field matching the capability" trong mission được hiện thực là metadata
  `capability_id` trên evidence (evidence `kind` enum là loại quan sát, không phải capability).
- PASS chỉ có nghĩa: không thấy lỗi trong scope test đã nêu.
