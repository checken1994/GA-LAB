# S21 — Hedged LLM Race (10s attempt deadline, first-result-wins, cap 90s)

Ngày: 2026-09-13 · Worker: S21 · Nhánh: `audit/runtime-guard-AUDIT-20260909` (KHÔNG đổi) · Base HEAD: `433dcea` · Commit code: **`41f2135`**
Owner directive (verbatim ý): **"khi LLM trả kết quả chậm khoảng 10s -> chuyển sang LLM khác hoặc API khác"**

## 1. Bối cảnh và vấn đề

- Baseline `bench_final_seed99.json`: latency mean **85.6s** / p95 **260s** (free-tier).
- Chain failover hiện tại là **TUẦN TỰ** (`LLMGateway.chat` — `for provider in rotation: await provider.chat(...)`):
  provider đầu chậm 30–260s chặn toàn bộ /ask trong khi các provider khác rảnh.
- S20 (lease heartbeat) giữ lease SỐNG khi provider chậm; S21 làm /ask NHANH đi bằng
  cách bắn provider khác SONG SONG. Hai cơ chế **bổ trục** (heartbeat giữ authority,
  hedge rút ngắn thời gian chờ), không thay thế nhau.

## 2. Seam chọn (AUDIT-FIRST)

Đọc `scp/llm_gateway/client.py` trước khi sửa: `chat_sync` (wrapper sync),
`LLMGateway.chat` (failover loop + provider chain), `OpenRouterProvider.chat/_call_model`
(retry 3×2 + breaker + key rotation), crosscheck.

| Điểm | File:line (sau sửa) | Lý do |
|---|---|---|
| **Seam chính** | `scp/llm_gateway/client.py:682` `LLMGateway.chat()` — dispatch tại :721 | Vòng `for provider in rotation` tuần tự là đúng chỗ provider chậm chặn mọi thứ; đây là tầng duy nhất nhìn thấy TOÀN BỘ chain → hedge theo `_provider_chain(task)` sẵn có, không đảo thứ tự, không thêm provider mới |
| Tuần tự gốc | `client.py:731` `_chat_sequential()` | Body loop cũ di chuyển NGUYÊN VẸN (diff: 0 deletions) — `SCP_LLM_HEDGE=off` hoặc chain 1 provider quay về hành vi cũ bit-for-bit |
| Hedge race | `client.py:759` `_chat_hedged()` | Race asyncio: attempt deadline per provider, first-result-wins, cap tổng, cancel chỉ ở dọn dẹp |
| Env parse | `client.py:56` `_parse_positive_seconds` + `:69` `_hedge_settings` | Fail-closed: lỗi/0/âm/non-finite → default (10/90); kill-switch `SCP_LLM_HEDGE=off` |
| Compose | `compose.yml:47-53` | 3 env mới pattern `${VAR:-default}` (giống S20), không sửa gì khác trong compose |

**Vì sao KHÔNG đụng crosscheck 2-family:** `scp/runtime/multi_llm_crosscheck.py:21,93`
tự iterate `gateway._provider_chain` và gọi `provider.chat()` TRỰC TIẾP — không đi qua
`LLMGateway.chat()`. Hedge nằm trong `gateway.chat()` nên crosscheck/judge **không bị
ảnh hưởng theo cấu trúc** (đã xác nhận bằng đọc code + runtime log `[MULTI-LLM]` vẫn chạy).
`_provider_chain` không đổi.

## 3. Thiết kế đã cài (đúng spec chốt, không tự design lại)

1. **Attempt deadline** `SCP_LLM_ATTEMPT_TIMEOUT_SECONDS` (default **10**): provider đầu
   chạy; quá deadline → bắn provider kế tiếp trong chain vào race **SONG SONG**
   (`loop.create_task`), KHÔNG cancel provider đang chạy.
2. **First-result-wins**: answer thành công đầu tiên của bất kỳ provider nào → trả ngay
   kèm `provider` label; tie-break deterministic theo thứ tự chain khi nhiều task về cùng
   một lượt `asyncio.wait`. Các task còn lại bị cancel ở bước **dọn dẹp** (`finally`) —
   SAU khi winner đã được lấy kết quả (an toàn, không double-spend vô nghĩa).
3. **Cap tổng** `SCP_LLM_HEDGE_MAX_SECONDS` (default **90**): quá cap → fail-closed
   `(None, "hedge_cap_exceeded")` + log ERROR rõ, cancel sạch — không chờ vô hạn.
4. **Provider LỖI (không chậm)** vẫn failover NGAY sang kế tiếp (giữ ngữ nghĩa tuần tự
   giữa các lỗi; hedge song song chỉ dành cho provider CHẬM). Mỗi provider chỉ 1 hedge
   attempt (`next_idx` monoton); retry logic cũ giữ nguyên trong `provider.chat()`.
5. **Telemetry**: log INFO `[S21 HEDGE] fire:` (provider chậm + provider được bắn) và
   `[S21 HEDGE] race won by`; counters `hedge_fires`/`hedge_wins`/`hedge_caps` + `failover_count`
   trong **cùng `_stats` store hiện có** (không chế store mới).
6. **Không phá**: egress guard + breaker + Z2/Z3 zero-cost vẫn chạy TRONG mỗi
   `provider.chat()` (mọi attempt qua choke — hedge chỉ thêm scheduler, không bỏ qua lớp nào);
   zero-cost opt-in short-circuit không đụng (0 dòng thay đổi trong zero_cost_runtime.py).
7. **Env parse fail-closed**: `"abc"/""/"0"/"-5"/"nan"/"inf"` → default; kill-switch
   `SCP_LLM_HEDGE ∈ {off,0,false,no}` (case-insensitive) → tắt hoàn toàn.

Ràng buộc tôn trọng: KHÔNG sửa `ask_kernel_adapter.py`, `taskkernel*`, `zero_cost_runtime.py`,
`.env`, `GA.md`, `spec/`. Diff thật: `client.py` +209/-0 (loop cũ chỉ DỜI sang
`_chat_sequential`, text giữ nguyên), `compose.yml` +7, test mới +260.

## 4. Test results (hermetic, FA-01 — fake provider in-process, T05 chặn network)

File: `tests/T05_gateway/test_hedge_latency.py` — 17 test:

| # | Contract | Kết quả |
|---|---|---|
| a | A chậm quá deadline → B bắn song song, B thắng; `elapsed < sleep(A)`; event `fastB:answered` TRƯỚC `slowA:cancelled` (A không bị hủy trước khi B thắng) | PASS |
| b | A trả sau deadline nhưng trước B → vẫn nhận A (`firstA:model`), B đã được bắn (`hedge_fires==1`), B chỉ hủy sau | PASS |
| c | Cả hai quá cap → `(None, "hedge_cap_exceeded")`, elapsed < 9s (không treo), cả hai bị cancel sạch, `hedge_caps==1` | PASS |
| d | `SCP_LLM_HEDGE=off` → max concurrency == 1, event tuần tự `A:start,A:end,B:start,B:end`, `hedge_fires==0` | PASS |
| e | Env parse: 8 giá trị lỗi → default (10/90); valid 2.5/45; unset → default; kill-switch 5 giá trị off / 5 giá trị on; behavioral: deadline `0` → default 10s (không fire oan, failover lỗi vẫn NGAY) | PASS |
| f | Telemetry: log fire có `slowA` + `quickB`, log `race won by quickB`, stats fires/wins | PASS |
| + | `first_provider_won` đường lành: provider đầu nhanh → không fire, không hủy ai | PASS |

| Suite | Kết quả | Exit |
|---|---|---|
| `tests/T05_gateway/test_hedge_latency.py` | 17 passed (4.67s) | 0 |
| `tests/T05_gateway/` | **68 passed** (8.03s) | 0 |
| `tests/T02_contract/test_flow_02_ask_chat_scp_standard.py` + `tests/T07_learning/test_chat_multimodal_contract.py` + `tests/T09_golden_task/test_e2e_scp_complete.py` | 40 passed, 1 failed | — |
| `tools/t00_meta_audit.py` | All integrity checks passed (0 new regressions) | 0 |
| `tools/verify_scp_test_skill_contract.py` | PASS_WITHIN_SCOPE | 0 |

### T02 flow02 — 1 FAIL pre-existing, KHÔNG do diff S21 (A/B evidence)

`test_ws_chat_fail_closed_when_no_answer_source_available` FAIL với assertion
`['groq','cerebras','nvidia'] == []` — precondition `_disable_openrouter` không clear
`SCP_LLM_FALLBACK_PROVIDERS` + key groq/nvidia trên .env máy này. **A/B: `git stash`
diff S21 → chạy trên HEAD sạch `433dcea` → FAIL Y HỆT** (1 failed in 2.32s) → pre-existing,
environment-dependent, trùng finding đã ghi trong report S20d. Không phải regression của S21.

## 5. Runtime proof (Docker, LLM thật, default env — KHÔNG cần override 3s)

`docker compose build scp-api` → Built · `up -d` → `/health` 200 sau ~10s · token mint
TRONG container (không in token, không in secret).

POST /ask 3 câu thật (auth Bearer, task=chat):

| Câu | wall_s (client) | server elapsed_ms | LLM generation | Hedge? |
|---|---|---|---|---|
| "Giai thich ngan gon: hedged request la gi?" | 49.95 | 33 194 | race won **20.64s** (`first_provider_won=False`) | **CÓ** — fire thật |
| "Viet ham Python kiem tra so nguyen to" | 19.96 | 17 461 | race won **6.87s** (`first_provider_won=False`) | failover-lỗi ngay (provider đầu chết nhanh) |
| "2 cong 2 bang may?" | 16.47 | 13 265 | race won **8.15s** (`first_provider_won=False`) | failover-lỗi ngay |

So baseline mean 85.6s / p95 260s: cả 3 câu đều thấp hơn mean nhiều; không câu nào phải
dùng override `SCP_LLM_ATTEMPT_TIMEOUT_SECONDS=3` vì hedge đã fire với default 10s.

Hedge events từ `docker compose logs scp-api` (tổng cả phiên): **14 fire, 28 race-won, 0 cap**.
Fire tiêu biểu (provider chậm quá deadline 10.0s → bắn song song):

```
15:09:02,498 INFO [S21 HEDGE] fire: openrouter chưa trả sau deadline 10.0s → bắn thêm cerebras (chain idx 1) vào race song song
15:09:37,497 INFO [S21 HEDGE] fire: openrouter chưa trả sau deadline 10.0s → bắn thêm groq (chain idx 5) vào race song song
15:09:44,690 INFO [S21 HEDGE] race won by openrouter:openrouter/free sau 20.64s (first_provider_won=False, hedge_fires=14)
15:09:44,691 INFO [CHATBOT] LLM (openrouter:openrouter/free) generated answer: Hedged request là một hình thức ...
```

Fail-closed khi cả chain chết (free-tier quota cạn — đúng thiết kế, không treo):

```
15:09:27,027 ERROR [S21 HEDGE] tất cả provider trong race đều lỗi: gemini: none; cerebras: none; sambanova: none; nvidia: none; groq: none; openrouter: none
```

Zero-cost/breaker/egress intact: log còn thấy `cerebras: waiting_free_quota` (Z3 verdict),
mọi attempt đi qua PEP (T05 test (a–f) chạy dưới `SCP_LLM_COST_MODE=free_only` + network
guard — vẫn xanh).

**Verdict PASS-within-scope**: cơ chế hedge hoạt động trong runtime thật với default env;
provider chậm >10s được hedge song song và race thắng bởi provider hedged; không có cap hit;
không treo; fail-closed đúng khi hết provider.

## 6. Giới hạn và câu hỏi mở (DNA #22–#25)

1. **Verdict /ask = FAIL trong phiên proof** do crosscheck `missing_distinct_providers`
   (secondary family trả `none` — quota free-tier cạn hôm nay). LLM generation THÀNH CÔNG
   (log `[CHATBOT] ... generated answer`). Crosscheck đi đường riêng (bypass gateway.chat)
   nên KHÔNG phải do hedge; nhưng hedge **có thể** đốt thêm quota free-tier song song
   (double-spend trong lúc chờ) → gián tiếp làm secondary family dễ cạn hơn. Chưa có
   bằng chứng định lượng — cần A/B quota trước/sau nếu owner muốn khắc (hướng: loại
   cùng-family khỏi race hoặc reserve quota cho judge).
2. `first_provider_won=False` ở cả 3 câu nghĩa là rotation đầu (rr) không thắng — đúng
   ngữ nghĩa, nhưng cho thấy rr start không ưu tiên provider nhanh; chưa đo tỉ lệ
   hedge-win dài hạn (chỉ 14 fires/1 phiên).
3. Fire event có thể log trễ vài giây so với deadline lý thuyết khi event loop đang
   nghẽn (quan sát 15:09:37 so với start kỳ vọng 15:09:34) — deadline KHÔNG bao giờ
   fire sớm; trễ là hạn chế của scheduler 1 loop, không phá cap (cap tính từ start thật).
4. `SYNC_CALL_TIMEOUT_SECONDS=90` == cap default 90: chat_sync đường thread-pool có thể
   timeout trước khi cap kịp fail-closed sạch. Giữ nguyên theo spec (cap=90 do owner chốt);
   nếu muốn an toàn hơn có thể hạ cap hoặc nâng SYNC timeout ở task riêng.
5. PASS chỉ có nghĩa "không thấy lỗi trong phạm vi test + 1 phiên runtime đã nêu" —
   không claim production-ready.

## 7. Skill bindings (SHA256, bắt buộc append)

- `.agents/skills/scp-dna/SKILL.md`
  `4aada0be4873598dc50c3a7f38d90151429bb5263c511a838ed1cdcb4d594d10`
- `.agents/skills/scp-gateway-resilience/SKILL.md`
  `b60e8eb3a2d2c9de971a001924019cfa0b3038f9c96dfa4e3ac1cb8fca750a5a`

Gateway-resilience mapping: hedge race bổ sung "Circuit Breaker / Retry" cửa ngõ bằng
**song song hoá fallback** thay vì chờ tuần tự — breaker + egress + Z2/Z3 vẫn là authority
trên từng attempt; fallback privacy không đổi (chain không thêm provider mới).
