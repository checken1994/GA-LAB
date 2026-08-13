# SCP DNA — Đối chiếu báo cáo với thực tế và phân tích Durable Learning/Evolution

**Đối tượng:** `C:\Users\check\Downloads\scp`
**Repository:** `checken1994/GA-LAB`, nhánh `main`
**Mục đích:** Cập nhật các kết luận trong báo cáo được cung cấp theo trạng thái thật trên PC và Git working tree; phân biệt snapshot lịch sử, code hiện tại, runtime data và bằng chứng độc lập.

> **Nguyên tắc:** `PASS` chỉ có nghĩa là chưa phát hiện lỗi trong phạm vi test và dữ liệu hiện tại. Nó không chứng minh rằng toàn bộ hệ thống đã đúng tuyệt đối.

## 1. Đánh giá nhanh nội dung báo cáo được cung cấp

Báo cáo được cung cấp **đúng về hướng cảnh báo**, nhưng nhiều số liệu là snapshot cũ hoặc đến từ lineage tự kiểm toán. Nó không còn mô tả đầy đủ trạng thái PC hiện tại.

| Claim trong báo cáo | Đối chiếu hiện tại | Kết luận cập nhật |
|---|---|---|
| Clone/repository không đầy đủ, không thể chạy đầy đủ | PC hiện có working tree với 761 tracked files; `pytest 9.1.1` có trong `scp/venv` | Claim này đã lỗi thời cho PC hiện tại |
| Pytest thiếu | `scp/venv\Scripts\python.exe -m pytest --version` trả `pytest 9.1.1` | False alarm trong trạng thái hiện tại |
| Reality baseline có 0 service | `reality-tests-results.json`: 73 tests, 73 PASS, 0 FAIL, 0 TIMEOUT, 0 ERROR; hiện port 8000 và 11434 đang LISTEN | Snapshot baseline không được dùng thay cho current state |
| Results có `pass:null` | Results array hiện không có field `pass`; dùng `status=PASS`; 0 result có field `pass` | Claim cũ nhầm `summary.pass` với result schema |
| R20 `84/84 fixed`, `67 reality-tests`, `159 CI assertions` | Current release artifact đang dùng native result 73/73 và contract evidence 11/11 ở rerun gần nhất; trước đó release-contract suite có 36/36 | Hai bộ số khác scope/version, không được cộng hoặc so trực tiếp |
| DEV/auto-approve/relaxation flags còn bật | `.env` hiện tại: `SCP_DEV_MODE=1`, `SCP_AUTO_APPROVE_TIER3=1`, `SCP_TIER3_ALLOW_RELAXATION=1`, `SCP_TIER3_ALLOW_BAREEXCEPTPASS=1`, `SCP_EVOLUTION_AUTO=1` | Finding thật; candidate đã fail-closed nhưng chưa được tự ý promote |
| Tài liệu và code lệch phase | Vẫn đúng một phần: root có README/R20/baseline và audit rounds cũ; docs có nhiều round cũ; working tree còn thay đổi chưa commit | Finding lineage/documentation drift vẫn còn |
| “84/84 + 0 failures” đủ chứng minh production | Không đúng theo DNA #22; đây chỉ là PASS trong scope/commit/test harness tương ứng | Kết luận production phải dựa trên current packaged smoke và external lineage |

### Git state hiện tại

HEAD local là `d80c24645eb7d0a85b0485de23ab1f70dc01d93a`, nhánh `main`; remote `origin/main` cùng trỏ tới commit đó tại thời điểm kiểm tra. Tuy nhiên working tree **không sạch**. Các thay đổi chưa đồng bộ gồm:

| Nhóm | Trạng thái |
|---|---:|
| File tracked modified | 4: `reality-tests-results.json`, `scp/api_server.py`, `scp/api_server_parts/helpers.py`, `tests/reality-tests/reality_4-a-005.py` |
| File untracked | 10, gồm benchmark, route mới, evidence filter, patch scripts và một smoke test |
| Data/runtime | Không nên push trực tiếp; `.gitignore` loại `**/data/` và `**/runtime/` |

Vì vậy, câu “đã đồng bộ repo lên GitHub” chỉ đúng cho commit `d80c246...`; **không đúng nếu hiểu là mọi thay đổi hiện có trên PC đã được push**. Báo cáo này được tạo như một commit riêng, không gom các file untracked/scratch chưa được review.

## 2. Vì sao một số file test không nằm trong `tests/`?

Câu trả lời là **không phải mọi file có chữ `test`, `audit`, `reality` đều là test case**. Repository hiện có khoảng 103 tracked files dưới `tests/`, trong đó có 73 Python reality tests. Những file nằm ngoài `tests/` thuộc nhiều vai trò khác nhau.

| Ví dụ | Vai trò thật | Có nên chuyển vào `tests/` không? |
|---|---|---|
| `tests/reality-tests/reality_*.py` | Test case reality độc lập | Đã ở đúng vùng; nên chuẩn hóa tên/marker |
| `run_reality_tests_portable.py` | Test runner/orchestrator cấp repository | Không nên coi là test case; nên đặt ở `tools/` hoặc giữ root làm entrypoint |
| `scripts/test_resilient_browser.ps1`, `scripts/test_resilient_full.ps1` | Operator/integration scripts gọi service thật trên Windows | Có thể đưa vào `tests/integration/windows/`, nhưng trước hết phải bỏ hardcoded user path và thêm preflight |
| `scp/autofix/runner_phases/reality_test.py` | Production engine dùng trong autofix pipeline | Không được chuyển; đây là code sản phẩm, không phải test fixture |
| `scp/core/reality_engine.py` | Production module chứa logic reality | Không được chuyển |
| `scp/autofix/audit_log.py`, `scp/api/routes/audit_routes.py` | Audit implementation/route | Không được chuyển |
| `scripts/*.py` patch/benchmark | Tooling hoặc one-shot migration | Nên phân loại vào `tools/`, `scripts/migrations/`, hoặc archive; không mặc định là pytest |

Điểm yếu thật không phải “tất cả test bị đặt sai”, mà là **naming và taxonomy chưa đủ rõ**. Người review dùng filename search sẽ dễ nhầm production `reality_engine` với test, hoặc bỏ sót operator scripts ngoài `tests/`.

### Cấu trúc đề nghị, không big-bang move

```text
tests/
  unit/
  integration/
    windows/
    services/
  reality/
  fixtures/
  contract/
tools/
  reality_runner/
  migrations/
scripts/
  operator/
docs/
  architecture/
  audits/
    rounds/
  operations/
  releases/
evidence-manifests/
```

Không nên di chuyển ngay toàn bộ 103 file. Bước an toàn là thêm `tests/README.md` ghi contract, phân loại từng file, cập nhật CI path, rồi di chuyển từng batch nhỏ với backup/tag và chạy lại pytest + reality suite sau mỗi batch.

## 3. Vì sao tài liệu văn bản nằm ở thư mục chính?

Root hiện có 9 tài liệu text/markdown, gồm `README.md`, `ROUND20-README.md`, `WINDOWS-README.md`, các audit round 12–15 và baseline snapshot. Đây thường là di sản của nhiều phase:

1. `README.md` và `WINDOWS-README.md` là entrypoint nên hợp lý ở root.
2. `ROUND20-README.md` là tài liệu release/phase nên có thể ở root trong ngắn hạn, nhưng không nên trở thành README thứ hai không có index.
3. `SCP_DNA_AUDIT_ROUND12–15.md` và `SCP_20_BASELINE_*.txt` là historical audit/evidence, nên nằm dưới `docs/audits/rounds/` và `evidence-manifests/` nếu đã chuẩn hóa.
4. `docs/` hiện đã có 31 tài liệu nhưng tất cả nằm phẳng trong một thư mục, chưa có `audits/`, `archive/`, `operations/` hoặc index rõ ràng.
5. Data runtime như `data/v13.db`, `kb_evolve.sqlite`, JSONL audit và secrets **không nên đưa lên GitHub**. `.gitignore` loại `**/data/`, `.env`, `.private-secrets/`, `desktop/runtime/` và `desktop/release/`. Đây là đúng về bảo mật, nhưng cần manifest đỏacted để người khác biết evidence nào tồn tại mà không cần commit dữ liệu nhạy cảm.

Do đó, việc tài liệu nằm ở root phản ánh **repository chưa có information architecture ổn định**, không phải vì tài liệu phải nằm ngoài hệ thống lưu trữ. Cách sửa an toàn là tạo index và phân loại trước; không tự động move hàng chục file vì sẽ làm hỏng liên kết lịch sử và README.

## 4. Root-cause sâu của Durable Learning bị trống

### 4.1. Có nhiều lớp “learning” nhưng không cùng nghĩa

Hiện có ít nhất ba lớp state:

| Lớp | Store | Trạng thái thực tế |
|---|---|---:|
| Fast/real learning durable facts | `data/v13.db`, bảng `knowledge` | 0 rows |
| Error/knowledge JSONL store | `data/error_store.jsonl`, `data/knowledge_store.jsonl` | Có dữ liệu store riêng; đây không phải cùng bảng `v13.db` |
| Live cache | `data/v13.db`, `live_knowledge_cache` | 194 rows |

`live_knowledge_cache=194` chỉ chứng minh cache/query results đã từng được ghi. Nó không chứng minh fact đã đi qua verification và được promote vào bảng durable `knowledge`.

### 4.2. Learning engine có startup hook nhưng chưa có success invariant

`scp/api_server_parts/helpers.py` gọi `start_fast_learning_thread(scp_db_path="data/v13.db", data_dir="data")`. `FastLearningEngine` có các loop Ollama/local/news, verification và adaptive interval. Tuy nhiên, hiện không có health invariant bắt buộc kiểu:

```text
one verified learning cycle
→ durable knowledge row increases
→ source/confidence/verified_at/evidence hash exists
→ status is persisted and exposed
```

Nếu provider fail, Wikipedia verification fail, answer bị lọc, DB path lệch, thread dừng hoặc exception bị log ở debug, hệ thống có thể vẫn trả status/telemetry mà không tạo durable fact. Đây là cơ chế **“attempted learning” nhưng không có write-proof**.

### 4.3. `knowledge_versions=781` là tín hiệu gây hiểu nhầm

`data/v13.db` có 781 rows trong `knowledge_versions`, nhưng aggregate hiện tại là:

```text
change_type = delete: 781
source = PolicyApplier: 781
```

Đây là lịch sử policy cleanup/deletion, không phải evidence rằng engine đã học được 781 fact. Việc dùng row count tổng mà không phân loại `change_type/source` là một lỗi measurement theo DNA #22.

### 4.4. Những nguyên nhân cần kiểm chứng riêng

Không nên kết luận chỉ một nguyên nhân. Các khả năng cần instrument:

| Hypothesis | Evidence hiện tại | Cách kiểm chứng |
|---|---|---|
| Learning thread chưa chạy | Startup hook tồn tại, nhưng chưa có run ledger | Ghi `learning_runs` start/end/error/rows_before/rows_after |
| Provider hoặc verifier fail | Chưa có durable failure ledger trong report hiện tại | Mock provider/verifier và ghi reject reason theo cycle |
| Verification reject toàn bộ | Có verification layer trong code, chưa có counters persisted | Expose `asked/answered/verified/rejected/stored` và lưu cùng run |
| Ghi nhầm DB/path | Engine default là `data/v13.db`, nhưng singleton/config cần trace | Log absolute canonical DB path + inode/file hash, không log secret |
| Thread exception bị nuốt | Nhiều loop dùng non-fatal logging | Persist terminal status `FAILED`/`DEGRADED`, không chỉ logger.debug |
| Evolution không được gọi | `save_lesson()` chỉ xuất hiện trong `reflectmixin.py`; `evolve_cycle()` được gọi thực tế tại CLI `scp/autofix/runner.py --evolve` | Thêm admin-triggered run ledger và test callsite |

## 5. Root-cause sâu của Evolution `0 lessons / 0 patterns`

### 5.1. Writer hoạt động; pipeline không tạo input production

Smoke test cô lập đã tạo `Lesson` và `EvolvedPattern` qua `KBAccumulationStore.save_lesson()` và `save_pattern()` trên database tạm; kết quả `saved_lesson=true`, `saved_pattern=true`, `pattern_count=1`. Vì vậy, trạng thái 0 trong `data/kb_evolve.sqlite` **không phải bằng chứng writer hỏng**.

Callsite thực tế của writer chỉ nằm trong `scp/autofix/evolution_parts/reflectmixin.py`:

```text
extract_lesson_from_reflect(result, fix_verified=True)
→ if lesson: save_lesson(lesson)
→ extract_pattern_from_lesson(lesson)
→ if pattern: save_pattern(pattern)
```

Hàm này chạy trong luồng `reflect()` của autofix evolution. `evolve_cycle()` được gọi ở `scp/autofix/runner.py` qua nhánh CLI `--evolve`; không có evidence rằng FastLearningEngine background loop tự gọi `evolve_cycle()`.

### 5.2. Gate tự falsify có thể chặn lesson — đúng về an toàn nhưng thiếu observability

`extract_lesson_from_reflect()` trả `None` nếu `reflect_result.self_falsified` là true. Đây là gate đúng: không học từ một fix đã tự bác bỏ. Hàm có fallback lesson khi LLM trả rỗng hoặc trả search/replace block. Nhưng nếu gate trả None hoặc `reflect()` không chạy, hiện không có `evolution_runs`/`lesson_rejections` ledger cho biết:

```text
cycle started = ?
reflects = ?
self_falsified = ?
lesson_candidate = ?
lesson_saved = ?
pattern_saved = ?
```

Vì không có các counters này, bảng 0 không phân biệt được “chưa chạy”, “chạy nhưng bị reject” và “ghi DB lỗi”.

### 5.3. `SCP_EVOLUTION_AUTO=1` không đồng nghĩa evolution đã chạy

`CodeEvolutionAgent` đọc `SCP_EVOLUTION_AUTO`; flag này chọn auto/manual mode khi agent được dùng. Nó không tự tạo scheduler cho `--evolve`. Vì thế cấu hình `.env` hiện có `SCP_EVOLUTION_AUTO=1` là **rủi ro quyền hạn**, nhưng không phải nguyên nhân làm DB có dữ liệu. Nó có thể mở cửa cho auto-apply nếu một caller khác kích hoạt agent, trong khi hiện không có evidence rằng caller production đã chạy.

Candidate đặt `SCP_EVOLUTION_AUTO=0`, phù hợp với production fail-closed. Không được tự ý thay `.env` hiện tại nếu chưa có human approval.

### 5.4. `evolution_audit.jsonl` rỗng là missing run ledger

`evolution_audit.jsonl` rỗng không chứng minh “evolution failed”; nó cho thấy hệ thống không có observable event bắt buộc cho toàn bộ vòng evolution. `reflect` có reflect log/counters riêng, còn KB store ghi lesson/pattern riêng; thiếu một `run_id` xuyên suốt nối scanner → WHY → fix → verify → lesson → pattern → commit/rollback.

## 6. Remediation đề nghị, nhỏ và có rollback

### P0 — Fail-closed trước khi bật persistence mới

Không sửa trực tiếp `.env` hiện tại trong bước này. Candidate phải giữ:

```text
SCP_EVOLUTION_AUTO=0
SCP_DEV_MODE=0
SCP_AUTO_APPROVE_TIER3=0
SCP_TIER3_ALLOW_RELAXATION=0
SCP_TIER3_ALLOW_BAREEXCEPTPASS=0
```

Khi được human approval, backup `.env` với timestamp + SHA-256, promote candidate, chạy config gate và giữ backup để rollback nguyên file. Không rotate/revoke provider key.

### P1 — Thêm run ledger cho learning và evolution

Tạo một store riêng, ví dụ `data/learning_runs.jsonl` và `data/evolution_runs.jsonl`, hoặc bảng SQLite tương ứng. Mỗi run phải có:

```text
run_id, mode, started_at, ended_at, status,
source_revision, input_hash, db_path_hash,
asked, answered, verified, rejected, stored,
lessons_candidate, lessons_saved, patterns_saved,
approval_id, before_hash, after_hash, rollback_token,
error_class, error_summary
```

Không ghi API key, full answer nhạy cảm, IP hoặc token. `status=SUCCESS` chỉ được phép khi có write-proof hoặc status `NO_NEW_FACTS` với counters rõ ràng.

### P1 — Tách candidate khỏi durable state

Learning không ghi thẳng vào bảng durable. Chuỗi nên là:

```text
provider answer
→ provenance record
→ verification
→ candidate fact/lesson
→ policy/HITL gate
→ durable knowledge/pattern
→ version history
```

`knowledge_versions` phải phân loại rõ `insert`, `update`, `delete`, `reject`, `rollback`; dashboard không được gọi tổng row count là “số kiến thức đã học”.

### P1 — Nối evolution bằng một trigger có kiểm soát

Giữ evolution manual/admin-authenticated ở production. Có thể dùng CLI hiện tại làm trigger đầu tiên, nhưng phải tạo run ledger trước và sau `--evolve`. Nếu sau này thêm endpoint, endpoint phải yêu cầu admin auth, `dry_run=true` mặc định, không auto-commit, và trả run_id để theo dõi.

### P1 — Không nuốt lỗi ở debug-only

Các exception trong learning/evolution phải ghi `FAILED` hoặc `DEGRADED` vào ledger với error class và stage. Logger vẫn được dùng, nhưng không được là nơi duy nhất chứa nguyên nhân. Thread background phải có watchdog và health status.

### P2 — Pytest coverage bắt buộc

| Test | Expected assertion |
|---|---|
| Verified learning cycle với mock provider/verifier | `stored=1`, durable `knowledge` tăng đúng 1, source/confidence/evidence hash có mặt |
| Provider failure | `status=FAILED`, `stored=0`, error stage persisted; không silent PASS |
| Verification reject | `status=NO_NEW_FACTS` hoặc `REJECTED`, không ghi durable fact |
| Self-falsified reflect | lessons/patterns không tăng; `lesson_rejected_self_falsified` tăng |
| Valid reflect/evolve | `lessons=1`, `patterns=1`, run ledger `SUCCESS` |
| Duplicate lesson | occurrence count tăng, không tạo bản ghi trùng |
| Rollback | before/after hash khôi phục được, run ledger ghi rollback token |
| Production config | test fail nếu `SCP_EVOLUTION_AUTO=1` hoặc bypass flags ACTIVE |
| DB path | engine và health endpoint báo cùng canonical DB path |

### P2 — Test data không được ghi vào production data

Mỗi pytest dùng `tmp_path`; mỗi reality test có data dir riêng; sau test phải assert không sửa `data/v13.db`, `data/kb_evolve.sqlite`, `.env` hoặc runtime artifact. Chỉ commit schema/migration, tests và redacted manifest; không commit DB runtime.

## 7. Cách đồng bộ lên GitHub an toàn

Commit report này như một thay đổi tài liệu độc lập. Không stage các file untracked benchmark/patch/scratch trong working tree hiện tại khi chưa review. Không stage `.env`, `data/`, `desktop/runtime/`, `desktop/release/` hoặc `.private-secrets/`.

Sau khi commit report, cần kiểm tra:

```text
git diff --cached --check
git diff --cached -- docs/SCP_DNA_RECONCILIATION_R20.md
pytest -q tests/test_release_contracts.py
python -m compileall -q scp
```

Sau đó push commit report-only. Các thay đổi source còn lại phải được tách thành commit chức năng riêng, mỗi commit có backup/reality evidence; không gộp chúng vào commit tài liệu chỉ để làm working tree sạch.

## 8. Trạng thái kết luận

| Hạng mục | Kết luận |
|---|---|
| Báo cáo được cung cấp | Có giá trị như historical/self-audit snapshot, nhưng không còn đồng bộ hoàn toàn với PC hiện tại |
| Test files ngoài `tests/` | Phần lớn là production modules, runners hoặc operator scripts; taxonomy chưa rõ, không phải toàn bộ bị đặt sai |
| Tài liệu ở root | README/entrypoint hợp lý; historical audit/baseline nên phân loại vào `docs/audits` và evidence manifest |
| Durable learning | Có engine/startup hook/cache, nhưng durable fact table hiện 0; thiếu write-proof và run ledger |
| Evolution | Writer hoạt động trong smoke; production pipeline không có evidence đã gọi; `0 lessons/0 patterns` chủ yếu chỉ ra “chưa có verified evolution run” |
| `.env` production | Đang unsafe do auto/bypass flags; chưa tự ý sửa |
| GitHub synchronization | Remote HEAD khớp commit d80c246; working tree hiện có thay đổi chưa push; report này được sync riêng |
| Production readiness của learning/evolution | **Chưa đủ evidence để tuyên bố** |

### Evidence nội bộ chính

- `reality-tests-results.json`: 73 PASS, 0 FAIL/TIMEOUT/ERROR, results không có field `pass`.
- `scp/venv`: pytest 9.1.1.
- `data/v13.db`: `knowledge=0`, `knowledge_memory=0`, `memory=0`, `knowledge_versions=781` nhưng 100% `delete/PolicyApplier`, `live_knowledge_cache=194`.
- `data/kb_evolve.sqlite`: schema tồn tại nhưng `lessons=0`, `evolved_patterns=0`.
- `data/evolution_audit.jsonl`: rỗng.
- `scp/meta/kb_evolve.py`: public writer smoke đã PASS trên temp DB.
- `scp/autofix/evolution_parts/reflectmixin.py`: writer chỉ được gọi sau `reflect`/lesson gate.
- `scp/autofix/runner.py`: `evolve_cycle()` được gọi qua CLI `--evolve`.
- `docs/`: 31 tài liệu phẳng; root có 9 text/markdown tracked.
- Git HEAD/remote: `d80c24645eb7d0a85b0485de23ab1f70dc01d93a`.
