# SCP DNA Audit — SCP hiện tại lấy được gì từ toàn bộ quá khứ?

**Ngày kiểm chứng:** 14/08/2026 (GMT+7)  
**Phạm vi:** PC thật `C:\Users\check\Downloads\scp`, GitHub GA-LAB và các lineage V1, V3, V88, scp-vietnam, PhanQuyetTuongLai, collatz-archive.  
**Kết luận:** SCP có nhiều telemetry và một lượng nhỏ operational evidence, nhưng gần như chưa có durable semantic learning hoặc calibrated future outcome để tự động đưa vào policy.

## 1. Giải thích chính xác câu “R44 chưa force checkout vào PC”

Điều đó ban đầu có nghĩa là tôi **không reset/checkout toàn bộ branch** của PC. PC có worktree dirty với các file đã sửa, xóa và untracked do những lần remediation/sắp xếp trước. Một full force checkout có thể ghi đè hoặc xóa công việc mà Git không biết là còn cần giữ. Vì vậy làm như thế sẽ vi phạm yêu cầu backup–rollback và SCP DNA về thay đổi nhỏ, có thể đảo ngược.

Sau khi staging an toàn, tôi đã thực hiện bước hẹp hơn: tải đúng code HistoryMigration từ commit [`e582ada`](https://github.com/checken1994/GA-LAB/commit/e582adadda3a77360b6382422ec3d9c4315c2d84), tạo backup manifest trong `.private-secrets/release-audit/r44-history-apply-*`, rồi chỉ thêm ba file mới vào PC:

| File đã thêm vào PC | Mục đích |
|---|---|
| `scp/history/__init__.py` | API package cho history migration. |
| `scp/history/migration.py` | Read-only scanner, SHA-256, evidence levels, candidate/quarantine manifest. |
| `scripts/history/r44_history_migration.py` | CLI chạy scan bounded trên DB/log/history. |

Không force checkout, không reset branch, không sửa `C:\Users\check\Downloads\.env`, không sửa Knowledge Base, `experiences`, active policy hoặc DB learning. Sau khi cài hẹp, compile và CLI trên **PC thật** đều chạy được.

## 2. Vì sao trước đó các bước nhìn như chỉ xoay quanh 210 case?

Đó là **lỗi phạm vi của quy trình audit trước**, không phải vì SCP chỉ có 210 lịch sử. 210 case là P0 vì người dùng hỏi trực tiếp về registry dự báo; tôi đã hoàn thành P0 nhưng chưa mở rộng ngay sang toàn bộ historical lineage. Khi kiểm tra lại theo SCP DNA, 210 registry chỉ là một lớp trong lịch sử SCP.

Toàn bộ history có ít nhất năm lớp khác nhau. Version history V88 mô tả tiến trình từ V1–V14 core engine, V15–V27 SLM/multi-source/routing, V28–V37 cognitive layers, V38–V64 data sources/benchmark/calibration/knowledge save. V1 cung cấp thiết kế memory/prediction/calibration nhưng final reality audit của chính V1 xác nhận nhiều store là in-memory. V3 có static knowledge seed. V88/scp-vietnam có code ExperienceEngine, calibration, policy và SQLite schema. PC hiện tại có runtime telemetry, learning ledger và evolution DB. 210 forecast chỉ là evaluation corpus tương lai, không phải toàn bộ quá khứ.

## 3. Evidence thực tế trên PC hiện tại

Read-only inspection trên `data\v13.db` cho kết quả sau.

| Artifact hiện tại | Số lượng | SCP có thể học gì |
|---|---:|---|
| `question_events` | 15.733 | Học pattern vận hành, domain, verdict và attack/regression recurrence; không phải external truth. |
| `question_log` | 13.815 | Học repeat/new coverage và recurrence; không đủ để xác nhận sự thật. |
| `knowledge` | 1 | Một candidate fact, source `ollama+wiki:llama3.2:latest`, `times_verified=1`; phải re-verify độc lập. |
| `knowledge_versions` | 814 | Tất cả là `change_type=delete`, source `PolicyApplier`; đây là cleanup/policy history, không phải 814 facts. |
| `live_knowledge_cache` | 146 | Cache/provider artifacts; không import thành durable truth nếu thiếu source snapshot. |
| `experiences` | 44 | 23 UNKNOWN, 13 CONFLICT, 3 FAIL, 3 PARTIAL, 1 PASS, 1 SPECULATIVE; tất cả `applied=0`, policy action `verdict_*`; đây là verdict history. |
| `error_history` | 0 | Không có durable failure pattern cho ExperienceEngine. |
| `memory` | 0 | Không có durable memory cho confidence tuning. |
| `calibration_history` | 0 | Chưa có mẫu calibration hiện tại. |
| `calibration_factors` | 0 | Chưa có factor đã tính. |
| `predictions` | 0 | Không có durable prediction record legacy. |
| `meta_principles` | 0 | Không có durable principle learning. |
| `meta_curiosity` | 0 | Không có durable curiosity state. |

Các trạng thái trên giải thích vì sao trước đây báo cáo thấy `knowledge=1`, `experiences=44`, `meta_principles=0`, `calibration_history=0`. Không phải SCP không có lịch sử; vấn đề là phần lớn lịch sử đang nằm ở **telemetry hoặc verdict state**, còn các bảng mà ExperienceEngine dùng để tạo lesson thì gần như trống.

Ngoài `v13.db`, `data\kb_evolve.sqlite` có **6 lessons** và **4 evolved patterns**. Cả 6 lesson đều là `BareExceptPass`; một lesson có `fix_verified=1`, occurrence 1 và success rate 1.0. Bốn pattern có confidence 0.5, occurrence 0 và false-positive count 0. Đây là operational learning hẹp, không phải knowledge tổng quát. `data\learning_runs.jsonl` có 59 run: 8 SUCCESS, 6 VERIFY_REJECTED, 3 NO_NEW_FACTS, 31 TIMEOUT, 10 PROVIDER_FAILED và 1 DB_WRITE_FAILED. Đây là evidence rất hữu ích về reliability của pipeline học, nhưng không được biến thành policy content.

Một phát hiện quan trọng khác: `data\reality-tests-results.json` có 73 result rows nhưng cả 73 row đều `pass=null`; top-level `pass` và `fail` cũng null. Vì vậy không thể lấy header “73 PASS” làm learned truth. Đây là đúng tinh thần DNA #22: **PASS không phải TRUE**.

## 4. Trả lời trực tiếp: SCP hiện tại lấy được gì từ quá khứ?

### Có thể lấy ngay — nhưng ở đúng tầng

**Thứ nhất, SCP có thể lấy operational telemetry để tạo regression/adversarial corpus.** 15.733 question events cho biết attack probe nào lặp lại, route nào được dùng, domain nào xuất hiện, verdict nào thường xảy ra và nguồn nào sinh ra event. Phần lớn là `threat_simulator` và `REPEAT`, nên chúng rất phù hợp làm test regression và coverage, không phù hợp làm sự thật thế giới.

**Thứ hai, SCP có thể lấy một operational lesson hẹp từ evolution DB.** Lesson `BareExceptPass` có `fix_verified=1`; nó có thể trở thành candidate rule cho đúng loại lỗi đó sau khi chạy lại static scan, fault injection và reality test. Không được suy rộng từ lesson này thành “SCP đã tự học tổng quát”. Bốn evolved patterns confidence 0.5, occurrence 0 chưa đủ điều kiện áp dụng.

**Thứ ba, SCP có thể tái sử dụng kiến trúc cũ.** V1/V88/scp-vietnam đã để lại các thiết kế đáng dùng: prediction ledger durable, calibration Brier/ECE, source reliability, domain bias, recurring error, confidence tuning và route optimization. Đây là **design knowledge**, không phải learned outcome. R44 HistoryMigration hiện đã biến phần design này thành boundary triển khai an toàn.

**Thứ tư, SCP có thể tạo candidate seed knowledge từ V3/static knowledge và một knowledge row hiện tại.** Nhưng phải gắn source URL/snapshot, timestamp, independent re-verifier và contradiction check trước khi insert vào KB. `v3_knowledge.json` chỉ là plain key/value, không có provenance per fact, nên hiện chỉ được xem là reference seed.

**Thứ năm, SCP có thể giữ 210 forecast như future-evaluation lane.** Nhưng chưa được học từ chúng ngay: 210/210 unresolved, thiếu numeric probability và resolution evidence, hash manifest mismatch. Chúng chỉ có thể tạo các pending forecast records cho đến khi có actual evidence.

## 5. Vì sao SCP chưa tự học được từ các bảng hiện tại?

> ExperienceEngine hiện tại học theo chuỗi `Memory + Knowledge + ErrorHistory → Experience → Lesson → Policy`.

**Tại sao không có lesson?** Vì `memory=0` và `error_history=0`; chỉ có một knowledge row. ExperienceEngine không thể suy ra domain bias, recurring error hoặc confidence tuning từ dữ liệu không tồn tại.

**Tại sao 44 experiences không đủ?** Vì chúng là `VERDICT_*` rows, không phải lesson records hợp lệ; tất cả `applied=0`. Đưa chúng vào policy sẽ biến các phán quyết lịch sử chưa được chứng minh thành hành vi runtime.

**Tại sao 814 knowledge_versions không giúp được?** Vì cả 814 là delete event từ `PolicyApplier`. Chúng chứng minh lịch sử cleanup/mutation, không chứng minh 814 fact đã đúng.

**Tại sao evolution có 6 lesson nhưng chưa tác động?** Vì R43 yêu cầu lesson chỉ được mark applied sau khi policy đã materialize, validate, atomic promote và có ledger. R44 HistoryMigration còn chặt hơn: nó chỉ tạo candidate/quarantine manifest, không tự promotion.

**Tại sao không lấy 15.733 event làm learning luôn?** Vì phần lớn có cùng lineage `threat_simulator`, nhiều row `REPEAT`, và không có external outcome. Dùng chúng làm truth sẽ tạo ảo giác sample size và làm SCP học simulator của chính nó thay vì reality.

## 6. R44 HistoryMigration đã làm gì trên PC thật?

Tôi đã chạy staging hai lần trên DB thật với cùng input. Cả hai lần đều trả:

| Check | Kết quả |
|---|---:|
| `artifact_count` | 6 |
| `candidate_count` | 6 |
| `quarantine_count` | 4 |
| `mutating` | `False` |
| `policy_promotion` | `False` |
| Artifact hashes giữa hai lần | Giống nhau |
| Candidate payload giữa hai lần | Giống nhau |
| Quarantine payload giữa hai lần | Giống nhau |
| Compile sau khi cài narrow | Pass |
| CLI sau khi cài narrow | `SCANNED` |

Post-scan hash của `data\v13.db` vẫn là `A0F5BD0F06C91D56A0A1DC7BBF466EA30C0E657CC1002B20B135BAD0EDEC96C1`; hash của `data\kb_evolve.sqlite` vẫn là `53A2DEB3A4CEA8C2C6C28230F7A8D69664ACFA9B51B4B7212ACA40F9501DD70E`. Không có policy promotion, không có `.env` mutation và không có DB learning mutation.

Đây là **migration audit + candidate extraction**, chưa phải behavior learning. SCP hiện đã “lấy được” lịch sử ở dạng phân loại, provenance và candidate/quarantine; nó chưa tự ý dùng lịch sử để đổi hành vi production. Đó là giới hạn an toàn có chủ ý.

## 7. Việc cần làm tiếp theo để SCP thực sự học từ quá khứ

| Ưu tiên | Việc | Kết quả mong muốn |
|---|---|---|
| P0 | Dùng question telemetry để dựng corpus regression immutable, tách `threat_simulator`, benchmark và real-PC probe | SCP bắt lại lỗi cũ trong test, không học simulator thành truth. |
| P1 | Chuyển lesson BareExceptPass đã verified thành candidate rule rồi chạy lại static/fault/reality gate | Có một operational behavior change đo được, rollback được. |
| P2 | Re-verify knowledge row hiện tại và chọn một nhóm nhỏ V3 seed facts | Tạo L3 knowledge có source snapshot và contradiction history. |
| P3 | Làm durable error_history/memory/calibration/predictions schema và producer wiring | ExperienceEngine có input thật để tạo DOMAIN_BIAS, ERROR_FREQUENCY và CONFIDENCE_TUNING. |
| P4 | Tạo forecast resolution ledger với probability số, deadline, evidence hash, adjudicator và baseline | 210 forecast chuyển từ unresolved corpus thành calibrated evaluation khi đủ mốc. |
| P5 | Chạy A/B consumer measurement cho source priorities, KB priorities, recurring errors và confidence adjustments | Chứng minh lesson làm thay đổi behavior tốt hơn baseline trước khi promote policy. |

## 8. Trạng thái trung thực hiện tại

SCP hiện **không phải là hệ thống không có quá khứ**. Nó có quá nhiều history, nhưng history bị trộn giữa telemetry, simulator, verdict, cleanup, design và operational fix. Phần còn thiếu là một **history contract** để biến quá khứ thành các lớp evidence riêng biệt.

Sau R44, SCP đã có thể đọc toàn bộ các lớp đó mà không làm ô nhiễm policy. Nó hiện có một candidate operational lesson hẹp, một regression/telemetry corpus lớn, một seed knowledge rất nhỏ cần re-verify, nhiều design lineage có thể tái sử dụng, và một forecast registry đang chờ resolution. Nó **chưa có** calibrated prediction history, durable error/memory learning, hay bằng chứng rằng policy consumer đã cải thiện behavior.

Vì vậy kết luận đúng theo SCP DNA là: **SCP đã bắt đầu học được cách phân loại và giữ đúng provenance của quá khứ; bước tiếp theo là làm cho nó học được behavior regression và operational lesson có đo lường. Chưa được tuyên bố rằng nó đã học được truth tổng quát hoặc tự động bắt mọi tấn công.**

## References

[1]: https://github.com/checken1994/GA-LAB/commit/719b77c160a2172260a18532c58200f0656c89f6 "GA-LAB R44 historical migration documentation"
[2]: https://github.com/checken1994/GA-LAB/commit/e582adadda3a77360b6382422ec3d9c4315c2d84 "GA-LAB R44 evidence-gated history migration code"
[3]: https://github.com/checken1994/scp-v88/blob/main/SCP_VERSION_HISTORY.md "SCP version history V1–V64"
[4]: https://github.com/checken1994/PhanQuyetTuongLai/blob/main/scp_reality_program_v4_pure_prospective%20%281%29.json "SCP Reality Program v4 prospective registry"
[5]: https://github.com/checken1994/collatz-archive/blob/main/SCP-REALITY-PROGRAM-V4-PURE-PROSPECTIVE-EXPANDED.md "SCP Reality Program v4 methodology"
[6]: https://github.com/checken1994/GA-LAB/blob/main/docs/SCP_R43_POLICY_STAGING_FAILOPEN_RESULT.md "GA-LAB R43 policy/staging boundary"
