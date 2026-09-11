# M03 Runbook — OpenAI-compat & SWE-bench compat (`/v1/*`, `/swe-bench/v1/*`)

Mạch: **M3 OpenAI-compat & SWE-bench compat**. Closure record: `reports/circuit-closures/M03-closure.json`.
Bản đồ 14 mạch: `reports/circuit-closures/CIRCUIT-FLOW-MAP.md`.
Runbook được tạo sau pin (F2/F3, DNA-2 2026-09-12) — chỉ chạm `reports/circuit-closures/**`, không đụng file scope `.py` nên không vô hiệu hoá pin.

> [!IMPORTANT]
> M3 đang ở `CLOSED_WITH_KNOWN_GAP`: D0–D3 = PASS (D3 chứng minh fail-closed runtime:
> 401 auth-first, 400 envelope cho malformed input, 200 FAIL/KILL withheld khi không answer
> source); D4/D5/D6/D7 = `PASS_WITH_LIMITS`. Endpoint là **OpenAI-SHAPE compat + fail-closed**,
> KHÔNG phải answer generator: đường chat-lượng-thật với model thật CHƯA được chứng minh runtime.
> Chi tiết: `known_gaps` GAP0–GAP10 trong closure record.

## 0. Purpose

Tái lập bằng chứng runtime cho các route OpenAI-compat (`scp/api/routes/openai_compat.py`)
và SWE-bench compat (`swe_bench_routes.py`), cùng contract import-order
(`test_api_import_order_contract.py` — root-cause thật nằm ở `v105_routes.py` thiếu import `Request`).
Kết quả khác kỳ vọng bên dưới ⇒ mạch không còn CLOSED.

## 1. How to run / verify

### D1 — Contract tests (không cần Docker)

```powershell
python -m pytest tests/T02_contract/test_flow_03_openai_compat_scp_standard.py tests/T02_contract/test_api_import_order_contract.py -q
```

Kỳ vọng theo evidence: **28 passed, exit 0** (`M03-evidence/D1-T03-pytest.txt` tại pin `3f29c18`;
repeat: 29 passed — `D1-T03-pytest-repeat.txt`; regression T02: 34 passed — `D1-T02-regression.txt`).
Test ERR-1 dùng fault injection tại seam `get_judge` (không mock golden path).

### D2 — Runtime proof (Docker, pin SHA)

```powershell
$env:SCP_GIT_SHA = "3f29c180502fe71d92454f9ffcf699476a07f4ce"   # hoặc git rev-parse HEAD khi re-pin
docker compose build scp-api
docker compose up -d --force-recreate
Invoke-RestMethod http://127.0.0.1:8000/health     # 200, service_identity.commit == SCP_GIT_SHA
Invoke-RestMethod http://127.0.0.1:8000/readiness  # 200 {status:ready, judge:ok, background_scheduler:ok}
```

Evidence: `M03-evidence/D2-docker.txt` + `D2-docker-build.txt`.

### D3 — Probes runtime (theo `D3-runtime-setup.txt`)

Probes HTTP thật trên **instance tạm full-profile** (`scp-m3-std`, `127.0.0.1:8002`) cùng image pin,
`/health` xác nhận `service_identity.commit == pin` trước khi probe; JWT mint trong container.
Đã quan sát: `no_auth` → **401** auth-first; `auth_bad_json` → **400** envelope OpenAI-shape.
Evidence: `M03-evidence/D3-m3-runtime.json` + `D3-runtime-setup.txt` +
`D3-failure-triggers-postfix.txt`.

## 2. Failure modes + recovery

| Triệu chứng | Nguyên nhân thật | Recovery đúng |
|---|---|---|
| `/v1/*`, `/swe-bench/v1/*` → **404** trên deployment chính | Deployment chạy `SCP_API_PROFILE=core` (GAP0, gap vận hành env; openai_compat cần standard+, swe-bench cần full) | Chạy profile phù hợp. KHÔNG đăng ký route vô điều kiện để "hết 404". |
| Completion trả `FAIL`/`KILL`, content withheld, kèm `REJECT_EMPTY` | Không answer source ⇒ `ai_answer=''` → tier1 REJECT_EMPTY (GAP1) — fail-closed đúng thiết kế | Không bypass. Endpoint không sinh answer; muốn luồng thật phải có answer source được chứng minh. |
| `stream=true` trả về 1 JSON completion đơn | SSE streaming CHƯA được hỗ trợ (GAP2, observed) | Ghi nhận là giới hạn; không mô phỏng SSE trong test để PASS. |
| `instance_id` gửi lên không thấy trong tracking | SWE-bench compat: instance_id không bắt buộc, extra field bị ignore, endpoint trả static tool-calling stub (GAP3) | Không dùng endpoint này làm agent loop thật (agent loop ở mạch khác). |
| `503` (judge pipeline failure) không tái hiện được qua HTTP | Nhánh 503 chỉ chứng minh ở contract test qua fault injection tại seam `get_judge`; probe content list/int/None đều graceful (GAP4) | Giữ nguyên fault-injection test; không mở surface thật để "chạm" nhánh lỗi. |
| Import-order contract fail sau khi sửa `v105_routes.py` | Root-cause lịch sử: thiếu import `Request` — đã fix tại pin; fail mới ⇒ regression thật | Chạy lại D1 (flow_03 + import-order) và sửa product tại điểm lỗi. |

## 3. Evidence pointers

| Mục | File |
|---|---|
| D1 | `reports/circuit-closures/M03-evidence/D1-T03-pytest.txt`, `D1-T03-pytest-repeat.txt`, `D1-T02-regression.txt` |
| D2 | `M03-evidence/D2-docker.txt`, `D2-docker-build.txt` |
| D3 | `M03-evidence/D3-m3-runtime.json`, `D3-runtime-setup.txt`, `D3-failure-triggers-postfix.txt` |
| D6 | `M03-evidence/D6-ast-scan.txt` (2 `except OSError: pass` pre-existing trong `v105_routes.py` cleanup guard, re-raise bên ngoài — GAP7) |
| D7 | `M03-evidence/D7-todo-scan.txt` |
| Panen tổng | `reports/expert-panel/MC3-m3-closure.md` |

## 4. Regression clause

Commit sau chạm file scope M3 (`scp/api/routes/openai_compat.py`, `scp/api/routes/swe_bench_routes.py`,
`scp/api/routes/v105_routes.py`) bắt buộc chạy lại tối thiểu **D1 (flow_03 + import-order) + D2 + D4**
(GAP10). Đổi kiến trúc ⇒ đóng lại D1–D8.
