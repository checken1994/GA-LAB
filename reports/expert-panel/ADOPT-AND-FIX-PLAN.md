# KẾ HOẠCH: MƯỢN NỀN TẢNG (ADOPT) + XỬ LÝ VẤN ĐỀ AUDIT (2026-09-12)

> Căn cứ: bảng so sánh SCP vs world-stable systems (đánh giá 2026-09-12) + audit report
> 11 claims (9/11 CONFIRMED) + V2 architecture + campaign 14/14 @ main c9955e1.
> Nguyên tắc: mỗi việc đi qua evidence ladder (worker → verifier độc lập, D0–D8 cho item lớn),
> commit-per-group, skill binding, KHÔNG big-bang, KHÔNG thay TaskKernel/capability/verifier/T00-T11.

## TRACK A — P1: LỖI SECURITY/SUPPLY-CHAIN (nhỏ, nguy hiểm cao — làm trước)

| # | Việc | Cách | Evidence gate | Effort |
|---|---|---|---|---|
| A1 | `cryptography` đưa vào `scp/requirements.txt` chính; đọc `scp/security/bypass_encrypt.py` chốt behavior khi thiếu dep — **fail-open phải thành fail-closed** (raise, không fallback plaintext) | Fix dependency split + code | Unit test: thiếu cryptography → raise fail-closed; Mimosa scan | S |
| A2 | **judge.py sync crosscheck chết** (`cross_verify` async không await → TypeError → nuốt → fallback im lặng). Fix: gọi đúng async (to_thread/await theo context) hoặc bỏ nhánh sync + log | Product fix + test pin (multi-LLM crosscheck sống lại) | Test chứng minh crosscheck chạy thật khi enabled; flow_02 regression | M |
| A3 | Lockfile supply-chain: pin `==` còn floating + tạo constraints lockfile + hash-mode install nếu khả thi | Config | pip install --dry-run reproducible; Mimosa | S |
| A4 | Ruff config: kiểm tra claim "select BLE001/S110/S112 rồi ignore" (grep không thấy config) → cài ruff config thật, bật fail-loudly rules | Config | ruff exit code trong CI | S |

## TRACK B — P2: HYGIENE + FAIL-LOUDLY TOÀN REPO

| # | Việc | Cách | Evidence gate | Effort |
|---|---|---|---|---|
| B1 | **Silent-except sweep**: 1801 `except Exception` — triage subset "silent" (không log/re-raise); tệ nhất: rollback path autofix. Mục tiêu: mọi except có log hoặc re-raise có chủ đích + comment DNA | Mở rộng fail-loudly campaign (mẫu M4 `62afcd7`/M12 `fa9da62`) | AST scan: bare-pass=0; silent→logged; pytest không tăng fail | L (3-4 agent phiên) |
| B2 | Dọn dead/artifact: `_lifespan.py` 764 LOC (audit-first rồi xóa), `hello_bug.py` → tests/fixture, `.tier3bak` trong tree, `test_api.py` root → tests/ | Audit-first per file | grep 0; pytest; Mimosa | S |
| B3 | print→logging 924 điểm | Mechanical, per-module, giữ stdout contract nơi cần | py_compile + pytest per module | L (mechanical) |
| B4 | Docs refresh: SCP_ARCHITECTURE.md (LOC/endpoint), EMERGENCY_GAP_REPORT GAP-12/13, GA.md đồng bộ | Docs theo code thật | Cross-check số liệu vs wc -l/route list | S |
| B5 | Triage 117 medium/low: REAL_FIX (~20: probe temp-file, template-injection, 1 cmd-injection) → sửa; BY_DESIGN (96 random phi-crypto) → record justification; FP → ghi | Triage-first, KHÔNG ép random về 0 (rủi ro phá determinism test) | Medium về ~0 REAL; Mimosa scan sau | M |

## TRACK C — P2: MƯỢN NỀN TẢNG GIAO TIẾP/CHỨNG THỰC (theo V2)

| # | Việc | Mượn gì | Giữ gì | Evidence gate | Effort |
|---|---|---|---|---|---|
| C1 | **PostgreSQL storage cho TaskKernel** (V2 P1-P2): implement `PgKernelStorage` qua abstraction `kernel_storage.py`; event table durable + NOTIFY chỉ là chuông (mất NOTIFY ≠ mất event); migration SQLite→Pg có tool + rollback | PostgreSQL MVCC/LISTEN-NOTIFY | Kernel semantics 17-state, fencing, UNKNOWN reconcile, journal hash-chain NGUYÊN | D0–D8 riêng: dual-write parity test (SQLite vs Pg cùng input cùng projection), crash recovery trên Pg, Mimosa, chaos kill Postgres giữa task | XL |
| C2 | **Event bus pattern** giữa container: bảng event + NOTIFY wake-up (không dùng NOTIFY làm queue) | PostgreSQL | TaskKernel là source of truth | Delivery test: listener chết → event không mất, replay khi sống lại | M |
| C3 | Container hoá: API/LLM-gateway/Autofix/Sandbox tách service (V2 P4) — Sandbox Evaluator chạy pytest thật, autofix không tự chấm | Docker Compose | Không đổi logic, chỉ biên | E2E: EVAL_REQUEST→EVAL_RESULT→gate chốt; OOM Autofix → LLM sống | L |

## TRACK D — P3: ADOPT TÍCH HỢP (sau C)

| # | Việc | Ghi chú |
|---|---|---|
| D1 | **Playwright thay web_control browser runtime** — mảnh yếu nhất; giữ policy/capability/egress wrapper | M |
| D2 | **MCP server interface cho hands/tools** — interop với hệ sinh thái agent; giữ PEP + capability | M |
| D3 | Đánh giá LiteLLM routing (nếu cần provider rộng) — giữ $0-wall + quota ledger | S đánh giá trước |
| D4 | OPA (governance), SIEM integration (alert router), LangGraph interop (multi-agent) | P3, chỉ khi có use case thật |

## KHÔNG LÀM (chốt từ đánh giá)

- ❌ Thay TaskKernel bằng Temporal/Celery (mất evidence-coupled completion)
- ❌ OAuth2/JWT thay capability token (sai vấn đề: user-auth ≠ attempt-scoped machine cap)
- ❌ Thay IndependentVerifier bằng CI (verify lúc merge ≠ per-action runtime receipt)
- ❌ Thay T00–T11 meta-audit (crown jewel, không có trên thị trường)
- ❌ Tách namespace injection 48 file NGAY (thuộc V2 redesign scope — làm khi container hoá, có plan riêng, không hotfix)

## THỨ TỰ THỰC THI ĐỀ XUẤT

```text
TUẦN 1:  A1 → A2 → A3 → A4 (P1 security — mỗi item worker+verifier+push)
TUẦN 2:  B2 → B4 → B5 (hygiene nhanh) — song song B1 chia lô theo module
TUẦN 3+: C1 Postgres (XL — làm theo D0–D8 riêng, dual-write parity trước khi switch)
         B1/B3 cài kèm giữa các phiên C
SAU C1:  C2 event bus → C3 containers → TRACK D
```

## QUY TẮC BẤT BIẾN
- Worker ≠ Verifier; skill binding hash; no-mock; commit-per-group; PIPESTATUS
- Mỗi item chốt bằng evidence record; main chỉ nhận qua gate (HIGH=0) + regression
- PASS_WITHIN_SCOPE — không claim complete; release-verdict tool vẫn là authority
