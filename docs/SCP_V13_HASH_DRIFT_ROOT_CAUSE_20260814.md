# SCP DNA — Root Cause Analysis: `data\v13.db` Hash Drift

**Ngày:** 2026-08-14  
**Phạm vi:** PC thật `C:\Users\check\Downloads\scp`, supervisor 24/7 và bounded outage test  
**Kết luận:** Hash thay đổi vì `v13.db` là **runtime database đang được ghi bởi SCP Python/background writers**, trong khi supervisor đã từng thoát nhưng các child service vẫn còn sống. Đây không phải bằng chứng DB bị corrupt và cũng không phải lỗi của SHA-256. Lỗi kiến trúc quan trọng là **child process không bị containment khi supervisor bị terminate**, khiến runtime writer tiếp tục chạy ngoài watchdog và làm thay đổi DB sau test.

## 1. Vấn đề cần giải thích

Trong bounded outage test trước, SHA-256 của `data\v13.db` sau test không còn khớp baseline. Cần phân biệt bốn giả thuyết: hash được tính sai; SQLite đang corrupt; test harness tự ghi DB; hoặc một runtime process khác tiếp tục ghi DB trong lúc test và sau khi supervisor mất.

Kết luận không được dựa vào một hash duy nhất. Hash của SQLite main file không đại diện đầy đủ cho logical state khi WAL đang tồn tại; phải kiểm tra cả WAL/SHM, SQLite integrity, row counts, process lineage và timeline của loop/audit logs.

## 2. Chuỗi “Tại sao?”

**Tại sao hash thay đổi?** Vì bytes của SQLite main file/WAL thay đổi sau baseline.

**Tại sao bytes thay đổi?** Vì các bảng runtime tăng row trong khi PC vẫn có Python SCP process sống: `question_events`, `question_log`, `healing_history` và `pending_reverification` đều tăng.

**Tại sao Python vẫn ghi khi supervisor đã không còn chạy?** Vì bốn child service được tạo bằng `Start-Process` nhưng không thuộc Windows Job Object. Khi PowerShell supervisor bị terminate bên ngoài, `finally` của script không được bảo đảm chạy; child processes trở thành orphan và vẫn tiếp tục background work.

**Tại sao child vẫn có thể ghi?** `api_server.py` khởi tạo các learning/judge components dùng `data\v13.db`; `judgecore_mixin.py` gọi `QuestionTracker` để log mỗi question; các cognitive/reverification paths ghi các bảng runtime khác. `SCP_ENABLE_CLOSED_LOOP=0` ngăn policy closed-loop promotion, nhưng không đồng nghĩa mọi runtime telemetry/background writer đều trở thành read-only.

**Tại sao chỉ nhìn supervisor ledger có thể bỏ sót?** Vì supervisor ledger chỉ ghi lifecycle của supervisor. Sau khi PID supervisor biến mất, child process vẫn phục vụ port và vẫn ghi DB; không còn watchdog nào ghi `HEALTHY` hoặc `SUPERVISOR_ERROR` cho chúng. Đây là một observation gap đúng theo SCP DNA.

## 3. Evidence map độc lập

| Lineage | Evidence thực tế | Ý nghĩa |
|---|---|---|
| SQLite integrity | `PRAGMA integrity_check = ok` ở mọi lần read-only audit | Không có evidence DB corrupt |
| Row-count timeline | T0/T45/T90: `question_events 17097 → 17156 → 17191`; `question_log 14907 → 14930 → 14947`; `healing_history 28662 → 28761 → 28820`; `pending_reverification 1978 → 1984 → 1989` | DB vẫn bị ghi trong khi supervisor `Ready` |
| File/WAL timeline | DB mtime tăng tới khoảng `15:55:31Z`; WAL mtime tăng tới `15:56:19Z` | Có write activity thật, không chỉ hash calculation noise |
| Task state | `SCP-247-Supervisor = Ready`, supervisor PID không còn tồn tại, nhưng 4 ports vẫn listen | Child services đã thoát khỏi watchdog containment |
| Process lineage | Các listener có parent chain qua các PID orphan; sau Job Object patch, mọi listener đều có ancestor là supervisor PID | Xác nhận nguyên nhân orphan và hiệu quả containment |
| Loop log | `loop_runs.jsonl` đứng ở 17 dòng trong cửa sổ T45/T90; không có cron run mới trong phần còn lại của cửa sổ | DB writes sau đó không thể quy toàn bộ cho Loop Scheduler cron |
| Source code | `api_server.py` tạo `RealLearningEngine`/`FastLearningEngine`; `judgecore_mixin.py` gọi `QuestionTracker`; loop scheduler POST `/v105/autofix/run-audit` | Có các runtime write lineage độc lập với supervisor ledger |

Các dòng evidence trên có rủi ro shared-origin nếu chỉ xem source code. Vì vậy kết luận chính dựa trên **process state + WAL/mtime + row-count delta**, còn source code chỉ dùng để giải thích cơ chế.

## 4. Root cause được xác nhận và phần chưa thể quy kết

Root cause đã được xác nhận ở mức **runtime DB drift do orphanable child processes**. Khi supervisor `Ready` nhưng các service vẫn sống, row counts và WAL tiếp tục tăng; sau khi dừng chính xác bốn orphan listeners, DB writer activity không còn nằm ngoài supervisor.

Chưa thể quy kết 100% mọi row được thêm trong toàn bộ khoảng test chỉ cho bounded outage harness. Có thể có ba nguồn trộn lẫn: background writer của SCP Python, một cron audit trước khi Loop Scheduler pause, và các side effects của outage/recovery. Vì vậy báo cáo không gọi đó là “policy mutation” nếu chưa có row-level provenance; chỉ gọi đúng là **runtime telemetry/database drift**.

## 5. Lỗi đã bắt được trong test harness

Reality testing đã phát hiện bốn lỗi độc lập:

| Lỗi | Tác động | Bản vá |
|---|---|---|
| Dùng biến `$pid` | Đụng automatic read-only variable `$PID` của PowerShell | Đổi thành `$targetPid` |
| Single-cycle `.Count` | Single object không có property `.Count` như dự kiến | Ép pipeline thành `@(...)` |
| `$snapshotExit:` trong string | PowerShell parser hiểu sai variable reference trước dấu `:` | Dùng `${snapshotExit}` |
| `fsync` trên read-only/đã đóng descriptor | Snapshot utility exit non-zero dù DB copy đã tạo | Fsync trên handle mở đúng mode; manifest atomic |

Sau bản vá, harness parse với `PARSE_ERRORS=0` và chạy một cycle với `HARNESS_EXIT=0`. Evidence ghi `preflight=PASS`, snapshot manifest `COMPLETE`, `recovered=true`, recovery 1 giây, task vẫn `Running`, cả bốn port `true` và LLM Bridge HTTP 200.

## 6. Bản vá supervisor: Windows Job Object

Supervisor hiện tạo Windows Job Object với `JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE` và assign mỗi child process vào job ngay sau `Start-Process`. Nếu PowerShell, Task Scheduler hoặc supervisor bị terminate ngoài dự kiến, handle Job Object đóng và Windows dừng toàn bộ descendants. Nếu assignment thất bại, supervisor taskkill process vừa tạo rồi fail-closed thay vì chạy child ngoài containment.

Reality test trực tiếp đã terminate supervisor PID. Kết quả trước recovery:

| Kiểm tra | Kết quả |
|---|---|
| Port 3000 | `False` |
| Port 3030 | `False` |
| Port 8000 | `False` |
| Port 11434 | `False` |
| Task | `Ready` |

Sau `Start-ScheduledTask`, cả bốn port trở lại `True`, task `Running`; process lineage của mọi listener đều có ancestor là supervisor PID. Đây là bằng chứng mạnh hơn việc chỉ nhìn port.

## 7. Snapshot SQLite v2 — quy trình tối ưu

Snapshot utility mới dùng SQLite backup API qua connection `mode=ro`, không copy thô file đang có WAL. Với mỗi DB, utility thực hiện các bước sau:

1. Tạo thư mục snapshot duy nhất theo UTC timestamp và label; không overwrite snapshot cũ.
2. Ghi metadata của main DB, `-wal` và `-shm` trước snapshot.
3. Mở source read-only, chạy `PRAGMA integrity_check`, rồi dùng `Connection.backup()` sang DB đích.
4. Commit DB snapshot, chạy `PRAGMA integrity_check` trên snapshot và lưu row counts của mọi table.
5. Ghi metadata source sau snapshot và đánh dấu `source_changed_during_snapshot` nếu file/WAL/SHM thay đổi.
6. Ghi manifest tạm rồi `flush + fsync + os.replace` thành `manifest.json` atomic.
7. Chỉ trả exit code 0 khi đủ cả `v13.db` và `kb_evolve.sqlite`, source/snapshot đều integrity `ok`, không có error; nếu thiếu thì status `INCOMPLETE` và exit code 2.

Snapshot mới đã chạy trên PC với `status=COMPLETE`, cả hai DB `source_integrity=ok`, `snapshot_integrity=ok`, và manifest nằm trong `.private-secrets\release-audit\scp-247\experiments\snapshots`. Đây là rollback artifact nhất quán sau cleanup/recovery.

## 8. Quy trình fault injection mới

Không chạy outage test nếu supervisor không ở trạng thái `Running`, kill switch đang tồn tại, thiếu snapshot utility, thiếu Python venv, thiếu một trong bốn port hoặc LLM Bridge không healthy. Harness phải tạo pre-test snapshot trước khi kill process. Sau mỗi cycle, harness kiểm tra LLM Bridge phục hồi và supervisor vẫn `Running`; nếu một cycle fail thì dừng ngay, ghi `FAIL_CLOSED`, không tiếp tục làm hỏng hệ thống.

Rollback phải theo thứ tự: tạo kill switch; chờ supervisor dừng children hoặc dùng process-containment recovery; xác nhận bốn port đóng; chỉ restore snapshot khi không còn writer; chạy integrity và row-count verification; sau đó start task mới. Không restore DB khi SCP Python còn sống vì sẽ tạo race và có thể làm hỏng snapshot.

## 9. Những gì đã được chứng minh sau bản vá

| Claim | Trạng thái |
|---|---|
| Harness không còn các lỗi `$PID`, single-cycle count và interpolation parser đã phát hiện | Đã sửa và chạy `PARSE_ERRORS=0`, `HARNESS_EXIT=0` |
| Snapshot tạo được copy nhất quán | Đã có manifest `COMPLETE`, integrity `ok` |
| Supervisor không để child orphan khi bị terminate trực tiếp | Đã test: 4 port đóng sau external kill |
| Supervisor recovery sau external kill | Đã test: 4 port trở lại, task `Running` |
| Listener hiện thuộc containment lineage | Đã test: 4 listener có ancestor supervisor |
| Closed loop/policy promotion không bị bật bởi test | Harness ghi `env_touched=false`, `policy_touched=false`; `SCP_ENABLE_CLOSED_LOOP=0` |

## 10. Giới hạn còn mở

`v13.db` vẫn là runtime DB writable trong chế độ SCP đang chạy. Job Object giải quyết orphan process, nhưng không biến background writers thành read-only. Nếu yêu cầu test tuyệt đối không mutate production DB, cần chạy fault injection trên staging clone hoặc bổ sung một observation-only runtime contract có kiểm tra fail-closed trước startup, thay vì chỉ dựa vào `SCP_ENABLE_CLOSED_LOOP=0`.

Cold boot, logon, sleep/hibernate, disk-full ledger, provider outage kéo dài qua restart window và quyền user bị thay đổi vẫn chưa được chứng minh. Không có evidence nào cho phép tuyên bố SCP bắt được mọi cuộc tấn công AI hoặc con người.

## 11. References

[1] [Supervisor Job Object patch — commit `fff3976`](https://github.com/checken1994/GA-LAB/commit/fff3976c9c527550ca2a648562993f80ec104ade)  
[2] [Snapshot and harness hardening — commit `0ab9278`](https://github.com/checken1994/GA-LAB/commit/0ab92786adb1d0d3bb21a7e9098fe31d89d36a1e)  
[3] [Snapshot fsync fixes — commits `7c9d17e` and `4594172`](https://github.com/checken1994/GA-LAB/commit/459417259cfc02efd45ade9613d1c785c893384a)  
[4] [Harness interpolation fix — commit `0401ccc`](https://github.com/checken1994/GA-LAB/commit/0401ccc6befadbe63e769344525f2e1a3bcf763f)
