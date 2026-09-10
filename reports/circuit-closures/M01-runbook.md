# M01 Runbook — Boot & Background (SCP API)

Mạch: **M1 Boot & Background**. Closure record: `reports/circuit-closures/M01-closure.json`.
Bản đồ 14 mạch: `reports/circuit-closures/CIRCUIT-FLOW-MAP.md`.

Runbook này dùng để **tái lập bằng chứng runtime** cho M1 và để chẩn đoán khi boot hỏng.
Không thay thế closure record; nếu kết quả chạy khác kỳ vọng bên dưới thì mạch **không** còn CLOSED.

> [!IMPORTANT]
> M1 đang ở trạng thái `CLOSED_WITH_KNOWN_GAP`, không phải `CLOSED` sạch: **D4 (ratchet scan) = EVIDENCE_GAP**
> (hook ledger `inconclusive`, `scanned_files=0`, 6/6 file phạm vi `scanner_failed`). Chi tiết và các known gap
> khác nằm trong `reports/circuit-closures/M01-closure.json` và `reports/circuit-closures/M01-evidence/CORRECTIONS-AND-HASHES.md`.
> Bước 8 (regression clause) vì vậy vẫn hiệu lực đầy đủ.

---

## 0. Tiền đề (fail-closed, phải kiểm trước)

| Điều kiện | Kiểm | Ghi chú |
|---|---|---|
| Working tree sạch tại SHA pin | `git status --short` | Build từ tree bẩn ⇒ `/health` báo SHA sai. |
| `.env` tồn tại và có `SCP_JWT_SECRET`, `SCP_ADMIN_KEY` | **không in giá trị** | `validate_boot_config()` fail-closed: thiếu ⇒ lifespan raise ⇒ container boot fail có chủ đích. |
| Docker daemon chạy | `docker version --format '{{.Server.Version}}'` | |
| Cổng 8000 không bị chiếm | `docker compose ps` | compose bind `127.0.0.1:8000:8000`. |

Không dán giá trị secret vào log/evidence. Sai cấu hình ⇒ để nó fail, không bypass.

## 1. Build có pin SHA (bắt buộc cho D2)

PowerShell (Windows):

```powershell
$env:SCP_GIT_SHA = git rev-parse HEAD
docker compose build scp-api
```

- `$env:SCP_GIT_SHA` chảy vào `compose.yml` → `build.args.SCP_GIT_SHA` → `Dockerfile` `ARG/ENV` → image.
- Runtime đọc ENV này trong `_scp_service_identity()` (`scp/api_server.py`), nên `/health` trả về **đúng SHA đã pin**.
- Nếu bỏ bước này, `SCP_GIT_SHA` = `unknown`, runtime sẽ fallback sang `git rev-parse HEAD` trong container — mà image không có `.git`, nên `commit` sẽ là `unknown` và D2 **không** đạt.
- Image được tag `scp-api:local` (cố định trong `compose.yml`).

## 2. Lên dịch vụ

```powershell
docker compose up -d --force-recreate
```

`--force-recreate` là bắt buộc khi vừa build lại: không có nó, container cũ (image cũ) tiếp tục chạy và `/health` sẽ trả SHA cũ.

## 3. Kiểm chứng readiness

```powershell
Invoke-WebRequest http://127.0.0.1:8000/health    | Select-Object -Expand Content
Invoke-WebRequest http://127.0.0.1:8000/readiness | Select-Object -Expand Content
```

**`/health` — kỳ vọng:** HTTP 200, và `service_identity.commit == $env:SCP_GIT_SHA`.

```json
{
  "status": "ok",
  "service_identity": {
    "service_name": "scp-backend",
    "mode": "isolated",
    "configured_port": 8000,
    "commit": "<SHA đã pin>",
    "config_hash": "sha256:...",
    "argv": ["8000"]
  }
}
```

**`/readiness` — kỳ vọng:** HTTP 200 và tối thiểu:

```json
{"status":"ready","checks":{"judge":"ok","background_scheduler":"ok"}}
```

Payload thật còn có `service`, `version`, `reason` (`reason` phải là `null` khi ready). HTTP **503** + `"status":"initializing"` là **chưa** ready, không phải lỗi cấu hình: judge init chạy nền (`SCP_JUDGE_START_DELAY_SEC`, mặc định 5s) và scheduler chờ `_judge` tối đa 30s. Chờ và probe lại, đừng coi 503 là PASS.

Đối chiếu nhanh commit:

```powershell
(Invoke-RestMethod http://127.0.0.1:8000/health).service_identity.commit -eq $env:SCP_GIT_SHA
```

## 4. Log phải thấy (bằng chứng "đã nối dây")

```powershell
docker logs scp-scp-api-1 2>&1 | Select-String -Pattern '\[MACH1-FIX-1\]|\[MACH1-FIX-2\]|\[RESTORED-SYSTEMS\]|first execution completed'
```

| Dòng log | Ý nghĩa |
|---|---|
| `[MACH1-FIX-2] Boot config contract validated (fail-closed)` | gate cấu hình đã chạy **trước** mọi subsystem |
| `[MACH1-FIX-1] Background job registry started (5 jobs: attack_mode_monitor, canary_token_cleanup, deep_audit_scheduler, kernel_lease_expiry, kernel_orphan_reconcile)` | registry `start_all()` thật sự được gọi; 2 job `required=True` |
| `[BackgroundJob] kernel_lease_expiry: started (interval=30s)` + `kernel_orphan_reconcile: started (interval=60s)` | watchdog thread đã chạy |
| `[BackgroundJob] <name>: first execution completed` | **thân job** đã execute thật, không chỉ thread được schedule |
| `[RESTORED-SYSTEMS] RetryPolicy background thread started (real kernel wiring, db=...)` | retry worker chạy trên kernel DB thật (không còn stub) |

Thiếu `first execution completed` trong ~60s đầu ⇒ job đã start nhưng body chưa chạy (hoặc initial delay chưa hết: `canary_token_cleanup` 600s, `deep_audit_scheduler` 60s, `attack_mode_monitor` 120s). Đây là điểm khác biệt cốt lõi giữa "thread scheduled" và "job thật sự chạy".

## 5. Khi boot fail — đọc theo thứ tự

1. `validate_boot_config()` raise (`ConfigContractError`) ⇒ thiếu biến bắt buộc trong `.env`. Sửa cấu hình, **không** hạ gate.
2. `[MACH1-FIX-1] Background job registry failed to start` ⇒ job `required=True` fail. Container **phải** chết (fail-closed theo thiết kế). Đọc traceback job tương ứng.
3. `STARTUP-GATE` bị bypass nếu `SCP_SKIP_STARTUP_GATE=1`; compose pin `"0"` cho local candidate. Nếu thấy log `audit BYPASSED`, môi trường đang chạy dev/test — D2 không hợp lệ trên môi trường đó.
4. `[BackgroundJob] <name>: error #N — ...` ⇒ lỗi trong thân job; sau 5 lỗi liên tiếp job tự suppress tới chu kỳ sau (không chết app).

## 6. Xuống dịch vụ

```powershell
docker compose down
```

Shutdown path (`lifespan` post-yield) dừng `deep_audit_stop`/`attack_monitor_stop`/`retry_policy_stop`, cancel các task nền, `doubt_cron.stop()`, rồi `registry.stop_all(timeout=10.0)`.

## 7. Rollback

Rollback = revert commit, **không** gỡ bỏ gate và **không** nới ngưỡng test:

```powershell
git revert --no-edit <closure_commit>
git revert --no-edit <sha_pin>
docker compose build scp-api   # với $env:SCP_GIT_SHA = SHA sau revert
docker compose up -d --force-recreate
```

Kiểm lại `/health` (`service_identity.commit` == SHA sau revert) và `/readiness` như mục 3.
Pin SHA là bất biến: sau revert phải build lại, không tái dùng image cũ.

## 8. Regression clause

Commit sau **chạm file trong phạm vi M1** bắt buộc chạy lại **D1 + D2 + D4**.
Không chạm file phạm vi thì không vô hiệu hoá pin (xem `commit_pattern_note` trong closure record).

## Phạm vi file M1 (scope lock — D0)

```text
scp/api_server_parts/lifespan.py
scp/api/background_jobs.py
scp/policy/retry_policy.py
scp/api_server.py
scripts/run_scp_acceptance.py
.env.example
Dockerfile
compose.yml
tests/T01_boot/test_flow_01_boot_background_scp_standard.py
reports/circuit-closures/**
```
