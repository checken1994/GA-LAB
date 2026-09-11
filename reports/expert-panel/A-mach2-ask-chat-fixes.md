# A — Mạch 2 (Ask & Chat) Fixes — Progress Log

- Agent: SCP Worker Agent A (Mạch 2)
- Branch: `audit/runtime-guard-AUDIT-20260909`, base HEAD `6328d51`
- Ngày: 2026-09-10
- Audit verdict phục vụ: `MACH2_FAIL_SILENT_RISKS` (Agent B)
- Ràng buộc tuân thủ: KHÔNG commit; chỉ sửa file trong whitelist; không mock thay
  subsystem logic trong assertion mới; không đụng `.env`; không in secret.

## BUG 1 — WebSocket chat chết (ai_answer="" → REJECT_EMPTY mọi tin nhắn)

File: `scp/api/chat.py`

| Fix | Vị trí |
|---|---|
| Sinh candidate answer TRƯỚC khi judge (mirror `_ask_impl.py`: `llm_gateway.chat(task="chat")` + web fallback bounded) | `chat.py:89-145` (`_generate_candidate_answer`), gọi tại `chat.py:415` |
| Normalize dict kết quả judge (trước đây `v.verdict` trên dict → AttributeError → MỌI message rơi vào error frame) | `chat.py:55-87` (`_DotDict`, `_normalize_judge_result`), gọi tại `chat.py:432` |
| Cap độ dài message 8000 chars + raw-frame guard (32000) → error frame + close 1009 | `chat.py:47-52`, nhận loop `chat.py:276-289` và `chat.py:315-326` |
| Rate-limit per-connection 20 msg/60s (sliding window) → error frame + close 1008 | `chat.py:51-52`, nhận loop `chat.py:291-308` |

Evidence Docker runtime (WS client raw-socket trong container, image sau build,
app profile=standard ở :8001, token thật từ auth config, không in secret):

```
RT-WS handshake status: HTTP/1.1 101 Switching Protocols
RT-WS welcome type: system session: True
RT-WS normal: type=clarification verdict=UNKNOWN gov=ESCALATE has_run_id=True latency=1.6s
RT-WS oversize reason: message_too_large max_chars: 8000
RT-WS close opcode: 8 code: 1009
```

→ Tin nhắn bình thường KHÔNG còn "rejected"-vì-empty (không còn generic error
frame); message vượt cap bị chặn + close 1009 đúng code.

## BUG 2 — /ask fail-silent

File: `scp/api_server_parts/_ask_impl.py`

| Fix | Vị trí |
|---|---|
| Khai báo field degradation trên AskResponse (additive, default None) | `_ask_impl.py:44-70` |
| Image fetch lỗi (URL local) → `detector_degraded=true` + note `image_fetch_failed:local_unreachable` thay 400; URL ngoài → vẫn 400 policy | `_ask_impl.py:145-166` |
| Image/voice detect bọc `asyncio.to_thread` + `asyncio.wait_for` 10s; timeout/exception → WARNING + flag; OCR/Whisper unavailable → flag | `_ask_impl.py:168-231` (`_DETECT_TIMEOUT_SECONDS=10`) |
| Voice fetch lỗi local → flag `voice_fetch_failed:local_unreachable` | `_ask_impl.py:186-200` |
| Pre-judge fact-check lỗi (có claim) → `fact_check_degraded=true` + WARNING | `_ask_impl.py:270-272, 320-324` |
| Tách 5 RESTORED hooks thành 5 try/except RIÊNG, log WARNING từng hook | `_ask_impl.py:459-556` (risk `:477`, history `:493`, world_state `:514`, calibration `:532`, forecast `:554`) |
| Response mang `detector_degraded` / `detector_note` / `fact_check_degraded` | `_ask_impl.py:560` |

Runtime evidence (trong container, /ask JWT thật + image_url local không tồn tại):

```
RT-ASK status: 200
RT-ASK detector_degraded: True
RT-ASK detector_note: image_fetch_failed:local_unreachable
RT-ASK verdict: FAIL   (fail-closed do không có LLM — đúng thiết kế)
```

Log per-hook cũng xác nhận: `[RESTORED-SYSTEMS] history hook failed: only
verified records may enter the ledger` — 1 hook fail KHÔNG còn kéo chết 4 hook
còn lại.

## BUG 3 — SSRF debt misc_slms2.py (7 điểm)

File: `scp/runtime/slms_parts/misc_slms2.py`

| Fix | Vị trí |
|---|---|
| Import `safe_urlopen` (pattern `experts/lifestyle.py`) | `misc_slms2.py:16` |
| `build_holiday_url` — regex `^[A-Za-z]{2}$`, chặn TRƯỚC khi fetch | `misc_slms2.py:27-40` |
| `build_city_search_url` — `urlencode` cho city, host cố định | `misc_slms2.py:42-55` |
| `build_bible_url` — `quote(ref, safe='')` | `misc_slms2.py:57-62` |
| HolidaySLM fetch → builder + safe_urlopen | `misc_slms2.py:576-583` |
| AnimalFactsSLM (cat/dog, host cố định) → safe_urlopen | `misc_slms2.py:651, 670` |
| CitySLM → thay `requests.get` bằng builder + safe_urlopen | `misc_slms2.py:736` |
| ReligionSLM → build_bible_url + safe_urlopen | `misc_slms2.py:804` |
| AdviceSLM / ChuckNorrisSLM → safe_urlopen | `misc_slms2.py:861, 921` |

Static check: `urllib.request.urlopen(`, `requests.get(`, `requests.post(` = 0
match còn lại trong module (test `test_misc_slms2_has_no_raw_urlopen_left`).

## BUG 4 — v105 route trả {"error": str(exc)} kèm HTTP 200

| File | Handler chuyển sang 500 | Giữ nguyên (lỗi có chủ đích) |
|---|---|---|
| `scp/api/routes/history_routes.py` | stats `:47`, list_evidence `:60`, record_evidence `:89` | `{"error": "subject_id required"}` (validation) |
| `scp/api/routes/calibration_routes.py` | stats `:49`, resolve `:98`, accuracy `:113` | — |
| `scp/api/routes/forecast_routes.py` | stats `:68`, list_cases `:120`, resolve `:141` | missing-fields / outcome_code (validation) |
| `scp/api/routes/world_state_routes.py` | stats `:60`, projection `:163` | — |
| `scp/api/routes/risk_routes.py` | KHÔNG có pattern swallow (kiểm tra thực tế — không cần sửa) | — |

Pattern chung: `_internal_error(exc)` → `logger.warning(..., exc_info=True)` +
`HTTPException(500, "internal error")` — không leak message nội bộ.

## TEST — `tests/T02_contract/test_flow_02_ask_chat_scp_standard.py`

File untracked được viết lại: 11 test cũ fail (tham chiếu API không tồn tại:
`ChatMemoryStore(db_path=)`, `gateway.ask`, `result.is_malicious`,
`_process_chat_message`, mock sai đối tượng auth) → 33/33 PASS, toàn bộ chạy
subsystem thật.

Test mới (a)-(e), không mock thay subsystem logic:

| Test | Dòng | Cách chạy thật |
|---|---|---|
| (a) WS message → answer không rỗng, không "rejected" | `:345` | HTTP server OpenAI-compat cục bộ thật (ThreadingHTTPServer) + gateway/provider/transport production + seed $0 pricing proof qua API chính thức của proof-store; openrouter bị tắt env để deterministic |
| (a') fail-closed không LLM → verdict FAIL + withheld | `:322` | Gateway không provider — branch fail-closed |
| (b) message > 8000 → error frame + close 1009 | `:384` | |
| rate-limit → error frame + close 1008 | `:402` | window constant được widen trong test (72 ghi chú trong docstring); constant thật 20/60 pin ở causal test |
| (c) /ask image_url local lỗi → `detector_degraded=true` | `:448` | TestClient thật + readiness poll + JWT thật + TaskKernel SQLite tmp_path |
| (c') không media → flag False + note None | `:481` | |
| (d) build_holiday_url chặn `../` v.v. | `:511` | Builder thuần (pure) |
| (d') HolidaySLM.predict với code xấu → không outbound (<2s) | `:525` | |
| (d'') city/bible encode trước fetch + static guard không còn raw urlopen | `:540, :551` | |
| (e) /v105/history/stats lỗi nội bộ → 500, không leak | `:578` | `_EVIDENCE_PATH` trỏ vào directory thật (tmp_path) → IsADirectoryError thật |
| (e') /v105/calibration/accuracy ledger hỏng → 500 | `:601` | SQLite file không hợp lệ (tmp_path) |

Fixtures dùng: `tmp_path`, `TestClient`, HTTP server thật trên 127.0.0.1
(egress policy của SCP cho phép loopback cho local fixture), env qua
monkeypatch. AttackCrawler + FastLearning background threads bị NEUTRALIZE ở
mức test session (test-isolation, không liên quan assertion — lý do ghi trong
docstring: non-daemon executor của HF download làm pytest process không exit
được; crawler thật vẫn chạy trong Docker runtime verify).

## VERIFY CUỐI

1. `python -m pytest tests/T02_contract/ -q` → **8 failed, 145 passed** (EXIT=1)
2. `python -m pytest tests/T01_boot/ tests/T02_contract/ -q` → **8 failed, 180 passed** (EXIT=1)
   → 8 failure này GIỐNG HỆT baseline TRƯỚC khi tôi sửa (baseline: 19 failed /
   130 passed = 8 pre-existing + 11 trong test_flow_02 cũ). Cả 8 nằm NGOÀI
   whitelist file của tôi:
   - `test_flow_03_openai_compat_scp_standard.py` (7): assert 422-vs-401
     (auth-first contract của API) + API mock không tồn tại — pre-existing.
   - `test_api_import_order_contract.py` (1): pydantic
     `TypeAdapter[Annotated[ForwardRef('Request')]] not fully defined` trong
     import-probe subprocess — pre-existing.
   File test của tôi: **33/33 PASS**.
3. Docker: `docker compose build scp-api` EXIT=0 → `up -d --force-recreate`
   EXIT=0 → `/health` 200 → `/readiness` `{"status":"ready","checks":{"judge":"ok","background_scheduler":"ok"}}`
   → logs không có crash/traceback (2 dòng "ERROR" là OTel span của 503 khi
   judge đang init — bình thường), RestartCount=0. Container `scp-scp-api-1`
   vẫn Up.
4. Smoke `/ask` không auth: **401** (auth-first, không 5xx). Với JWT thật trong
   container: **200** + `detector_degraded=true`.

## RUNTIME FINDING (ngoài scope, đề report)

Container đang chạy với `SCP_API_PROFILE=core` → `route_group_enabled("chat",
"core") == False` → route `/chat` KHÔNG được đăng ký trong app chính: mọi WS
handshake tới :8000/chat nhận **403 Forbidden** ở tầng router (trước cả auth).
Đây là posture triển khai hiện có (env deployment), KHÔNG phải regression của
fix này. Chat chỉ available từ profile `standard` trở lên — đã verify end-to-end
trên instance profile=standard (:8001) cùng image. Owner cần quyết định profile
deploy nếu muốn bật chat thật.

## Không làm được / hạn chế

1. T02_contract không PASS 100% do 8 failure pre-existing ngoài whitelist file
   (chi tiết trên) — KHÔNG tự ý sửa file ngoài phạm vi.
2. Rate-limit test phải widen window constant (60s → 1h) trong test vì 1 cycle
   fail-closed tốn ~2-4s dưới event loop của test (background jobs); cơ chế
   count→frame→close 1008 vẫn chạy code production thật.
3. `detector_degraded` với image_url local đã đổi hành vi 400 → 200+flag CHỈ
   cho URL loopback (policy của `_safe_fetch_url` cho phép localhost); URL ngoài
   vi phạm policy vẫn 400. Đây là điều kiện để test (c) khả thi trong runtime.

## TEST CONTRACT UPDATE 1a — Agent T (2026-09-10)

Bối cảnh: owner phê duyệt contract 1a cho chat WS (candidate answer sinh TRƯỚC
khi judge; judge PASS → frame `type:"verified"` tại `chat.py:475`). 3 test cũ
pin contract cũ nên đỏ. Chỉ sửa
`tests/T02_contract/test_flow_02_ask_chat_scp_standard.py` — KHÔNG đụng product
code (git diff `scp/api/chat.py` vẫn đúng +180/-3, `scp/llm_gateway/` 0 diff).

### Nguyên nhân gốc thật (evidence-first, khác giả định ban đầu)

Hai trong 3 test đỏ KHÔNG phải do contract đổi, mà do **lỗ hổng isolation của
test harness làm lộ key cloud thật**:

- `.env` chứa `OPENROUTER_API_KEY` … `OPENROUTER_API_KEY_10`;
  `scp/security/env_loader.py:load_selected_env()` nạp tất cả vào `os.environ`
  khi import (`judge_llm.py:6` gọi ở module level — chạy trong pytest).
  `_disable_openrouter()` cũ chỉ xóa slot 1-3 → slot 4-10 còn nguyên.
- `OpenRouterProvider._init_keys()` (`client.py:219-232`) reload keys mỗi khi
  `_API_KEYS` rỗng → `enabled` vẫn True dù đã "tắt".
- `LLMGateway.chat` (`client.py:638-647`) là brand-neutral round-robin chủ đích
  (comment "không ưu tiên model nào") → provider openrouter thật được chọn xoay
  vòng → test gọi thẳng openrouter.ai: label `openrouter:openrouter/free`,
  verdict PASS confidence 0.85 (hardcode `judge.py:154`).
- Kết quả: fail-closed test nhận PASS/knowledge không tồn tại trong
  `RealityJudge` (`scp/runtime/judge.py:20` — judge 2-tier, KHÔNG dùng
  phase1-9 mixins; không có đường KB short-circuit cho chat). Toàn bộ "đường
  PASS không cần LLM ngoài" quan sát được là key lộ + model cloud thật.

→ KHÔNG phát hiện product bug ở gateway (round-robin là design có chủ đích,
documented tại `client.py:635-647`); bug nằm ở test env setup → sửa HARNESS
theo hướng TĂNG strictness, đúng điểm lỗi.

### Thay đổi từng test

| Test | Thay đổi | Lý do |
|---|---|---|
| `_disable_openrouter()` (helper dùng chung) | Xóa MỌI `OPENROUTER_*` env (scan prefix, gồm slot 4-10 + biến `*_FILE`) + patch `scp.llm_gateway.client.load_openrouter_keys` → `[]` + reset `_API_KEYS`/`_key_cycle`. Là removal credential (config), không mock subsystem — provider/breaker/transport vẫn chạy thật | Chặn đường key lộ từ dotenv; loại dependency cloud thật (trước đây test gọi openrouter.ai thật, kết quả non-deterministic, tốn quota) |
| (1) `test_ws_chat_rate_limit_exceeded_closes_1008` | Accepted frame types `{"answer","rejected","clarification"}` → `{"verified","rejected","clarification"}` | Contract 1a: PASS → `verified` (`chat.py:475`); bỏ legacy `answer` = siết chặt hơn (pipeline không còn emit type đó). Cơ chế giữ nguyên: vượt 20 msg/window → error frame `rate_limit_exceeded` + close 1008 |
| (2a) `test_ws_chat_message_exchange_fail_closed_without_llm` → đổi tên `test_ws_chat_fail_closed_when_no_answer_source_available` | Giữ nguyên 3 assertion fail-closed (FAIL/rejected/withheld), THÊM `governance == "KILL"`; thêm precondition assert: chain chat của gateway singleton KHÔNG còn provider enabled | Pin contract đúng: fail-closed áp dụng cho scenario cả-các-nguồn-dead; precondition chứng minh isolation thay vì giả định. KHÔNG xóa fail-closed assertion |
| (2b) NEW `test_ws_chat_verified_frame_when_answer_source_available` | Pin contract 1a: có answer source (fixture OpenAI-compat thật qua HTTP loopback) → frame `type == "verified"`, `verdict == "PASS"`, `governance == "UPHOLD"`, answer ≠ rỗng ≠ withheld, confidence > 0, có run_id/trace_id | Companion của (2a): có nguồn → verified/PASS; hết nguồn → rejected/FAIL |
| (3) `test_ask_endpoint_llm_gateway_fallback_chain` | `startswith("openai_compat:")` → pin exact `provider_label == "openai_compat:t02-local-model"` + answer chứa content fixture `"2 cộng 2 bằng 4"` | Chứng minh round-robin thực sự tới provider fallback đã cấu hình qua HTTP thật, không phải provider cloud nào khác lọt vào |

### Environment repair (ngoài file test — công khai để audit)

`reports/pytest-basetemp` (pytest scratch dir, cấu hình tại `pytest.ini:6`)
hỏng ACL trên Windows: `icacls`/`ls`/`icacls` đều Access denied (WinError 5),
chặn setup `tmp_path` của 6 test (ERROR at setup). Đã RENAME sang
`reports/pytest-basetemp.corrupt-20260910` (không xóa dữ liệu; pytest tự tạo
basetemp mới mỗi session). Dir corrupt còn trên disk, cần dọn tay khi ACL được
sửa.

### Evidence — lệnh thật + kết quả

```
# 4 test đã đổi (trước khi chạy full):
python -m pytest ...::test_ws_chat_fail_closed_when_no_answer_source_available \
  ...::test_ws_chat_verified_frame_when_answer_source_available \
  ...::test_ask_endpoint_llm_gateway_fallback_chain \
  ...::test_ws_chat_rate_limit_exceeded_closes_1008 -q
→ 4 passed in 5.90s   EXIT=0   (5.9s = không còn cloud round-trip)

# Full file (chạy 2 lần liên tiếp để loại order-dependence):
python -m pytest tests/T02_contract/test_flow_02_ask_chat_scp_standard.py -q
→ 34 passed in 19.45s  EXIT=0
→ 34 passed in 19.09s  EXIT=0
```

So với run trước khi sửa: `3 failed, 24 passed, 6 errors in 127.68s EXIT=1`
(6 errors = basetemp ACL). Sau sửa: **34/34 PASS** (33 cũ + 1 test mới 1a),
nhanh hơn ~6.5x vì hết call cloud thật.

### Scope còn mở / open questions

1. `.env` thật vẫn được `load_selected_env()` nạp vào mọi pytest process; test
   khác ngoài file này (T03/T05/…) không dùng `_disable_openrouter` của T02 —
   khuyến nghị owner cân nhắc guard tập trung ở `tests/conftest.py` (ngoài
   whitelist của task này, không tự sửa).
2. `reports/pytest-basetemp.corrupt-20260910` cần dọn thủ công.
3. PASS ≠ hoàn toàn: các run xác nhận trong scope file T02 trên máy này
   (branch `audit/runtime-guard-AUDIT-20260909`, chưa commit); chưa verify
   Docker runtime cho phần contract 1a.
