# SCP 24/7 — Báo cáo Reality Test Failure Paths

**Ngày:** 2026-08-14  
**PC thật:** `C:\Users\check\Downloads\scp`  
**Supervisor:** `SCP-247-Supervisor`  
**Kết luận hiện tại:** **Canary 24/7 đang chạy và đã chứng minh được recovery/circuit-breaker trong một phạm vi hẹp; chưa có cơ sở để tuyên bố mọi điều kiện 24/7 đều đã được chứng minh.**

## 1. Vì sao cần kiểm thử gián đoạn?

Trước thử nghiệm, không có lỗi đang quan sát được: cả bốn service đều healthy và trả HTTP 200. Kiểm thử outage không nhằm chứng minh rằng hệ thống đang hỏng; nó kiểm tra một đường hành vi chỉ xuất hiện khi có lỗi. Nếu không làm gián đoạn có kiểm soát, không thể biết supervisor có restart đúng, có dừng ở restart budget, có mở circuit hay có vô tình bật learning/policy promotion khi provider mất kết nối.

Đây là một thử nghiệm nhỏ và có rollback: chỉ dừng process LLM Bridge bằng PID hiện đang listen trên loopback; không sửa `.env`, không thay đổi firewall, không rotate provider key, không promote policy, không dừng Ollama, Python system hay phần mềm ngoài phạm vi SCP. Sau test, operator kill switch được dùng để đưa supervisor về trạng thái sạch rồi khởi động lại.

## 2. Baseline trước thử nghiệm

Trước outage test, Task Scheduler ở trạng thái `Running`, kill switch không tồn tại, bốn port 3000/3030/8000/11434 đều listen, bốn endpoint health trả 200, năm dangerous flags và `SCP_ENABLE_CLOSED_LOOP` đều OFF. SHA-256 của `.env` và `data\kb_evolve.sqlite` được ghi vào baseline; `v13.db` được đọc qua FileShare để không dừng SCP.

Một lỗi quy trình cần ghi rõ: baseline ban đầu có **hash nhưng chưa có byte-for-byte SQLite snapshot trước test**. Vì vậy không thể tuyên bố có rollback hoàn chỉnh về đúng byte trạng thái trước outage. Sau test đã tạo snapshot nhất quán bằng SQLite backup API cho cả `v13.db` và `kb_evolve.sqlite`; snapshot này là rollback artifact của trạng thái sau test, không phải snapshot pre-test.

## 3. Lỗi thực tế trong chính test harness

Reality test đã bắt được hai lỗi của script kiểm thử trước khi dùng kết quả làm evidence. Lỗi thứ nhất là dùng biến `$pid`, đụng biến tự động chỉ-đọc `$PID` của PowerShell. Lỗi thứ hai là đọc `.Count` trên một single object khi chỉ chạy một cycle. Cả hai lỗi đã được sửa, commit, tải lại từ GitHub và chạy lại; lần chạy một cycle cuối cùng trả `TEST_EXIT=0`, LLM Bridge hồi phục sau 14 giây, port 11434 và HTTP endpoint trở lại 200.

Điều này có ý nghĩa: **PASS của service không tự động làm cho harness đúng**. Harness cũng phải được reality-tested trước khi tin vào verdict của nó.

## 4. Bounded outage một cycle

| Tiêu chí | Evidence |
|---|---|
| Đối tượng | Chỉ LLM Bridge, port 11434 |
| Process bị dừng | PID thực tế tại thời điểm test |
| Production `.env` | `env_touched=false` |
| Policy | `policy_touched=false` |
| Kill switch | Không có trước và sau |
| Recovery | `recovered=true` |
| Thời gian recovery | 14 giây trong lần chạy cuối |
| Sau test | Port 11434 listen, HTTP `/api/tags` = 200 |

Supervisor ghi `STOP`, `START`, `RESTART` và sau đó ghi `HEALTHY`. Đây là bằng chứng trực tiếp rằng một provider-sidecar outage ngắn được phát hiện và phục hồi trong watchdog loop.

## 5. Circuit-breaker test

Circuit test được yêu cầu chạy 6 cycle, nhưng harness dừng sớm ở cycle thứ 4 khi recovery không còn được phép. Kết quả thực tế là:

| Chỉ số | Kết quả |
|---|---:|
| Cycle hồi phục thành công trước circuit | 3 |
| Cycle bị giữ down do circuit | 1 |
| `RESTART` mới trong test | 3 |
| `CIRCUIT_OPEN` mới | 3 |
| Trạng thái trước recovery thủ công | Port 11434 đóng |
| Recovery sau operator kill switch + start task | Cả 4 port trở lại trong 10 giây |

Không nên đọc “3 `CIRCUIT_OPEN`” thành “budget chỉ là 3”. Hai restart trước đó từ các single-cycle test vẫn nằm trong cùng restart window 900 giây. Vì vậy circuit mở sau khi restart history tích lũy đến ngưỡng supervisor cho phép. Đây là kết quả đúng của bounded restart: hệ thống không tiếp tục restart vô hạn khi LLM Bridge liên tục chết.

Sau khi recovery, theo dõi thêm 45 giây ghi `HEALTHY` cho cả bốn service và **không có `CIRCUIT_OPEN` mới** trong cửa sổ hậu phục hồi. Task ở `Running`, kill switch `False`, bốn port đều listen và bốn HTTP endpoint đều 200.

## 6. Phát hiện quan trọng về runtime DB

Post-check không được phép nói rằng toàn bộ production data “không bị sửa”. SHA-256 của `.env` và `data\kb_evolve.sqlite` vẫn khớp baseline. Tuy nhiên, SHA-256 của `data\v13.db` **không khớp baseline** sau khoảng thời gian kiểm thử. Read-only SQLite audit cho thấy:

| Kiểm tra | Kết quả |
|---|---|
| `PRAGMA integrity_check` | `ok` |
| `question_events` | Tăng so với baseline lịch sử đã ghi nhận |
| `question_log` | Tăng so với baseline lịch sử đã ghi nhận |
| `experiences` | Vẫn 44 |
| `knowledge` | Vẫn 1 |
| `knowledge_versions` | Vẫn 814 |
| `active_policies.json` | Không tồn tại |
| `policy_handoff_ledger.jsonl` | Không tồn tại |

Sau khi recovery hoàn tất, phép đo read-only T0/T30 trong 30 giây cho thấy các bảng telemetry chính không tăng thêm và integrity vẫn `ok`. Tuy vậy, evidence hiện có **không đủ để quy kết toàn bộ DB drift chỉ cho outage test**; drift có thể bao gồm runtime audit/loop activity trong cùng khoảng thời gian. Kết luận an toàn là: outage test không tạo bằng chứng policy promotion, nhưng nó đã chạy trong một hệ thống có runtime DB writable và DB hash đã thay đổi.

Đây là missing piece thật sự cần sửa trong quy trình: trước mọi fault injection trên PC thật phải tạo SQLite snapshot nhất quán trước test, sau đó so sánh theo bảng và provenance; chỉ hash file là chưa đủ.

## 7. Trạng thái sau khi khôi phục

| Hạng mục | Trạng thái thực tế |
|---|---|
| Supervisor task | `Running` |
| LLM Bridge | Port 11434, HTTP 200 |
| Loop Scheduler | Port 3030, HTTP 200 |
| SCP Python | Port 8000, HTTP 200 |
| Dashboard | Port 3000, HTTP 200 |
| Kill switch | Không tồn tại |
| `SCP_ENABLE_CLOSED_LOOP` | OFF |
| Năm dangerous flags | OFF |
| `.env` hash | Khớp baseline |
| `kb_evolve.sqlite` hash | Khớp baseline |
| SQLite integrity | `ok` |
| Policy promotion | Không có evidence xảy ra |

## 8. Những gì đã được chứng minh và chưa được chứng minh

Đã chứng minh được rằng supervisor có thể phát hiện LLM Bridge chết, restart trong bounded window, mở circuit khi restart budget tích lũy, ghi ledger, dừng bằng kill switch và khôi phục lại 4 service. Đã chứng minh closed loop vẫn OFF và không có active policy artifact mới trong test.

Chưa chứng minh cold boot trước logon, sleep/hibernate, provider outage dài hơn restart window, disk-full khi ghi ledger, quyền user bị thay đổi, network stack bị reset, hoặc hành vi trên PC thứ hai. Chưa chứng minh SCP có thể bắt “tất cả” tấn công AI/con người. Chưa có pre-test SQLite snapshot cho lần fault injection vừa rồi, nên không được tuyên bố rollback dữ liệu hoàn chỉnh về trạng thái trước test.

## 9. Commit và audit artifacts

Supervisor wiring fix đã có ở [`e8ef171`](https://github.com/checken1994/GA-LAB/commit/e8ef171932c11595478d4def7d0584d7e74347cf). Bounded outage harness và các lần sửa do reality test phát hiện nằm trong các commit [`6728199`](https://github.com/checken1994/GA-LAB/commit/6728199), [`0deb91e`](https://github.com/checken1994/GA-LAB/commit/0deb91e), [`c0da04c`](https://github.com/checken1994/GA-LAB/commit/c0da04c2b533a60fdcb1a02cabc0f1e3f63f5381). Read-only DB audit và consistent snapshot utilities nằm ở [`65628ae`](https://github.com/checken1994/GA-LAB/commit/65628ae7fafff4a5d835dc9e1f36f4d7bdebda1a) và [`c0b7ea5`](https://github.com/checken1994/GA-LAB/commit/c0b7ea53670155444144280071b987c5e3517206).

Các evidence runtime vẫn nằm trong `.private-secrets\release-audit\scp-247\experiments` trên PC; không đưa `.env`, DB runtime hoặc provider secret lên GitHub.

## Kết luận SCP DNA

> **PASS ở đây có nghĩa là không tìm thấy lỗi trong phạm vi thử nghiệm và evidence hiện tại; không có nghĩa là mọi failure mode đã được chứng minh là an toàn.**

Trạng thái đúng sau lần chạy này là **24/7 canary đã được harden và reality-tested thêm**, không phải “đã hoàn thiện tuyệt đối”. Missing piece ưu tiên cao nhất không còn là provider wiring; đó là **isolation và snapshot contract cho runtime DB trước fault injection**, tiếp theo là cold-boot/logon và sleep/hibernate test có rollback rõ ràng.
