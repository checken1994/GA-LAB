# M04 Runbook — Control & Hands (`/v3/pc/*`, `/v3/hands/*`, `/v3/web/*`)

Mạch: **M4 Control & Hands** (pc_controller_routes, hands_routes, web_control_routes,
control_routes, pc_controller, scp/hands, capability_epoch). Closure record:
`reports/circuit-closures/M04-closure.json`. Bản đồ 14 mạch:
`reports/circuit-closures/CIRCUIT-FLOW-MAP.md`.
Runbook được tạo sau pin (F2/F3, DNA-2 2026-09-12) — chỉ chạm `reports/circuit-closures/**`,
không đụng file scope `.py` nên không vô hiệu hoá pin.

> [!IMPORTANT]
> M4 đang ở `CLOSED_WITH_KNOWN_GAP`: D0/D1/D2 = PASS; D3 = `PASS_WITH_LIMITS` — 13/13 probe HTTP
> thật trên instance tạm full-profile cùng image pin (6 negative token-only 403 + 2 PEP 403 +
> golden path hands/execute kernel COMPLETED); **lenh thuc `/v3/pc/execute` bi platform-limit trong
> container Linux** (thực thi thật được chứng minh ở D1 trên Windows host). KHÔNG đọc là
> "PC control production-ready" hay "an toàn trước mọi lớp tấn công". Chi tiết: `known_gaps`
> GAP0–GAP10 trong closure record.

## 0. Purpose

Tái lập bằng chứng runtime cho surface điều khiển PC/hands/web và các guard capability token
(PEP), đồng thời chẩn đoán 403/404/UNKNOWN khi vận hành. Kết quả khác kỳ vọng bên dưới ⇒
mạch không còn CLOSED.

## 1. How to run / verify

### D1 — Contract tests (không cần Docker; thực thi thật trên Windows)

```powershell
python -m pytest tests/T03_capability/test_flow_04_control_hands_scp_standard.py -q
```

Kỳ vọng theo evidence: **58 passed, exit 0** (`M04-evidence/D1-T04-pytest.txt` tại pin `e13fad4`;
repeat/regression: 76 passed — `D1-T04-repeat-regression.txt`; token/PEP boundary: 18 passed —
`D1-regression-token-pep-boundary.txt`). Mock helpers ĐÃ BỊ XÓA khỏi test module.

### D2 — Runtime proof (Docker, pin SHA)

```powershell
$env:SCP_GIT_SHA = "e13fad455afbfaa7b5e53ec677c1e9772eecc19d"   # hoặc git rev-parse HEAD khi re-pin
docker compose build scp-api   # lan 1 co the fail TRANSIENT TLS auth.docker.io — retry 1 lan (observed)
docker compose up -d --force-recreate
Invoke-RestMethod http://127.0.0.1:8000/health     # 200, service_identity.commit == SCP_GIT_SHA
Invoke-RestMethod http://127.0.0.1:8000/readiness  # 200 {status:ready, judge:ok, background_scheduler:ok}
```

Evidence: `M04-evidence/D2-docker.txt` + `D2-docker-build.txt` (ghi rõ: không shared secret ⇒
token-only fail-closed mặc định; tên env `SCP_CAPABILITY_SECRET`, `SCP_API_PROFILE`,
`SCP_EGRESS_MODE` được set — không đọc/in giá trị).

### D3 — Probes runtime (theo `D3-runtime-setup.txt` + `_probe_http.py`)

13/13 probe HTTP thật trên container tạm full-profile (`scp-m4-probe`, cùng image pin, đã teardown).
Token/signature KHÔNG bao giờ được ghi vào evidence (chỉ `token_id` truncate 8 ký tự).
Evidence: `M04-evidence/D3-m4-runtime.json` + `D3-runtime-setup.txt`.

## 2. Failure modes + recovery

| Triệu chứng | Nguyên nhân thật | Recovery đúng |
|---|---|---|
| `/v3/pc/*`, `/v3/web/*` → **404** trên deployment chính (hands cần standard, pc/web cần full) | Deployment chính chạy profile khác (`scp/api/route_profile.py`) — GAP0, gap vận hành env | Chạy profile `full` cho pc/web; `standard` đủ cho hands. KHÔNG nới profile để "hết 404". |
| **403** `PC Controller token is missing or invalid` | Capability token thiếu/sai — negative path ĐÚNG thiết kế (probe N1/N2 trong D3) | Cấp token đúng seam; không tắt token guard. |
| `/v3/pc/execute` fail trong container Linux | Platform-limit: không có `powershell.exe` trong container (GAP1) | Thực thi thật chỉ chứng minh trên Windows host (D1). KHÔNG đọc là "command execution đã chứng minh runtime trong container". |
| `/v3/hands/execute` với token bad-signature → kernel **UNKNOWN (reconciliation required)** | Bridge đi qua checkpoint rồi kết thúc UNKNOWN — durable-kernel fail-closed, không retry (GAP6) | Reconcile theo quy trình kernel; KHÔNG retry mù. Chưa có test riêng pin kịch bản này — gap đã ghi. |
| Build Docker fail lần 1 với TLS handshake timeout tới auth.docker.io | Transient network (observed tại D2, không phải product defect) | Retry build 1 lần; nếu lặp lại, kiểm registry/network trước khi đổi code. |

## 3. Evidence pointers

| Mục | File |
|---|---|
| D1 | `reports/circuit-closures/M04-evidence/D1-T04-pytest.txt`, `D1-T04-repeat-regression.txt`, `D1-regression-token-pep-boundary.txt` |
| D2 | `M04-evidence/D2-docker.txt`, `D2-docker-build.txt` |
| D3 | `M04-evidence/D3-m4-runtime.json`, `D3-runtime-setup.txt`, `_probe_http.py` |
| D6 | `M04-evidence/D6-ast-scan.txt` (6 `except:pass`-without-log PRE-EXISTING, có chủ đích cleanup/control-flow — GAP4) |
| D7 | `M04-evidence/D7-todo-scan.txt` |
| Panen tổng | `reports/expert-panel/MC4-m4-closure-attempt3.md` |
| State pollution đã biết | `data/pc_controller/KILL_SWITCH` leftover trong repo data dir (GAP9) — cần owner dọn, không ảnh hưởng verdict |

## 4. Regression clause

Commit sau chạm file scope M4 (`scp/api/routes/pc_controller_routes.py`, `hands_routes.py`,
`web_control_routes.py`, `control_routes.py`, `scp/pc_control/pc_controller.py`, `scp/hands/*`,
`scp/security/capability_epoch.py`) bắt buộc chạy lại tối thiểu **D1 (flow_04 + 2 regression suite)
+ D2 + D4** (GAP10). Đổi kiến trúc ⇒ đóng lại D1–D8.
