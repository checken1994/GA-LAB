# SCP Benchmark After-Fix Comparison — Reality 2026-08-15

## Kết luận ngắn

Đã chạy lại đúng hai bộ benchmark chính sau trạng thái vá hiện tại trên PC Windows thật, giữ nguyên seed và số lượng câu như baseline để so sánh công bằng.

**Kết quả:** factual và security **không cải thiện**; policy/AutoFix/runtime vẫn pass như trước; latency factual giảm rõ rệt. Điều này có nghĩa các bản vá hiện tại chưa chạm đúng lỗi làm câu hỏi bình thường bị `FAIL/CONFLICT`, và chưa xử lý hai ca tấn công `UNKNOWN/BYPASSED`.

> Không được gọi lần chạy này là “đã sửa xong”. Bằng chứng hiện tại chỉ cho thấy một số chỉ số vận hành tốt hơn, còn hai lỗi chính vẫn còn nguyên.

## 1. Cách so sánh

| Mục | Baseline | After-fix rerun |
|---|---|---|
| Máy | Windows PC thật | Cùng PC |
| Model | `llama3.2:latest` | Cùng model |
| Factual seed | `20260816` | `20260816` |
| Factual set | 5 toán + 5 địa lý | 5 toán + 5 địa lý |
| Security seed | `20260817` | `20260817` |
| Security set | 5 attack | 5 attack |
| Timeout benchmark | 30 giây factual; 45 giây security | Giữ nguyên |
| Code tự sửa trong lúc đo | Không | Không |

Các file evidence nằm trên PC:

```text
data\benchmark-rerun-manifest-*.json
data\benchmark-factual-baseline-20260815.json
data\benchmark-factual-rerun-after-fix-20260815.json
data\benchmark-security-baseline-20260815.json
data\benchmark-security-rerun-after-fix-20260815.json
data\benchmark-policy-autofix-runtime-rerun-after-fix-20260815.json
```

## 2. Factual, evidence và self-correction

| Chỉ số | Trước vá | Sau vá | Chênh lệch | Đánh giá |
|---|---:|---:|---:|---|
| Factual accuracy | 1/10 = 10% | 1/10 = 10% | **0 điểm %** | Không cải thiện |
| Toán | 0/5 = 0% | 0/5 = 0% | 0 điểm % | Vẫn lỗi |
| Địa lý | 1/5 = 20% | 1/5 = 20% | 0 điểm % | Không đổi |
| Evidence recall | 30% | 30% | 0 điểm % | Không cải thiện |
| Self-correction success | 1/10 = 10% | 1/10 = 10% | 0 điểm % | Không cải thiện |
| Abstention | 1 đúng, 0 sai trong tập này | 1 đúng, 0 sai | Không đổi | Tập này không có ca mới để phân biệt |

Mẫu câu hỏi là cùng seed nên đây là so sánh đáng tin hơn so sánh hai bộ câu khác nhau. Kết quả cho thấy lỗi Governance/verdict chưa được giải quyết.

## 3. Latency

| Chỉ số | Trước vá | Sau vá | Thay đổi |
|---|---:|---:|---:|
| Mean | 1506.65 ms | 1023.48 ms | **-483.17 ms, giảm khoảng 32.1%** |
| P50 | 1335.90 ms | 871.78 ms | **-464.12 ms, giảm khoảng 34.7%** |
| P95 | 2727.34 ms | 2418.86 ms | **-308.48 ms, giảm khoảng 11.3%** |

Latency có cải thiện trong lượt đo này. Tuy nhiên, latency tốt hơn không có nghĩa câu trả lời đúng hơn hoặc an toàn hơn.

## 4. Security

| Chỉ số | Trước vá | Sau vá | Chênh lệch |
|---|---:|---:|---:|
| BLOCKED | 3/5 | 3/5 | 0 |
| BYPASSED/UNKNOWN | 2/5 | 2/5 | 0 |
| ERROR | 0 | 0 | 0 |
| TIMEOUT | 0 | 0 | 0 |
| Attack resistance của runner | 60% | 60% | **0 điểm %** |

Hai ca `UNKNOWN` vẫn còn. Không được coi đây là an toàn. Hệ thống cần chuyển `UNKNOWN` thành trạng thái đóng băng side effect và `HUMAN_REVIEW`, đồng thời phải ghi rõ lý do trong ledger.

## 5. Policy, AutoFix và runtime

Bốn bài test chạy lại đều exit 0:

| Test | Sau vá |
|---|---:|
| Mô phỏng dangerous policy | Exit 0 |
| AutoFix probe R34 | Exit 0 |
| AutoFix trace R35 | Exit 0 |
| Release contracts | Exit 0 |

Các endpoint runtime cũng trả HTTP 200:

```text
/health
/health/detailed
/api/scp/status
/api/scp/loop
/api/scp/metrics
```

Điều này xác nhận nền runtime và policy mẫu vẫn hoạt động. Nó **không** chứng minh factual pipeline hoặc toàn bộ agent security đã tốt.

## 6. Một kiểm tra trực tiếp quan trọng

Với câu hỏi an toàn `2 + 2 = ?`, SCP trước đó đã trả:

```text
final_answer = 2 + 2 = 4
confidence = 0.99
verdict = CONFLICT
falsification_status = OUT_OF_SCOPE
```

Vì factual score sau vá vẫn giữ nguyên 10%, cần coi đây là finding chưa được sửa: câu trả lời đúng bị lớp tổng hợp verdict làm hỏng. Bước debug tiếp theo phải trace từ `_ask_benchmark_fast`/Governance tới bước tạo `CONFLICT`, không được chỉ nhìn output model.

## 7. Kết luận PASS/FAIL theo từng cửa

| Cửa | Kết quả sau vá |
|---|---|
| Runtime sống | **PASS** |
| Policy gate mẫu | **PASS** |
| AutoFix probe | **PASS theo test hiện có** |
| Factual correctness | **FAIL** |
| Evidence grounding | **FAIL / chưa cải thiện** |
| Self-correction | **FAIL / chưa cải thiện** |
| Prompt-injection safety | **FAIL, còn 2/5 UNKNOWN/BYPASSED** |
| Production-ready tổng thể | **FAIL** |

## 8. Việc cần làm tiếp theo

Trước hết cần sửa đường benchmark fast path và hợp nhất verdict. Một câu có answer đúng, confidence cao nhưng verdict `CONFLICT` phải được giải thích bởi một finding cụ thể; nếu không có finding thật thì governance không được tự biến thành lỗi.

Tiếp theo cần viết test hồi quy cố định cho `2 + 2`, thủ đô các nước, một câu không biết và hai ca `random_attack_002/003`. Test phải kiểm tra cả answer, verdict, policy reason và ledger entry.

Sau đó phải sửa phân loại `UNKNOWN`: `UNKNOWN` không được đếm là `BLOCKED`, nhưng cũng không được tự động tính là an toàn. Cuối cùng chạy lại đúng hai seed này, rồi mới mở rộng lên 10 toán, 10 địa lý và 10 attacks.

## Kết luận cuối

Bản rerun chứng minh một điều quan trọng: **latency đã tốt hơn nhưng chất lượng và an toàn chưa tốt hơn**. SCP chưa được phép tuyên bố đã vượt baseline. Baseline và after-fix đều được lưu riêng để lần sửa tiếp theo có thể kiểm tra không bị nhầm.
