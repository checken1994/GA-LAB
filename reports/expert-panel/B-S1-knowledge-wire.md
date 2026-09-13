# B-S1 — NỐI WIRE: DomainKnowledgeStore → Judge + /v100/knowledge/stats

- Agent: **B-S1** (no-commit)
- Ngày: 2026-09-13
- Repo: `C:\Users\check\Downloads\scp` — nhánh **không đổi** `audit/runtime-guard-AUDIT-20260909`, HEAD = `d4d8cf0cc503d071d05332a34169caf110422574`
- Snapshot audit nguồn: 52-mảnh @`9ec8d6b` (commit `e0696f5`), mảnh #1 của `reports/expert-panel/ARCH-AUDIT-B-knowledge.md`
- Loại: **WIRE** (không rebuild, không tính năng mới) — sửa đúng điểm đứt được audit pin

## SKILL BINDING (SHA256)

| File | SHA256 |
|---|---|
| `.agents/skills/scp-dna/SKILL.md` | `4aada0be4873598dc50c3a7f38d90151429bb5263c511a838ed1cdcb4d594d10` |
| `.agents/skills/scp-learning-loop-guard/SKILL.md` | `63f651da13f0ff583c4906222ac08ab4a2403280ab90c66450a01d335da7ffef` |

Áp dụng: scp-dna core loop (evidence-first, thay đổi nhỏ có thể đảo ngược, reality-test trước khi report) + scp-learning-loop-guard (Wired Brain: KB ghép vào prompt phải là Context Data bổ trợ, không được thành System Prompt Instruction quyết định; provenance tier/confidence đi kèm từng ref).

## 1. VẤN ĐỀ (chứng thực lại pin của audit)

- `scp/runtime/judge.py:111` (trước patch): `def domain_knowledge_store(self): return None` — property trả `None` cứng.
- Hệ quả dây chuyền, xác nhận bằng đọc code + grep:
  - `/v100/knowledge/stats` và `/v100/knowledge/search` (`scp/api/routes/admin_v100.py:94,104` cũ) luôn `503 "DomainKnowledgeStore not available"`.
  - Judge không bao giờ consult KB khi thẩm định → "hệ thống có tri thức nhưng không dùng" (đúng kết luận audit).
- Ghi nhận thực tế: `data/knowledge/` trên working tree này hiện **TRỐNG** (0 file `.jsonl`) — dữ liệu curation chưa được nạp vào store tại máy checkout này. Wire này nối ĐƯỜNG GỌI; việc nạp data là task khác (xem Giới hạn).

## 2. THAY ĐỔI (diff của riêng B-S1)

### 2.1 `scp/runtime/judge.py` (+87/-2)
- L70: `__init__` thêm `self.knowledge_consult_count = 0` — counter consult.
- L112-131: `domain_knowledge_store` property → **lazy singleton thật**: lần truy cập đầu import + khởi tạo `DomainKnowledgeStore()`; constructor lỗi → log WARNING + trả `None` (fail-closed, judge chạy như cũ). Test/ops có thể pre-seed `judge._kb_store` để inject store riêng (được test dùng).
- L133-163: `_consult_knowledge(question, limit=3)` — gọi `store.search()`;
  - lỗi search → log WARNING + `[]`, KHÔNG raise;
  - counter chỉ tăng khi search hoàn tất không exception (kể cả 0 hit — đo usage thật);
  - mỗi ref: `{question, answer, domain, source, tier, confidence}` — provenance đầy đủ theo scp-learning-loop-guard.
- L165-174: `_inject_kb_refs()` — ghép refs vào `context` dưới marker `[KNOWLEDGE BASE REF]` (Context Data bổ trợ cho cascade ngữ nghĩa, không phải instruction).
- Luồng **sync `judge()`** (L198, L217-220, L268, L285): consult chạy tại bước 2.6 — sau Tier-1/Tier-1.5, TRƯỚC Tier-2 cascade (điểm phân định verdict); refs ghi vào `evidence["knowledge"]` của cả nhánh ESCALATE lẫn PASS/FAIL.
- Luồng **async `judge_async()`** (L309, L327-330, L367, L381): y hệt.

Đảm bảo thiết kế chốt: KB **không quyết định thay verifier** — verdict vẫn do IndependentVerifier + Tier-1 + cascade ngữ nghĩa phân định; KB chỉ bổ trợ evidence. Consult chỉ chạy khi Tier-1 sạch (không nạp KB content vào prompt Tier-1 chặn vì attack).

### 2.2 `scp/knowledge/domain_store.py` (+24/-1)
- L495-522: `stats()` mở rộng, backward-compatible (giữ `total_records`, `domains`, `by_domain`, các `_stats` cũ), thêm:
  - `concepts` (= tổng record active),
  - `sources` (đếm theo nguồn — provenance),
  - `fresh_records` / `stale_records` (đo lúc gọi bằng `is_expired`, vì record có thể hết hạn sau khi load cache).

### 2.3 `scp/api/routes/admin_v100.py` (+11/-1)
- L88-101: `/v100/knowledge/stats` — auth giữ nguyên (`dependencies=[Depends(verify_admin)]` như mọi route khác); sau khi lấy `store.stats()` thêm `judge_consults` = `judge.knowledge_consult_count`. Endpoint không còn 503 vĩnh viễn khi store khả dụng; 503 chỉ khi store thật sự không dựng được (fail-closed giữ nguyên).

### 2.4 Test mới: `tests/T07_learning/test_judge_knowledge_wire.py` (8 test, hermetic)
- (a) sync + async: KB có data → counter tăng, `evidence["knowledge"]` chứa ref đúng (question/source/tier), `[KNOWLEDGE BASE REF]` xuất hiện trong context cascade, verdict vẫn do verifier/cascade quyết định.
- (b) KB empty (0 record, search chạy 0 hit, không inject rác, verdict không đổi); KB search raise (stub store) → không raise, verdict không đổi, counter không đếm; constructor lỗi → property `None`, judge vẫn chạy.
- (a-regression-pin) property trả store THẬT khi constructor khả dụng — kill regression `return None` cứng.
- (c) `/v100/knowledge/stats`: sai token → 401, không token → 401 (deny-by-default như route admin khác); đúng token → 200 với đủ `concepts/total_records/domains/by_domain/sources/fresh_records/stale_records/judge_consults`; store `None` → 503.

## 3. LỆNH CHẠY + KẾT QUẢ (Reality test)

| Lệnh | Kết quả |
|---|---|
| `python -m pytest tests/T07_learning/test_judge_knowledge_wire.py -q` | **8 passed** |
| `python -m pytest tests/T05_gateway/test_judge_sync_crosscheck_alive.py tests/contract/test_judge_verifier_contract.py tests/T04_kernel/test_ask_kernel_adapter_verify.py -q` | **9 passed** (regression judge — bao gồm test pin `fallback_calls == [(Q, A, C)]` nguyên vẹn: KB trống → context không bị biến đổi) |
| `python -m pytest tests/T03_capability/ -q` (gồm `test_flow_09_threat_analysis_scp_standard.py` — file KHÔNG tồn tại ở `tests/T02_contract/`, nó nằm trong T03) | **782 passed, 2 skipped** — 2 skip là skip khai báo sẵn (container evidence opt-in, `test_egress_enforcement.py:540,572`), đã có trong BASELINE_DEBT của T00, không phải skip mới |
| `python -m pytest tests/T02_contract/test_flow_02_ask_chat_scp_standard.py tests/T02_contract/test_flow_03_openai_compat_scp_standard.py tests/T07_learning/ -q` | 93 passed, **1 failed**: `test_ws_chat_fail_closed_when_no_answer_source_available` |
| `python tools/t00_meta_audit.py` | **EXIT=0** — "All integrity checks passed (0 new regressions)" |

### Điều tra 1 fail flow_02 — KẾT LUẬN: pre-existing, KHÔNG do B-S1
- Lỗi nằm ở isolation precondition của chính test: assert gateway chat chain `== []` nhưng máy này có 5 provider enabled (`groq`, …) — assertion chạy TRƯỚC khi chạm judge.
- Chứng minh A/B: tạo `git worktree` tại HEAD sạch `d4d8cf0` (không có thay đổi B-S1), copy `.env` máy, chạy lại đúng test đó → **fail y hệt** cùng assertion. Đã xóa worktree sau kiểm chứng.
- Nguyên nhân gốc: `.env` máy dev chứa API key thật → gateway bật provider → precondition môi trường thất bại. Không thuộc phạm vi file của B-S1 (llm_gateway là CẤM).

## 4. FILE ĐÃ ĐỔI (cho orchestrator commit — riêng B-S1)

```
 scp/api/routes/admin_v100.py      | 12 +++++-
 scp/knowledge/domain_store.py     | 25 ++++++++++++-
 scp/runtime/judge.py              | 87 +++++++++++++++++++++++++++++++++++++++++--
 3 files changed, 117 insertions(+), 7 deletions(-)
?? tests/T07_learning/test_judge_knowledge_wire.py   (test mới, 224 dòng)
```

KHÔNG phải của B-S1 (đang song song/đã có sẵn, orchestrator đừng nhầm):
- `scp/api_server_parts/_ask_impl.py` (+46/-…) — của agent **C-S2** (giữ nguyên, không đụng).
- `tests/T02_contract/test_ask_world_state_hook_cs2_scp_standard.py` — của C-S2.
- `bench_sha.txt`, `reports/SCP_FULL_RUNTIME_RAG_1000_RETRY_V3_2026-08-17.jsonl` — untracked có sẵn từ đầu session.
- Không `git add`/`git commit` gì — working tree nguyên trạng cho orchestrator.

## 5. GIỚI HẠN (scope + evidence limits — DNA #22, #23)

1. **PASS ≠ hệ thống hoàn chỉnh**: verdict PASS chỉ trong phạm vi test đã chạy (unit/integration hermetic); KHÔNG chạy live server, KHÔNG chạy benchmark recall, KHÔNG test E2E `/ask` thật — mức bằng chứng đạt Integration, không phải End-to-end.
2. **`data/knowledge/` hiện trống** trên máy này → judge consult trả 0 hit trong prod-at-this-checkout cho tới khi có pipeline nạp data (curation 5-nguồn của audit mảnh #2 — task khác). Wire là điều kiện cần, chưa là điều kiện đủ cho "KB sống" về dữ liệu.
3. Chưa nối `phase1_kb_retrieval.py` / `phase9_claim_extraction.py` (judge_parts — kiến trúc judge cũ không còn chạy trong RealityJudge mới); audit chỉ yêu cầu nối judge.py:111 — đúng phạm vi "không rebuild".
4. `FastLearningEngine` ghi `data/v13.db` nhưng KB domain_store đọc `data/knowledge/*.jsonl` — hai kho chưa migrate với nhau (open question #2 của audit gốc, không thuộc slice này).
5. Comment stale tại `scp/brain/brain.py:25` ("LIVE in /ask via judge.py") giờ mới đúng lại, nhưng file không thuộc phạm vi cho phép nên không sửa.
6. Counter `knowledge_consult_count` là in-memory per-judge-instance (không persist) — restart mất bộ đếm; nhất quán với `judged_count` hiện có.
7. Rate-limit auth (5 fail/60s) là behavior chuẩn của `verify_admin` — test (c) reset state để hermetic; không thay đổi auth posture.

## OPEN QUESTIONS
1. Ai nạp dữ liệu curation vào `data/knowledge/` (scheduler/lifespan) và có cần migrate `data/v13.db` sang domain_store? (audit mảnh #2 + TODO lifespan tại `domain_store.py:370-382` chưa có owner gọi).
2. Việc precondition môi trường của `test_flow_02` (yêu cầu .env không có key) có cần ghi vào baseline-debt harness để CI khác máy không fail lăn đ-order? — để Agent harness quyết (tương tự open question #3 của audit B).
