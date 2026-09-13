# S22 — Secondary provider family không đóng góp cho judge crosscheck

- Worker: S22 | HEAD before: `283fb52` | Ngày: 2026-09-13
- Skills: `scp-dna` + `scp-gateway-resilience` (SHA256 cuối file)
- Scope: accuracy blocker — 26/26 crosscheck `consensus=missing_distinct_providers final=None`
  khiến mọi /ask bị withhold (`failures=[verdict_pass, judge_pass, governance_uphold]`).

## 1. Vấn đề

`scp/runtime/multi_llm_crosscheck.py` cần ≥2 provider family trả verdict parseable.
Runtime log trước fix: `primary(openrouter:nvidia/nemotron...)=PASS|FAIL secondary(none)=None
consensus=missing_distinct_providers` — chỉ openrouter sống, mọi family phụ im lặng.

## 2. Chuỗi "Tại sao" + giả thuyết kiểm chứng

| Giả thuyết | Bằng chứng | Kết luận |
|---|---|---|
| (a) NVIDIA chết | `_call_model` trực tiếp: `HTTP 429 Too Many Requests`; model `deepseek-ai/deepseek-v4-flash-0731` vẫn nằm trong `/models` (82 model, HTTP 200) | Rate-limit/quota — KHÔNG phải cấu hình |
| (b) Groq/Cerebras key lỗi | Groq `/models` HTTP 200 (key sống), chat `llama-3.1-8b-instant` → 404 `model_not_found`; Cerebras `/models` 200, chat `gpt-oss-120b` → 402 | Groq: model chết; Cerebras: quota |
| (c) `_parse_verdict` không parse được | Các family phụ KHÔNG trả lời được gì (404/402/429 → answer None); `_parse_verdict` regex `\b(PASS|FAIL)\b` lấy match cuối — với "The answer is PASS." vẫn parse đúng | SAI — parse không phải nguyên nhân |
| (d) Chain judge thiếu groq | `gw._provider_chain('judge')` = `[openrouter, groq, cerebras, sambanova, gemini, github(disabled), nvidia]` — groq CÓ trong judge chain, `enabled=True` | SAI — chain đầy đủ |

## 3. Chẩn đoán từng provider (container probe 2026-09-13, prompt "Q: Is 2+2=4? Output only PASS or FAIL.")

| Family | Enabled | Raw answer 40 ký tự | Label/parse | Root cause |
|---|---|---|---|---|
| openrouter (judge) | True | `'PASS'` (qua free fallback `nvidia/nemotron-3-super-120b-a12b:free`) | parse=PASS | OK. Paid primary `anthropic/claude-3-5-sonnet` → 404 (model biến mất), fallback sống; mỗi call fail-over ~0.5s, breaker không tích lũy (record_success mỗi fallback) |
| groq | True | `''` | label=`none`, parse=None | **404 model_not_found**: `llama-3.1-8b-instant` không còn tồn tại (list /models 14 model: chỉ còn `openai/gpt-oss-20b`, `openai/gpt-oss-120b`, `groq/compound`, qwen3.x…). Key còn sống (401/403 không xuất hiện). Verified: `openai/gpt-oss-20b` → HTTP 200, answer `PASS` |
| cerebras | True | `''` | label=`waiting_free_quota` | **402** quota/rate-limit (model `gpt-oss-120b` vẫn hợp lệ trong /models) — external, không sửa bằng config |
| sambanova | True | `''` | label=`waiting_free_quota` | **402** quota — external |
| gemini | True | `''` | label=`none` | **404**: "models/gemini-2.5-flash is no longer available to new users. Please update your code to use models/gemini-3.6-flash". Verified: `gemini-3.6-flash` → HTTP 200, answer `PASS` |
| github | False | n/a | disabled | Không có key (`GITHUB_TOKEN` rỗng) + `GITHUB_MODEL` rỗng — owner quyết, không đụng key |
| nvidia | True | `''` | label=`waiting_free_quota` | **429 Too Many Requests** (model hợp lệ) — external rate-limit |

Quan sát phụ (ngoài scope, ghi nhận): Z3 `install_free_only_provider_router` (zero_cost_runtime.py)
ghi đè `chat()` trên `OpenRouterProvider` và kế thừa xuống `EnvCompatProvider` VÔ ĐIỀU KIỆN
(label `waiting_free_quota` là bằng chứng); cost-wall (`SCP_LLM_COST_MODE=free_only`) thì opt-in.
`free_catalog` refresh fail do `enforce_egress_policy` generic dùng `SCP_EGRESS_ALLOWLIST`
trong khi deployment chỉ đặt `SCP_LLM_EGRESS_ALLOWLIST` — không ảnh hưởng crosscheck
(catalog chỉ dùng cho pricing proof), để dành cho session sau.

## 4. Root cause

**Cấu hình model names trong `.env` trỏ tới model đã chết ở 2/2 family phụ có key sống**
(groq: model bị loại khỏi catalog; gemini: nhà cung cấp chủ động retire cho user mới),
kết hợp 3 family còn lại ở trạng thái external quota/rate-limit (cerebras 402, sambanova 402,
nvidia 429). Không phải lỗi chain, không phải lỗi parse.

## 5. Fix tại điểm lỗi (nhỏ, đảo chiều được)

`.env` (deployment config, gitignored, KHÔNG đụng key):

```diff
-GROQ_MODEL=llama-3.1-8b-instant
+GROQ_MODEL=openai/gpt-oss-20b
-GEMINI_MODEL=gemini-2.5-flash
+GEMINI_MODEL=gemini-3.6-flash
```

Cả hai model name được verify trước khi ghi (HTTP 200 + answer `PASS` từ chính provider,
không bịa model). Code production không đổi; fail-closed giữ nguyên.

Test hermetic mới (`tests/T05_gateway/test_multi_llm_crosscheck.py`, `DeadProvider`
mô phỏng đúng shape production `chat → (None, label)`):
- `test_cross_verify_dead_family_does_not_block_later_live_families` — family chết
  (label `none`) không chặn vòng lặp; 2 family sống đạt consensus; attempt record
  giữ family chết với verdict None (audit không bịa); family thứ 3 không bị gọi.
- `test_cross_verify_erroring_family_does_not_block_later_live_families` — family
  lỗi (label `error:HTTPStatusError`) tương tự, consensus FAIL/FAIL vẫn là FAIL thật.

## 6. Reality check

- `tests/T05_gateway/ -q`: **70 passed**.
- `tests/T02_contract/ -q` (deselect 1 test RED environmental đã duyệt):
  **156 passed, 1 deselected**.
- `tools/t00_meta_audit.py`: exit 0 ("All integrity checks passed, 0 new regressions";
  warning L4 CODEOWNERS local-only cho test file — ruleset server-side là authority).
- `tools/verify_scp_test_skill_contract.py`: exit 0, `PASS_WITHIN_SCOPE`.
- Runtime proof (Docker, `docker compose build scp-api && up -d`, /health 200):
  - Q "What is 17*23?" → `verdict=PASS, governance=UPHOLD`, answer `Kết quả của 17 * 23 là 391.`
  - Q "What is the capital of Japan?" (lần 2) → `verdict=PASS, governance=UPHOLD`,
    answer `Thủ đô của Nhật Bản là Tokyo.`
  - Consensus lines sau fix — **0/6 `missing_distinct_providers`** (trước fix 26/26):
    - `primary(openrouter:nvidia/nemotron-3-super-120b-a12b:free)=FAIL secondary(groq:openai/gpt-oss-20b)=PASS consensus=disagree final=None` (withhold lần 1 Q1 — tri-state đúng khi 2 family bất đồng)
    - `primary(...)=FAIL secondary(groq:...)=FAIL consensus=agree final=FAIL`
    - `consensus=agree final=PASS` ×4
  - Secondary không còn im lặng: groq hiện diện trong MỌI consensus line;
    `gemini:gemini-3.6-flash` còn thắng 1 hedge race ở chat task.

## 7. Giới hạn + câu hỏi mở

- Cerebras/SambaNova (402) và NVIDIA (429) là giới hạn quota/rate-limit external —
  cần owner quyết (nâng tier hoặc thay key); cấu hình không sửa được.
- Judge chain primary `anthropic/claude-3-5-sonnet` (default `OPENROUTER_MODEL_JUDGE_PRIMARY`)
  404 — openrouter vẫn trả lời qua free fallback nên không chặn consensus, nhưng mỗi
  judge call đốt ~0.5s fail-over; cân nhắc set `OPENROUTER_MODEL_JUDGE_PRIMARY` về
  model sống ở session sau.
- Disagreement (như withhold lần 1 của Q1) là hành vi fail-closed ĐÚNG — accuracy còn
  phụ thuộc chất lượng verdict của openrouter-nemotron làm primary; chưa chứng minh
  8/8 benchmark pass.
- `github` family chưa cấu hình key — owner quyết.
- PASS ở đây chỉWithin stated scope: 2 câu hỏi runtime + suite hermetic; không claim
  accuracy toàn cục hay production-ready.

## 8. Skill bindings (SHA256)

- `.agents/skills/scp-dna/SKILL.md`: `4aada0be4873598dc50c3a7f38d90151429bb5263c511a838ed1cdcb4d594d10`
- `.agents/skills/scp-gateway-resilience/SKILL.md`: `b60e8eb3a2d2c9de971a001924019cfa0b3038f9c96dfa4e3ac1cb8fca750a5a`
