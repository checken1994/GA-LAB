# MC-GREEN-3 — M13 Data sources & Learning (closure, resume)

- Ngày: 2026-09-11 (session resume sau khi tien nhiem MC-GREEN chet giua chung do provider error)
- Nhánh: `audit/runtime-guard-AUDIT-20260909`; HEAD đầu session `8c7f522`; pin cuối: `76b7624`
- Skills bắt buộc đã đọc đầu session (SHA256 trong `M13-closure.json`): scp-dna + scp-runtime-audit + scp-reality-verifier + scp-release-evidence-gate

## Tái sử dụng evidence của tiền nhiệm

D1 (27P @8c7f522) + D2 (build/recreate/health @8c7f522, image manifest `091c03a9…` khớp build log) đã kiểm tra độ tươi: khớp HEAD đầu session → TÁI DỤNG, không re-run. D3 của tiền nhiệm chạy trên container :8011 (ID `d04952…`) KHÔNG còn tồn tại khi resume (container `scp-scp-api-1` hiện tại là `59179611a9db`, core-profile, không serve v104) → D3 được CHẠY LẠI hoàn toàn trên container ephemeral full-profile mới, provenance mới.

## Phát hiện lớn

1. **PRODUCT_FAIL — `/v104/learn/consolidate` chết 500 vĩnh viễn** (probe-proven): handler gọi `consolidate_unverified()` không tồn tại (KnowledgeConsolidator đã bị thu nhỏ về minimal stub; route không được cập nhật theo). flow_13 suite không chạm endpoint này → D1 xanh vẫn lọt. Fix `76b7624` + test pin `[LEARN-9]` (27P → 28P exit 0). Payload sau fix khai báo trung thực `ok_stub_noop` — không trả "ok" thuật (anti-placebo).
2. **Egress deny KHÔNG được enforce cho urllib** (falsify giả định): trong container `SCP_EGRESS_MODE=deny`, `example.com` → HTTP 200, GitHub trả HTTP response, AttackCrawler crawl được 34 attacks, top-systems fetch thật GitHub+Wikipedia (records=3). Mở rộng gap chung M12 G1.
3. **Main deployment core-profile không serve v104** (404) — least-surface có tính; runtime proof M13 trên container ephemeral full-profile (methodology M11/M12).
4. **Rate limiter thật**: 5 auth-fail/60s/IP → 429 cho cả request admin hợp lệ cùng IP.
5. `docker compose build` không nhận `SCP_GIT_SHA` từ shell env (phải `--build-arg` tường minh) — nếu không, image ENV = "unknown" và health commit không khớp pin.

## Kết luận

`CLOSED_WITH_KNOWN_GAP` tại pin `76b7624` — chi tiết D0–D8, root cause, known_gaps (G1–G8) và falsification_status: `M13-closure.json`. Không đọc thành "learning pipeline production đầy đủ": consolidator vẫn là stub (G2), egress chưa enforce (G1), external learn mới probe bounded (G4).
