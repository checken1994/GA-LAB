# SCP DNA — R44 Regression Learning và Behavior Measurement

**Ngày kiểm chứng:** 14/08/2026 (GMT+7)  
**Máy thực tế:** `C:\Users\check\Downloads\scp`  
**GitHub HEAD sau các thay đổi:** [`f058715`](https://github.com/checken1994/GA-LAB/commit/f05871556eeb3c0e256c380393ac9126f91700fc)  
**Phạm vi:** chuyển telemetry lịch sử thành corpus regression, kiểm tra candidate `BareExceptPass`, sửa một lỗi portability của reality-test trên Windows, và xác nhận không có promotion vào policy.

## Kết luận ngắn

R44 đã làm cho SCP **đọc và replay được một phần lịch sử của chính nó theo provenance**, nhưng chưa biến lịch sử đó thành “truth” hay tự động sửa policy. Đây là kết quả đúng theo SCP DNA: quá khứ được tách thành telemetry, operational lesson, design lineage và future-evaluation thay vì trộn tất cả thành knowledge.

Có ba kết quả thực tế. Thứ nhất, PC đã tạo được corpus immutable gồm **10.000 `question_events`** trong `.private-secrets`, toàn bộ thuộc lineage `threat_simulator`, với **10.000 case ID duy nhất**, `ground_truth=0`, replay policy an toàn và corpus hash khớp manifest. Thứ hai, A/B scan trên **606 file Python hiện tại của PC** cho kết quả `baseline_findings=0` và `candidate_findings=0`; candidate không tạo behavior flip trên source hiện tại. Thứ ba, cùng một harness trên source lịch sử thật của V88/V3 cho detector parity: V88 có `7→7` findings và V3 có `1→1`; các patched source đều compile được. Đây là bằng chứng hoạt động cú pháp trong phạm vi hẹp, **không phải bằng chứng semantic correctness**.

## 1. Tại sao cần corpus regression?

Trước R44, SCP có 15.733 `question_events` và 13.815 `question_log`, nhưng các row này nằm trong DB runtime và không có contract rõ ràng để phân biệt telemetry với external truth. Nếu đưa chúng thẳng vào KB hoặc policy, SCP sẽ học lại simulator của chính nó. Đặc biệt, 15.587 event có source `threat_simulator` và phần lớn là `REPEAT`; đó là bằng chứng recurrence và coverage, không phải 15.587 quan sát độc lập của thế giới.

R44 tạo một boundary riêng. Mỗi corpus row có `case_id` ổn định, source artifact và SHA-256, lineage, event ID, input đã redaction, `observed_output`, `ground_truth`, provenance và replay policy. Một historical `PASS` hoặc `FAIL` không được tự động chuyển thành ground truth. `reality-tests-results.json` hiện có 73 row với `pass=null`, vì vậy vẫn bị quarantine.

| Contract | Trạng thái |
|---|---|
| Source lineage tách khỏi verdict | Đạt trong builder |
| Source artifact hash | Đạt |
| Stable case ID | Đạt; 10.000 unique IDs trên PC |
| Ground truth độc lập | Không có; giữ `null` |
| Secret/path redaction | Không phát hiện secret marker trong verifier run |
| Replay read-only | Đạt |
| Policy promotion | `False` |
| Corpus immutability/idempotence | Hai lần history scan trước đó cho cùng candidate/quarantine; corpus có hash manifest |

## 2. Kết quả tạo corpus trên PC thật

Builder R44 đã đọc `data\v13.db` ở chế độ SQLite read-only, lấy tối đa 10.000 row từ `question_events` và ghi corpus cùng manifest vào `.private-secrets\release-audit`. DB không bị sửa.

| Chỉ số | Kết quả |
|---|---:|
| Cases built | 10.000 |
| Lineage `threat_simulator` | 10.000 |
| Lineage benchmark | 0 |
| Lineage real-PC probe | 0 |
| Lineage reality-test | 0 |
| Unique case IDs | 10.000 |
| `ground_truth` khác `null` | 0 |
| Unsafe replay policy | 0 |
| Secret marker hits | 0 |
| Hash khớp manifest | `True` |
| Policy promotion | `False` |

Đây là **regression corpus**, không phải training set để SCP tự tin hơn một cách mù quáng. Bước kế tiếp phải tách thêm benchmark và real-PC probe thành các artifact riêng, sau đó đo replay stability theo từng lineage; không cộng gộp chúng thành một accuracy duy nhất.

## 3. Kết quả A/B candidate `BareExceptPass`

Harness A/B dùng hai nguồn đo khác nhau. Baseline là một AST detector độc lập đếm `except:` có body duy nhất là `pass`. Treatment là candidate generator hiện có trong `scp.autofix.speculative_prefixer`, chạy trong cache private bounded. Mỗi candidate patch được parse lại bằng AST; không có active-policy write.

### Source hiện tại trên PC

Harness quét **606 file Python**, bỏ qua `venv`, `node_modules`, cache, Git metadata và private staging. Kết quả là:

| Metric | Kết quả |
|---|---:|
| Files scanned | 606 |
| Parse failures | 0 |
| Independent baseline findings | 0 |
| Candidate findings | 0 |
| Behavior flips | 0 |
| Candidate compile failures | 0 |
| Ground truth available | `False` |
| Policy promotion | `False` |

Không có finding trên source hiện tại nghĩa là candidate không có behavior change để đo ở baseline hiện tại. Đây không phải là bằng chứng candidate đúng cho mọi source; chỉ nói rằng sau remediation hiện thời, source PC không còn `BareExceptPass` mà detector này nhận diện.

### Historical V88/V3 source

Để tránh kết luận “zero trên PC” thành “rule không bao giờ chạy”, cùng harness được chạy trên source lịch sử thật đã clone từ V88 và V3, không dùng mẫu tự tạo.

| Lineage | File scan | Baseline | Candidate | File có candidate | Candidate patch compile | Compile fail |
|---|---:|---:|---:|---:|---:|---:|
| `scp-v88/scripts/legacy` | 6 | 7 | 7 | 3 | 3 | 0 |
| `V3-/SCP` | 7 | 1 | 1 | 1 | 1 | 0 |

Kết quả `7→7` và `1→1` cho thấy detector độc lập và candidate generator có **detector parity** trong bounded corpus này. Tuy nhiên, cả hai A/B report đều ghi `independent_true_positive_evidence=0`, `independent_false_positive_evidence=0`, `ground_truth_available=false`. Chưa có source snapshot/adjudication chứng minh rằng thay `except:` bằng `except Exception:` là semantic-safe cho từng ngữ cảnh.

## 4. Independent reality gates trên PC

Hai reality test rollback liên quan đã được chạy trên PC thật.

| Test | Kết quả trước patch | Thay đổi | Kết quả cuối |
|---|---|---|---|
| `reality_4-b-012.py` | Runtime logic đã pass khi chạy trực tiếp | Loại Unicode check mark ở dòng kết thúc để redirect Windows không lỗi | Exit 0 khi redirect |
| `reality_4-b-013.py` | Lần đầu lỗi `UnicodeDecodeError` do default Windows code page đọc source | Thêm `encoding='utf-8'` cho file I/O và đổi output cuối sang ASCII | Exit 0 khi redirect |

Trong lần kiểm tra cuối, cả hai test đều chạy với stdout redirect mặc định và trả exit 0. `compileall` cho `scp\history` và `scripts\history` trả exit 0. Đây là fix cho **test portability**, không phải thay đổi policy hoặc behavior backend.

Một điểm cần giữ rõ: ruff toàn bộ file `reality_4-b-012.py` vẫn phát hiện một số vấn đề lint legacy ngoài phạm vi thay đổi ASCII, như import tại runtime, broad exception và `NamedTemporaryFile` không dùng context manager. Runtime gate đã pass, nhưng lint của toàn bộ legacy test chưa được tuyên bố sạch.

## 5. Những gì đã được cài lên PC và rollback

Các file mới R44 được áp dụng hẹp, từng batch có backup manifest:

| Batch | File/path | Tác động |
|---|---|---|
| History migration | `scp/history/__init__.py`, `scp/history/migration.py`, `scripts/history/r44_history_migration.py` | Read-only historical scan; không policy/DB mutation |
| Regression corpus | `scp/history/regression_corpus.py`, `scripts/history/r44_build_regression_corpus.py` | Tạo corpus private từ DB read-only |
| A/B harness | `scripts/history/r44_bare_except_ab.py` | Scan private/current source và historical staging; cache private |
| Test portability | `tests/reality-tests/reality_4-b-012.py`, `reality_4-b-013.py` | Chỉ sửa encoding/output của test harness |

Post-checkpoint hashes trên PC vẫn cho thấy `data\v13.db` giữ SHA-256 `A0F5BD0F06C91D56A0A1DC7BBF466EA30C0E657CC1002B20B135BAD0EDEC96C1`; `data\kb_evolve.sqlite` giữ SHA-256 `53A2DEB3A4CEA8C2C6C28230F7A8D69664ACFA9B51B4B7212ACA40F9501DD70E` theo snapshot đã ghi nhận trước đó; production `.env` không được sửa. Các source R44 đã áp dụng được đối chiếu SHA-256 với commit tương ứng, tất cả hash match.

Rollback path là các manifest dưới `.private-secrets\release-audit\r44-*-apply-*`. Vì các batch không force checkout và không ghi DB/runtime policy, rollback chỉ cần khôi phục đúng file từ manifest; không có thao tác reset toàn repository.

## 6. Kết luận theo SCP DNA

R44 đạt **PASS trong phạm vi detector, compile, corpus contract và rollback-test scope**. PASS này không có nghĩa là SCP đã chứng minh rule BareExceptPass đúng về semantic, cũng không có nghĩa SCP đã học được external truth. Missing piece chính là semantic evidence từ exact pre-fix snapshot, test behavior và independent adjudication. Sáu lesson trong `kb_evolve.sqlite` vẫn là sáu records cùng một bug class; chúng không được xem là sáu general lessons và bốn evolved patterns confidence 0.5 vẫn không được promote.

Trạng thái hiện tại của SCP là:

| Tầng | Trạng thái |
|---|---|
| Đọc quá khứ và giữ provenance | Đã có R44 HistoryMigration và regression corpus |
| Replay telemetry | Đã tạo được corpus 10.000 case, nhưng mới bounded một lineage |
| Operational lesson | Có candidate hẹp `BareExceptPass`; chưa semantic-promote |
| Calibration/prediction learning | Chưa đủ vì DB hiện tại không có durable calibration/predictions |
| External truth learning | Chưa được chứng minh |
| Active policy behavior change | Chưa có; `policy_promotion=False` |
| Production-ready toàn hệ thống | Chưa thể tuyên bố |

## 7. Bước tiếp theo có thứ tự

Trước hết, phải tạo thêm corpus từ `benchmark` và `real_pc_probe`, mỗi lineage có hash và metric riêng. Sau đó cần khôi phục exact pre-fix source snapshots cho sáu lesson `BareExceptPass`; nếu không khôi phục được, chỉ giữ chúng là candidate operational evidence. Khi có snapshot, chạy semantic tests cho từng patch và ghi rõ true/false positive evidence.

Tiếp theo, dùng corpus để xây A/B harness cho các policy consumers còn thiếu: `source_priorities`, `kb_priorities`, `recurring_errors` và `confidence_adjustments`. Mỗi consumer phải có before/after behavior delta, no-regression set, rollback token và promotion ledger. Không được lấy số lượng row làm bằng chứng improvement nếu không có independent outcome.

Cuối cùng, làm durable producers cho `error_history`, `memory`, `calibration_history` và `predictions`; chỉ sau đó ExperienceEngine mới có nguyên liệu thật để học recurring errors, domain bias và confidence tuning. 210 forecast vẫn giữ ở evaluation/quarantine lane riêng; nó không thay thế operational learning và không được đưa vào policy khi còn unresolved.

## References

[1]: https://github.com/checken1994/GA-LAB/commit/7b1635df9b9eca8dbdcbe5329cd76b02855816f1 "R44 provenance-safe regression corpus"
[2]: https://github.com/checken1994/GA-LAB/commit/32de40e58a4cee5fd49d5a47130f4ef396e0fef3 "R44 BareExceptPass A/B harness"
[3]: https://github.com/checken1994/GA-LAB/commit/c16fecd1f94934f5ad5ac10f4a791c4615c5f147 "UTF-8 portability fix for rollback reality test"
[4]: https://github.com/checken1994/GA-LAB/commit/f05871556eeb3c0e256c380393ac9126f91700fc "Windows-safe ASCII output for rollback reality tests"
[5]: https://github.com/checken1994/GA-LAB/blob/main/docs/SCP_HISTORY_LEARNING_AUDIT_R44_FINAL.md "Whole-history learning audit R44"
[6]: https://github.com/checken1994/GA-LAB/blob/main/docs/SCP_REGRESSION_CORPUS_R44.md "Regression corpus contract R44"
