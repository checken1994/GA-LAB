# SCP Free-API Knowledge Warehouse & TOP-1% Learning Loop — 2026-08-29

## Bối cảnh

SCP không có ngân sách API trả phí để so sánh trực tiếp với các hệ thống
TOP 1%. Thay thế trung thực nhất: dùng **kho tri thức free của Internet**
làm kho dữ liệu, học từ đó để cải tiến code và logic. Cùng ngày, local
Ollama đã bị xóa khỏi deployment — toàn bộ LLM call đi qua OpenRouter API
(xem `scp/llm_gateway/client.py`, thay đổi "-585 dòng dead code").

## Hai thành phần mới

### 1. Free API Catalog — `scp/data_sources/free_api_catalog.py`

Kho API free toàn cầu lấy từ repo công khai
[`public-apis/public-apis`](https://github.com/public-apis/public-apis)
(bản curated cộng đồng):

- **1.689 API entry, 51 category, 785 API free không cần key** (đo thực tế
  trên file catalog thật tại thời điểm triển khai).
- Parser thuần (`parse_catalog_md`) — xử lý cả 2 dạng header của README
  gốc (bảng đầu có pipe đầu dòng, các bảng sau bỏ pipe), bỏ qua bảng
  sponsor. Hermetic-testable, không cần mạng.
- Cache durable tại `data/free_api_catalog.json` kèm `raw_sha256` + TTL
  (`SCP_FREE_API_CATALOG_TTL_SEC`, mặc định 24h).
- Fail-closed: refresh lỗi → trả `{"ok": false}` và phục vụ cache; không
  bao giờ bịa entries.
- SSRF-safe by construction: chỉ fetch đúng 1 host cố định trong
  `ALLOWED_HOSTS`; URL không bao giờ đến từ user input.
- Egress opt-out: `SCP_TOP_SYSTEMS_EGRESS=0` → tắt mạng, chỉ dùng cache.

### 2. TOP-1% Learning Loop — `scp/core/top_systems_learning.py`

Vòng học thu thập kiến thức về thực hành của các hệ thống hàng đầu theo 8
chủ đề trùng với trụ cột kiến trúc của SCP: `agent_runtime`, `agent_kernel`,
`llm_evaluation`, `llm_redteam`, `sandboxing`, `evidence_audit`,
`rag_verification`, `observability`.

- Nguồn: GitHub Search API (repo tốt nhất theo stars) + Wikipedia API
  (nền tảng khái niệm). Chỉ 2 host cố định trong `ALLOWED_HOSTS`.
- Ledger durable `data/top_systems_knowledge.jsonl`, mỗi record có
  `source`, `url`, `stars`, `topic`, `collected_at` (provenance đầy đủ).
- `advise(query)` — API tra cứu cho con người và các tầng WHY/autofix.
- Per-topic isolation: 1 nguồn lỗi không làm chết vòng học.
- Rate-limit trung thực: GitHub unauthenticated 60 req/h → 1 vòng full
  8 topic = 16 request.

## API surface (đều yêu cầu admin auth `verify_admin`)

| Method | Path | Chức năng |
|---|---|---|
| GET | `/v104/learn/top-systems/status` | Số record, topics, catalog count |
| POST | `/v104/learn/top-systems` | Chạy 1 vòng học (bounded) |
| GET | `/v104/learn/top-systems/advise?query=` | Tra cứu kiến thức đã học |
| GET | `/v104/free-apis/search?query=&category=&auth=No` | Tìm API free |

## Bằng chứng thực tế (2026-08-29, tự chạy)

- Catalog refresh thật: `{"ok": true, "served": "network", "count": 1689}`.
- `learn_all()` thật: 75+ records trên 8 topics; ví dụ `advise("rag
  verification")` chỉ ra `infiniflow/ragflow` (89.5k★),
  `ruvnet/ruflo` (69.6k★), `SciPhi-AI/R2R` (8k★).
- E2E qua HTTP thật: cả 4 endpoint trả kết quả đúng (status/search/advise/POST).
- Gates: **pytest 142 passed, 1 skipped** · **reality 75/75** (gồm
  `reality_4-e-001.py` mới) · **pre_push_gate.ps1: PASS**.

## Unit tests (hermetic — không mạng)

- `tests/test_free_api_catalog.py` (6 tests): parser 2 dạng header, bỏ
  sponsor, search filters, cache roundtrip, fail-closed, allowlist.
- `tests/test_top_systems_learning.py` (6 tests): ledger + provenance,
  per-topic isolation, unknown topic, advise, allowlist, topic coverage.

## Giới hạn được khai báo trung thực

- "TOP 1%" ở đây là **tri thức tham chiếu** (hệ thống nhiều sao, khái niệm
  chuẩn mực), KHÔNG phải benchmark so sánh hiệu năng trực tiếp.
- GitHub search unauthenticated có rate-limit; vòng học cần scheduler
  Gentle interval (chưa wire vào scheduler — việc tiếp theo).
- Catalog phản ánh nội dung repo public-apis tại thời điểm fetch.
