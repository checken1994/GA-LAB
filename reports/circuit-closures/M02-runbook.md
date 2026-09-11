# M02 Runbook — Ask & Chat (`/ask` pipeline + `/chat` WS)

Mạch: **M2 Ask & Chat**. Closure record: `reports/circuit-closures/M02-closure.json`.
Bản đồ 14 mạch: `reports/circuit-closures/CIRCUIT-FLOW-MAP.md`.
Runbook được tạo sau pin (F2/F3, DNA-2 2026-09-12) — chỉ chạm `reports/circuit-closures/**`, không đụng file scope `.py` nên không vô hiệu hoá pin.

> [!IMPORTANT]
> M2 đang ở `CLOSED_WITH_KNOWN_GAP`: D3/D4/D5/D6/D7 đều `PASS_WITH_LIMITS`. Đặc biệt: đường
> PASS/verified của `/ask` chỉ được chứng minh runtime trên **instance standard TẠM** với answer
> source fixture local (deployment pin không có answer source, `SCP_EGRESS_MODE=deny`);
> deployment chính chạy `SCP_API_PROFILE=core` nên route `/chat` **không đăng ký**. Chi tiết:
> `known_gaps` GAP0–GAP11 trong closure record. Đọc trước khi dùng lại kết quả.

## 0. Purpose

Tái lập bằng chứng runtime cho mạch Ask & Chat và chẩn đoán khi `/ask` hoặc `/chat` hỏng.
Runbook không thay thế closure record; kết quả chạy khác kỳ vọng bên dưới ⇒ mạch không còn CLOSED.

## 1. How to run / verify

### D1 — Contract tests (không cần Docker)

```powershell
python -m pytest tests/T02_contract/test_flow_02_ask_chat_scp_standard.py -q
```

Kỳ vọng theo evidence: **34 passed, exit 0** (`M02-evidence/D1-T02-pytest.txt`, chạy tại pin `1f00d00`). Suite M2 là duy nhất file `test_flow_02_*` — 8 failure khác trong `tests/T02_contract/` thuộc mạch M3 (GAP10), không phải regression của M2.

### D2 — Runtime proof (Docker, pin SHA)

```powershell
$env:SCP_GIT_SHA = "1f00d00bfabdd4f0f436be892ba637b88f58c287"   # hoặc git rev-parse HEAD khi re-pin
docker compose build scp-api
docker compose up -d --force-recreate
Invoke-RestMethod http://127.0.0.1:8000/health     # 200, service_identity.commit == SCP_GIT_SHA
Invoke-RestMethod http://127.0.0.1:8000/readiness  # 200 {status:ready, judge:ok, background_scheduler:ok}
```

Evidence: `M02-evidence/D2-docker.txt` + `D2-docker-build.txt`.

### D3 — Probes runtime (theo `D3-runtime-setup.txt`)

JWT được mint **bên trong container** từ `SCP_JWT_SECRET` (không in giá trị). Probe chính:
`/ask` với header `X-SCP-Idempotency-Key` ⇒ kernel adapter ghi nhận identity `task_id` + idempotency
CLAIM rows trong sqlite; WS handshake `/chat` trên instance standard tạm. Evidence:
`M02-evidence/D3-ask-runtime.json` + `D3-ask-standard-runtime.json` + `D3-ws-standard.txt`.

## 2. Failure modes + recovery

| Triệu chứng | Nguyên nhân thật | Recovery đúng |
|---|---|---|
| Mọi WS handshake `:8000/chat` nhận **403 trước auth** | Deployment chạy `SCP_API_PROFILE=core` → route `/chat` không đăng ký (GAP0, gap vận hành env, không phải code defect) | Chạy profile `standard` trở lên. KHÔNG "sửa" bằng cách nới auth. |
| `/ask` trả FAIL/KILL với content **withheld** | Không có answer source trên deployment pin (`SCP_EGRESS_MODE=deny`, không LLM local): `ai_answer=''` → fail-closed đúng thiết kế (GAP1) | Không bypass. Muốn chứng minh PASS/verified: dựng instance tạm với answer source thật/fixture như D3 đã làm. |
| `/health` commit != SHA pin | Build thiếu `SCP_GIT_SHA` hoặc quên `--force-recreate` (container cũ vẫn chạy) | Build lại với build-arg đúng + `up -d --force-recreate` (cùng quy trình M01). |
| Cuối pytest run in `ValueError: I/O operation on closed file` (opentelemetry exporter) | Noise teardown exporter, quan sát được trong `D1-T02-pytest.txt` và suite vẫn 34 passed | Không phải fail của suite; không hạ assertion để "sửa". |

## 3. Evidence pointers

| Mục | File |
|---|---|
| D1 | `reports/circuit-closures/M02-evidence/D1-T02-pytest.txt` |
| D2 | `reports/circuit-closures/M02-evidence/D2-docker.txt`, `D2-docker-build.txt` |
| D3 | `reports/circuit-closures/M02-evidence/D3-ask-runtime.json`, `D3-ask-standard-runtime.json`, `D3-ws-standard.txt`, `D3-runtime-setup.txt` |
| D6 | `M02-evidence/D6-ast-scan.txt` + `D6-runtime-hook-warning.txt` (1 except:pass-without-log có chủ đích trong scope — GAP6) |
| D7 | `M02-evidence/D7-todo-scan.txt` |
| Panen tổng | `reports/expert-panel/MC2-m2-closure.md`, `reports/expert-panel/A-mach2-ask-chat-fixes.md` |

## 4. Regression clause

Commit sau chạm file scope M2 (`scp/api/chat.py`, `scp/api_server_parts/_ask_impl.py`,
`scp/api_server_parts/helpers.py`, `scp/api_server.py`, `scp/ask_kernel_adapter.py`,
`scp/runtime/slms_parts/misc_slms2.py`, `scp/api/routes/{history,calibration,forecast,world_state}_routes.py`)
bắt buộc chạy lại tối thiểu **D1 + D2 + D4** (GAP9). Đổi kiến trúc ⇒ đóng lại D1–D8.
