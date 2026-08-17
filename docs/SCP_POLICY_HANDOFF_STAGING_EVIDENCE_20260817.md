# Policy Handoff Staging Evidence — 17/08/2026

## Mục tiêu

Kiểm tra vì sao SCP chưa có `data/active_policies.json` production và liệu có candidate thật để promotion hay không. Kiểm tra này dùng **staging private**, không được phép ghi policy production.

## Cách kiểm tra an toàn

1. Tạo clone `v13.db` bằng SQLite backup API read-only vào `.private-secrets/release-audit/policy-handoff-staging-20260817/v13.db`. Snapshot báo **91** record trong bảng `experiences`.
2. Chạy `policy_handoff_r43.py materialize` với cả `--db` và `--data-dir` đều trỏ staging private.
3. Đọc metadata candidate, không gọi `promote` hay `apply`.
4. Kiểm tra `data/active_policies.json` production vẫn không tồn tại.

## Kết quả quan sát

| Điều kiện | Kết quả |
|---|---|
| Snapshot DB staging tạo được | PASS |
| `lesson_count_seen` | 91 |
| `eligible_lesson_count` | **0** |
| `skipped_lessons` | **91** |
| Candidate JSON/hash tạo được | Có; chỉ là candidate rỗng, không đủ điều kiện promote |
| Staging `active_policies.json` | Không tồn tại |
| Production `data/active_policies.json` | Không tồn tại |
| Promotion/apply | Không chạy |

Các record chưa áp dụng có các taxonomy kiểu `VERDICT_UNKNOWN`, `VERDICT_PARTIAL` và các verdict history tương tự. Đây không thuộc `SUPPORTED_LESSON_TYPES` của materializer như `SOURCE_RELIABILITY`, `DOMAIN_BIAS`, `ERROR_FREQUENCY`, `CONFIDENCE_TUNING` hoặc `ROUTE_OPTIMIZATION`.

## Ý nghĩa thực tế

Đây không phải lỗi “file policy bị mất”. Materializer đang **từ chối đúng**: history verdict không đủ nghĩa để biến thẳng thành policy runtime. Nếu tự cho các verdict này qua, SCP có thể học sai từ trạng thái quan sát, rồi thay đổi hành vi production mà không có lesson/action/target/value rõ ràng.

> Verdict: **EVO-004 vẫn BLOCKED đúng chủ đích.** Bằng chứng hiện tại nói rằng nguồn lesson có schema phù hợp chưa tồn tại, không phải rằng promotion code đã hỏng.

## Điều cần làm trước production handoff

1. Xây adapter tạo lesson có schema rõ ràng từ external truth hoặc verifier độc lập, với `lesson_type`, `policy_action`, `policy_target`, `policy_value` và provenance.
2. Chứng minh ít nhất một lesson staging có validation, candidate hash, atomic promote, application count và rollback hash.
3. Chỉ cân nhắc promotion production sau khi owner hiểu thay đổi policy cụ thể; không tự biến verdict history thành policy.
