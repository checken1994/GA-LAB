# SCP Learning Handoff và Learning Staging R43

**Release:** R43
**Scope:** Policy Handoff, isolated Learning Staging, FastLearning fail-closed
**Evidence:** Windows PC thật, Python 3.12 venv, `55 pytest passed`, `73/73 portable reality passed`

## Vấn đề trước R43

SCP có `ExperienceEngine` ghi lesson vào bảng `experiences`, nhưng runtime chỉ đọc `data/active_policies.json`; không có writer chính thức tạo file này. Vì vậy có thể có `lessons_stored` nhưng chưa có bằng chứng `policy_materialized`, `policy_applied` hoặc `behavior_delta_measured`.

Ngoài ra, FastLearning có các nhánh `fail-open` ở WHY gate, SourceWatchlist, self-verification, KB cross-check và DB write. Những nhánh này có thể làm learning tiếp tục hoặc báo metric không đúng khi hạ tầng kiểm chứng/lưu trữ lỗi.

## Các thay đổi R43

### PolicyMaterializer

`scp/core/policy_materializer.py` là implementation có versioned payload và các bước tách biệt:

```text
experiences (unapplied)
    → build candidate
    → validate schema + SHA-256
    → atomic promote active_policies.json
    → mark only eligible lesson IDs applied
    → record applied event in policy_handoff_ledger.jsonl
```

Candidate được ghi atomically bằng temporary file + `os.replace`. Candidate rỗng bị từ chối promote. Lần promote đầu tiên tạo marker rollback cho trạng thái “active policy chưa tồn tại”; các lần sau backup active policy cũ trước khi replace.

### ExperienceEngine integration

`ExperienceEngine.run_reflection_cycle()` không còn gọi `mark_applied()` trực tiếp trước khi có artifact. Nó gọi materializer, chỉ mark lesson sau khi policy được validate/promote, rồi ghi `policy_handoff` vào report. Nếu handoff lỗi, lesson giữ nguyên `applied=0` và report ghi `HANDOFF_FAILED`.

### ExperienceReflector

`scripts/learning/r43_experience_reflector.py` chuyển evidence `knowledge`, `error_history` và `memory` thành đúng năm lesson types cũ: `SOURCE_RELIABILITY`, `DOMAIN_BIAS`, `ERROR_FREQUENCY`, `CONFIDENCE_TUNING`, `ROUTE_OPTIMIZATION`. Các row `VERDICT_*` chỉ là verdict history, không bị coi nhầm là policy lesson.

### Learning Staging

`scripts/learning/learning_staging_r43.py` clone `data/v13.db` sang `.private-secrets/release-audit/learning-staging-r43-*`, giữ năm dangerous flags bằng `0`, bật closed loop chỉ trong process staging và giới hạn provider cycle tối đa 3 câu hỏi. Production DB, production policy và production ledger không bị dùng để ghi.

Các command chính trên Windows:

```powershell
# Tạo staging clone và không gọi provider
.\scp\venv\Scripts\python.exe scripts\learning\learning_staging_r43.py `
  --root C:\Users\check\Downloads\scp --count 2

# Tạo policy candidate từ staging DB
.\scp\venv\Scripts\python.exe scripts\learning\policy_handoff_r43.py `
  --root C:\Users\check\Downloads\scp `
  --db .private-secrets\release-audit\learning-staging-r43\v13.db `
  --data-dir .private-secrets\release-audit\learning-staging-r43 materialize

# Promote/apply chỉ khi candidate có eligible lesson
.\scp\venv\Scripts\python.exe scripts\learning\policy_handoff_r43.py `
  --root C:\Users\check\Downloads\scp `
  --db <staging>\v13.db --data-dir <staging> apply

# Rollback active policy
.\scp\venv\Scripts\python.exe scripts\learning\policy_handoff_r43.py `
  --root C:\Users\check\Downloads\scp `
  --db <staging>\v13.db --data-dir <staging> rollback
```

Không chạy các command trên production `data/` cho tới khi staging A/B measurement chứng minh policy cải thiện hành vi.

## FastLearning fail-closed

R43 thay đổi các nhánh có thể ảnh hưởng trust boundary:

| Failure boundary | Trước R43 | Sau R43 |
|---|---|---|
| WHY gate exception | Log non-blocking, có thể tiếp tục | Block KB write, audit event |
| SourceWatchlist exception | Fail-open | Block KB write, audit event |
| Verification call exception | Fail-open | Reject fact, audit event |
| KB cross-check exception | `True`, neutral penalty | Reject fact, audit event |
| Audit write failure | Debug-only | Fact không được coi là stored |
| DB write exception | Swallow/debug | Return `False`, audit/error log |
| Stored metrics | Tăng trước khi biết DB write thành công | Chỉ tăng khi `_store_kb()` trả `True` |

Các lỗi provider/network ở tầng hỏi Ollama và Wikipedia vẫn trả empty/unverified để cycle không crash. Đây là **availability fallback**, không phải success path: không có answer/verification thì fact không được lưu. Lỗi scan từng file/news feed cũng skip item và ghi log; đây là thiếu dữ liệu cần surfaced qua health/ledger ở bước tiếp theo.

## Evidence PC thật

| Check | Result |
|---|---:|
| Fail-closed fault injection: WHY/watchlist/verify/DB write | 4/4 pass |
| Stored metric khi `_store_kb=False` | `verified=1`, `stored=0` |
| Bounded staging provider với `OLLAMA_TIMEOUT=1`, Ollama-only | `asked=1`, `verified=0`, `stored=0`, `elapsed≈1.5s` |
| Empty policy candidate promotion | Rejected, exit `4` |
| Runtime integration với staging DB | `SOURCE_RELIABILITY` materialized/promoted/applied; active policy tồn tại; ledger tồn tại |
| Pytest sau R43b + integration | `55 passed` |
| Portable reality sau R43b + integration | `73/73 pass`, timeout `0`, error `0` |

Trong DB staging integration, 44 `VERDICT_*` history rows không bị mark applied; chỉ 1 lesson policy hợp lệ được apply. Đây là hành vi mong muốn: không biến verdict history thành policy giả.

## Remaining gaps

R43 đã đóng lỗi “stored nhưng không có policy handoff”, nhưng chưa chứng minh policy đã cải thiện verdict. Cần bước tiếp theo là bounded A/B experiment trên cùng corpus với metrics false-PASS, false-FAIL, calibration và routing delta. Cũng cần health/ledger cho background thread start failure, compounding query failure và per-source/news fetch failure; hiện các nhánh này không ghi fact sai nhưng có thể làm hệ thống học ít hơn mà chỉ xuất hiện trong log.

Production `.env` dangerous flags vẫn phải được promote riêng theo change window. R43 không tự sửa `.env` production và không bật closed loop production.

## R43c: stale-policy và timeout hardening

R43c sửa thêm hai failure mode. `RealityJudge._get_exp_policies()` now clears the in-memory policy cache when `active_policies.json` is missing, malformed or hash-mismatched; it no longer keeps a stale policy active after the artifact disappears or is corrupted. `learning_staging_r43.py` now forces a bounded `OLLAMA_TIMEOUT` (default 5 seconds, maximum 30 seconds) and records the timeout in its staging manifest.

R43c loader contract test trên Windows pass cho bốn trường hợp: missing clears cache, corrupt JSON clears cache, valid hash loads, hash mismatch clears cache.
