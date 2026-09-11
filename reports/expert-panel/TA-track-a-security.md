# TA — Track A Security (A1–A4) — Evidence Record

> Worker: Agent TA (subagent). Ngày: 2026-09-12. Repo: `C:\Users\check\Downloads\scp`,
> nhánh `audit/runtime-guard-AUDIT-20260909` @ base `b726463` (== origin/main).
> Gate: HIGH=0 (Mimosa). Commit-per-item. No-mock trừ fault-injection seam.

## Skill binding (SHA256)

| Skill | SHA256 |
|---|---|
| `.agents/skills/scp-dna/SKILL.md` | `4aada0be4873598dc50c3a7f38d90151429bb5263c511a838ed1cdcb4d594d10` |
| `.agents/skills/scp-capability-security-review/SKILL.md` | `83f1633256756f8e4951471a11b9d45c1738d09f4db851df8ee91ee123a235ee` |
| `.agents/skills/scp-reality-verifier/SKILL.md` | `a9d65ce53b18f8310ceeb302b18b341a0e1b8b19cddc7f46d4fa6ee99432269e` |

---

## A1 — cryptography fail-closed (P1) — commit `1fff329` (+ test-isolation `947aee9`)

### Verdict claim audit: fail-open **CONFIRMED** — và đang SỐNG ở runtime container

Chuỗi fail-open (3 điểm, trước fix):

1. `scp/security/bypass_encrypt.py` (trước fix dòng 97-100): `encrypt_bypass()` khi
   `_get_fernet()` ImportError → trả về **plaintext JSON** thay vì raise. Chỉ có 1
   WARNING log lúc import — data vẫn ghi plaintext.
2. `scp/core/partition/shard.py` (trước fix dòng 94-96): `_get_bypass_encryptor()`
   catch init failure → sentinel `False` → "fallback to plaintext" (WARNING).
3. `scp/core/partition/shard.py` (trước fix dòng 418-420): `encrypt_bypass` raise →
   catch → "fallback to plaintext" (comment "don't lose bypass record" — chọn
   data-loss-trumps-confidentiality = fail-open).

Bằng chứng runtime (level C): container `scp-scp-api-1` đang chạy với
`SCP_ENCRYPT_BYPASSES=1` + `SCP_ENCRYPTION_KEY` (đã set — giá trị KHÔNG ghi ở đây),
nhưng `cryptography` **không được cài** (`ModuleNotFoundError`) → mọi bypass record
được ghi **plaintext** dù encryption được yêu cầu tường minh. (Giá trị secret đã lọt
vào một output shell khi kiểm tra env — không được sao chép vào file/log/commit nào.)

### Sửa đổi

| File:line (sau fix) | Thay đổi |
|---|---|
| `scp/security/bypass_encrypt.py:60-75` | `_require_fernet()` mới — raise RuntimeError khi thiếu cryptography (fail-closed) |
| `scp/security/bypass_encrypt.py:88-92` | `__init__` gọi `_require_fernet()` — không cho tạo encryptor gãy |
| `scp/security/bypass_encrypt.py:127-145` | `encrypt_bypass()` raise khi thiếu dep/key — bỏ nhánh plaintext |
| `scp/security/bypass_encrypt.py` (`encrypt_file`, `rotate_key`) | raise thay vì skip/no-op im lặng |
| `scp/core/partition/shard.py:81-100` | `_get_bypass_encryptor()` propagate init error — bỏ fallback plaintext |
| `scp/core/partition/shard.py` (write path ~414-431) | encrypt fail → raise, KHÔNG ghi plaintext khi env=1 |
| `scp/core/partition/shard.py` (read path ~292-302) | except thêm WARNING log (bỏ nuốt im lặng) |
| `scp/requirements.txt:44-48` | `cryptography==49.0.0` vào main requirements (hard runtime dep) |
| `scp/requirements-optional-ml.txt` | bỏ `cryptography` (đã chuyển đi) |
| `tests/T03_capability/test_bypass_encrypt_fail_closed.py` | 8 test (fault-injection seam: `sys.modules` block + WHY pin) |

Giữ nguyên behavior HỢP LỆ: mode plaintext có chủ đích khi `SCP_ENCRYPT_BYPASSES != "1"`
(encryptor không được tạo) + read-path backward-compat cho file legacy (R5-3 contract).
KHÔNG có downgrade tự động nào còn tồn tại.

## A2 — judge.py multi-LLM crosscheck chết — commit `79fbcbb`

### Verdict claim audit: CONFIRMED

`scp/runtime/judge.py` (trước fix dòng 117): `cross = cross_verify(question, ai_answer, context)`
— `cross_verify` là `async def` (`scp/runtime/multi_llm_crosscheck.py:43`) nhưng được gọi
KHÔNG await trong sync `judge()` → nhận coroutine → `cross["final"]` raise TypeError →
`except` nuốt im lặng → fallback `_llm_judge` single cascade. Kết quả: crosscheck
2-provider **không bao giờ chạy** trong sync path (sync path được dùng thật qua
`asyncio.to_thread` ở import_routes/stream_routes/webhook/chat). Async `judge_async`
(dòng 208) await đúng — path đó không ảnh hưởng.

### Sửa đổi

| File:line (sau fix) | Thay đổi |
|---|---|
| `scp/runtime/judge.py:37-61` | `_run_crosscheck_sync()`: `asyncio.run` khi thread không có loop; bridge worker thread riêng khi đang có loop (crosscheck vẫn chạy thật) |
| `scp/runtime/judge.py:150-166` | gọi `_run_crosscheck_sync()`; except → **log WARNING** rõ rồi mới fallback `_llm_judge` (hết nuốt im lặng) |
| `tests/T05_gateway/test_judge_sync_crosscheck_alive.py` | 5 test: agree→PASS thật, disagree→UNKNOWN + `multi_llm_disagreement`, raise→WARNING+fallback, bridge trong running loop, missing providers→None fail-closed |

Semantics giữ nguyên thiết kế cross_verify: agree → final=PASS/FAIL; disagree/missing →
final=None → escalate UNKNOWN (fail-closed). Regression flow_02/flow_12 giữ xanh
(flow_02 tự tắt crosscheck ở các case LLM).

## A3 — pin floating deps + lockfile — commit `cbc7d18`

### Verdict: DONE — 0 floating còn lại trong runtime file

- Floating trước fix: **7** (`pyjwt>=`, `slowapi>=`, `prometheus-client>=`,
  `opentelemetry-api>=`, `opentelemetry-sdk>=`, `opentelemetry-instrumentation-fastapi>=`,
  `PyYAML>=`) trong `scp/requirements.txt`. Sau: **0**.
- Pin theo version thật trong container `scp-scp-api-1` (pip freeze):
  pyjwt 2.13.0, slowapi 0.1.10, prometheus-client 0.26.0, otel-api/sdk 1.44.0,
  otel-instr-fastapi 0.65b0, PyYAML 6.0.3; `cryptography==49.0.0` (local, container
  rebuild xác nhận cài được).
- `scp/requirements.lock.txt` MỚI: 54 packages `==`, freeze từ container SAU rebuild
  (đã chứa cryptography) + header hướng dẫn dùng/re-lock.
- Dev/optional files: không đụng (trừ việc chuyển cryptography khỏi optional-ml).
- Rebuild image + `up -d`: build exit 0, container `Up`, cryptography 49.0.0 import được,
  `/health` = **200**.

## A4 — ruff config — commit `c611a82`

### Verdict claims audit: "select rồi ignore" ĐÚNG; "grep không thấy config" SAI

- Config TỒN TẠI: `scp/ruff.toml` (ưu tiên trong thư mục scp/) +
  `scp/pyproject.toml [tool.ruff]`. Audit grep ở root nên không thấy.
- `scp/ruff.toml` select `BLE001, S110, S112` (dòng 23-25) rồi `ignore` chính 3 rules đó
  (dòng 33-35) → **3 rules CHẾT, không enforcement**. Comment cũ "CI flags NEW silent
  except" SAI so với reality — đã sửa comment ghi trung thực + debt numbers + lộ trình B1.
- `E9,F63,F7,F82,B`: ACTIVE thật (không bị ignore). Đo `--select E9,F63,F7,F82,B`:
  594 findings (B020=20, B905=13, B904=11, B009=6, B007=5, B008=2, B013=1, F822=1;
  E9/F63/F7≈0). Rule F bắt được real bug: `F821 undefined name Path` tại
  `scp/api/routes/admin_v100.py:157`.
- Debt 3 rules chết (@ A4): **BLE001=1435, S110=20, S112=8** (tổng 1463).
- CI ruff exit-code gate tồn tại nhưng NARROW: `--select E9,F` (scp-refactor-freeze.yml:63)
  + focused file list (scp-release-gate.yml:96-100).
- Out of scope (theo lệnh): không fix 1463 debt, không đổi ignore semantics (sẽ phá CI
  khi debt chưa xử) — Track B1 mới là nơi xử.

---

## VERIFY CUỐI

| Gate | Kết quả | Evidence |
|---|---|---|
| pytest regression + test mới | **79 passed, exit 0** | flow_02 + flow_12 + test_bypass_encrypt_fail_closed (8) + test_judge_sync_crosscheck_alive (5) @ commit `947aee9`, Python 3.12, Windows host |
| Docker rebuild pin mới | build exit 0; cryptography 49.0.0 import OK trong container | image scp-api rebuild sau A1+A3 pins |
| `/health` | **200** | curl localhost:8000 sau `up -d` |
| Mimosa scan (normal) | HIGH = **0** (không tăng; baseline scan 2026-09-11 cũng HIGH=0); medium=20, low=97 | scanId `scan-2026-09-11T21-26-34.664Z-fb9c0c7b664e`, seal `sha256:ca97511171a895dd10887ee194f3c397d8c4652f431adbdcc8451b1f53c500ba`, 117 findings |
| Commit-per-item | `1fff329` → `79fbcbb` → `cbc7d18` → `c611a82` → `947aee9` | git log nhánh `audit/runtime-guard-AUDIT-20260909` |

## Limitations (PASS_WITHIN_SCOPE)

- Đã test trên host Windows + container Linux; chưa chạy full test suite toàn repo
  (chỉ flow_02, flow_12, A1, A2 và crosscheck tests như lệnh).
- Cryptography pin 49.0.0 chưa qua quét advisory online (offline DB match 0 affected).
- 1463 silent-except debt chưa xử (thuộc Track B1). Ruff subset 594 findings chưa fix.
- `judge()` sync khi gateway thiếu 2 provider family độc lập → verdict chuyển từ
  "single-cascade quyết" sang UNKNOWN/escalate (fail-closed đúng thiết kế cross_verify);
  chưa đo impact latency khi crosscheck enabled (2 LLM call thay vì 1).
- Secret `SCP_ENCRYPTION_KEY` đã hiện trong 1 output shell khi kiểm tra env container;
  không được sao chép vào file/log/commit nào — nên rotate nếu log đó được lưu nơi khác.
