# MC2 — Đóng Mạch 2 (Ask & Chat) — Progress Log

- **Agent:** SCP Worker Agent MC2
- **Ngày:** 2026-09-11
- **Branch:** `audit/runtime-guard-AUDIT-20260909`, HEAD/SHA pin: `1f00d00bfabdd4f0f436be892ba637b88f58c287`
- **Verdict closure:** `CLOSED_WITH_KNOWN_GAP` — `reports/circuit-closures/M02-closure.json`
- **Skill binding (sha256):** scp-dna `4aada0be…`, scp-runtime-audit `63680fd1…`, scp-reality-verifier `a9d65ce5…`, scp-release-evidence-gate `81b2cc0e…` (đọc trước khi làm việc, ghi trong closure record).

## Việc đã làm (D0–D8)

| Mục | Kết quả | Evidence |
|---|---|---|
| D0 scope lock | 11 file scope (chat.py, _ask_impl.py, helpers.py, api_server.py, ask_kernel_adapter.py, misc_slms2.py, 4 v105 route files, test_flow_02) | M02-closure.json `scope_files` |
| D1 contract tests | **34/34 PASSED, exit 0** (21.33s, verbose) — chạy lại tại pin | `M02-evidence/D1-T02-pytest.txt` |
| D2 runtime proof | Rebuild `--build-arg SCP_GIT_SHA=<pin>` EXIT=0, up --force-recreate; /health 200, /readiness ready (judge ok), **service_identity.commit == pin TRUE**; event journal per-task hash chain 8/8 mỗi ask task | `D2-docker.txt`, `D2-docker-build.txt` |
| D3 adversarial | Fail-closed runtime: /ask missing-context → 200 FAIL/withheld/KILL; zero-cost wall chặn provider chưa có proof (DENY_UNKNOWN_PRICE); WS 403 trên profile=core. Happy-path: /ask context-backed → 200 **PASS/UPHOLD + task COMPLETED**; WS /chat → handshake 101 + frame **`verified`/PASS/UPHOLD** (contract 1a) trên instance standard **tạm** (:8001, cùng image, đã tắt sau probe) | `D3-ask-runtime.json`, `D3-ask-standard-runtime.json`, `D3-ws-standard.txt`, `D3-runtime-setup.txt` |
| D4 ratchet | Deep scan có seal `4a66b279…`: **high=0** (medium 13 / low 97) tại snapshot pre-commit 1f00d00; 0 finding trong scope M2; limit: worktree drift sau commit chưa được scan | `reports/expert-panel/S6b-final-sweep.md` |
| D5 review độc lập | Agent B MACH2_FIX_APPROVED + Agent V SWEEP_APPROVED (no-weakening) — ghi ở commit message 1f00d00; **chưa có artifact review nguyen văn trong repo** (gap ghi rõ) | commit 1f00d00, `A-mach2-ask-chat-fixes.md` |
| D6 fail loudly | AST: 10/11 file = 0; 1 except:pass-without-log có chủ đích (env-parse `_ask_impl.py:237`, thực tế transcribe timeout log WARNING); runtime: hook-fail log WARNING bắt được trong lúc probe; degradation fields có trên response thật | `D6-ast-scan.txt`, `D6-runtime-hook-warning.txt` |
| D7 wiring/docs | 0 TODO trên 11 file; limits: không có header WIRED/CLOSED ở module M2, flow map M2 stale, chưa có runbook — ghi rõ, không an | `D7-todo-scan.txt` |
| D8 closure record | `M02-closure.json` + STATUS-LEDGER dòng M2 → CLOSED_WITH_KNOWN_GAP | files này |

## Phát hiện kỹ thuật trong phiên (evidence-first)

1. **Zero-cost wall hoạt động thật:** gateway gọi provider chưa có pricing proof →
   `zero_cost_denied:DENY_UNKNOWN_PRICE`. Phải seed proof $0 qua API chính thức
   của proof-store (đúng như D1 test làm) thì fixture mới chạy được. Đây là
   falsification tích cực cho một guard.
2. **`cross_verify` cần ≥2 provider families:** single-provider → fail-closed
   (verdict UNKNOWN, ESCALATE). D1 test đã pin `SCP_MULTI_LLM_CROSSCHECK=0`;
   instance tạm mirror đúng env đó (ghi trong `D3-runtime-setup.txt`).
3. **Idempotency:** header `X-SCP-Idempotency-Key` → task identity; resend trong
   window → kernel uniquify task mới (không replay) — hành vi observed.
4. **Container cũ (trước rebuild) báo `commit=unknown`** (build không truyền
   SCP_GIT_SHA) — đã rebuild + recreate với pin trong phiên này.
5. **Event journal:** per-task chain 8/8 OK; 3 ranh giới liên-task
   (TASK_CREATED) không cross-link — mở cho audit TaskKernel, ghi known_gaps.

## Giới hạn bằng chứng (đọc trước khi dùng)

- PASS/verified runtime chỉ chứng minh với **answer source fixture local**
  (không có LLM thật nào được gọi; egress deny giữ nguyên toàn phiên).
- Chat route KHÔNG đăng ký trên deployment profile=core — gap vận hành.
- D5 chưa có bản review độc lập nguyen văn trong repo.
- Không soak, không chaos, không durability-restart test — không tuyên bố
  production-ready.

## Kết quả cuối

- Commit closure: xem git log (`docs(M2): pin circuit closure record M02 at 1f00d00…`).
- Gate Mimosa HIGH=0 phải giữ nguyên sau commit — nếu gate chặn thì BÁO, không tự xử.
