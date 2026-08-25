# Báo cáo bằng chứng — Candidate Enrichment Phase 3

## Kết luận điều hành

Candidate enrichment trên bản isolated test đã được **chuẩn hóa và kiểm chứng cấu trúc trong phạm vi**: artifact cuối có đúng 1.000 dòng, 1.000 `question_id` duy nhất, không còn duplicate, citation/evidence quote không trỏ ra ngoài context, và mọi dòng vẫn giữ `candidate_only=true`, `human_review_required=true`, `gold_promotion=FORBIDDEN`. Đây là bằng chứng mức artifact/integration cho pipeline dự thảo, **không phải bằng chứng SCP đã trả lời đúng 1.000 câu**.

Kết quả chất lượng hiện tại vẫn **BLOCKED đối với mục tiêu Real RAG 1.000 câu**. Trong 1.000 dòng sanitized có 185 `COMPLETED`, 565 `NO_TEXT_ABSTAIN` và 250 `REQUEST_ERROR`; cả 1.000 provisional answer đều rỗng và `abstain=true`. Log bridge ghi nhận lỗi thật là provider trả `Insufficient credits` với `available_credits=0`, vì vậy 250 dòng không được coi là câu trả lời thất bại do nội dung. Ngoài ra, 44 dòng bị sanitizer buộc ABSTAIN vì citation/evidence quote không hợp lệ. Chưa có dòng nào đủ điều kiện làm verified gold; Ragas/ARES full 1.000 câu vẫn bị chặn.

> **Reality over Model:** “COMPLETED” chỉ nói rằng runner nhận được một structured response hoặc giữ một record candidate; nó không có nghĩa là câu trả lời đúng. Khi thiếu gold answer do người xác nhận và canonical provenance đạt chuẩn, SCP phải tiếp tục ABSTAIN/BLOCKED.

## Phạm vi, snapshot và rollback

| Trường | Giá trị |
|---|---|
| Source input | `phase2_bing_discovery_v2.jsonl` |
| Candidate artifact gốc | `phase3_candidate_enrichment_full.jsonl` — giữ nguyên để rollback |
| Candidate artifact sau dedup/retry | `phase3_candidate_enrichment_full_v2.jsonl` |
| Artifact cuối sau sanitizer | `phase3_candidate_enrichment_full_v2_sanitized.jsonl` |
| SHA-256 artifact sanitized | `f367f61854cd49ee3e878450b276783be67cd6954e1b4bf97948f47c4b216747` |
| Runtime được phép dùng | Isolated test 8002, PID 29364 |
| Runtime bị bảo vệ | Production 8000 PID 25212; test 8001 PID 14184 |
| Commit backend đã quan sát | `4e47add244edadfc1eb53baa4f75ebf239a75e82` |
| Rollback | Xóa/đổi tên v2 artifacts và dùng lại artifact gốc; không sửa production source |

## Chuỗi evidence đã thực hiện

| Bước | Quan sát được | Verdict trong phạm vi |
|---|---|---|
| Dedupe | Input discovery 1.000 dòng/1.000 ID; full cũ 1.001 dòng/995 ID; v2 tạo 1.000 dòng/1.000 ID | `PASS_WITHIN_SCOPE` |
| Retry | 250 `REQUEST_ERROR` được retry qua fixed bridge 8769 với batch 2, worker 1; lỗi được ghi rõ thay vì để trống | `PASS_WITHIN_SCOPE`; provider vẫn chặn |
| Sanitizer | 44 dòng có reference không hợp lệ bị ép ABSTAIN; 5 invalid chunk IDs và 48 invalid quotes bị loại | `PASS_WITHIN_SCOPE` |
| Postcondition | 1.000 rows, 1.000 unique IDs, IDs khớp discovery, policy fail-closed, 0 invalid citation/quote sau sanitizer | `PASS_WITHIN_SCOPE` |
| Human queue | Workbook có 1.000 dòng, 33 cột, giữ 3 sheet; gold fields vẫn trống và review status vẫn `NEEDS_HUMAN_REVIEW` | `PASS_WITHIN_SCOPE` |
| Runtime safety | Health 8000/8001/8002 đều trả lời; production và test PID không đổi trong các probe | `OBSERVED`; không phải release proof |

## Phân bố dữ liệu thực tế

| Trạng thái | Số dòng | Ý nghĩa |
|---|---:|---|
| `COMPLETED` | 185 | Có structured candidate record, nhưng cả 185 đều `abstain=true` và answer rỗng |
| `NO_TEXT_ABSTAIN` | 565 | Không có text fetched để làm evidence |
| `REQUEST_ERROR` | 250 | Provider bridge thất bại; error thật là `Insufficient credits`, không được xem là answer |
| **Tổng** | **1.000** | **Không có provisional answer nào non-empty** |

Trong candidate contexts, 566 dòng có 0 context; 431 dòng có 4 context; 2 dòng có 2 context và 1 dòng có 3 context. Vì vậy, discovery hiện mới có text cho 434/1.000 dòng, và phần lớn nguồn vẫn có nguy cơ lệch chủ đề. Các sample completed được lưu trong `phase3_candidate_enrichment_quality.json` để audit, không được dùng làm gold oracle.

## Kiểm tra citation và provenance

Sanitizer đã kiểm tra mỗi `cited_candidate_chunk_id` có tồn tại trong các context của chính dòng đó và mỗi evidence quote có thể tìm thấy trong text của chunk tương ứng. Reference sai bị loại; dòng bị ảnh hưởng chuyển sang `abstain=true`, answer rỗng và không được promote. Review queue lưu `candidate_context_chunk_ids`, `candidate_evidence_quotes`, trạng thái sanitizer, error, `text_sha256`, URL/final URL và hash của artifact nguồn để người duyệt có thể truy ngược provenance.

## Human review queue

File `rag_gold_v2_human_review_queue_enriched_v1.xlsx` là queue để người dùng xác nhận candidate. Script đã kiểm chứng: đủ 1.000 dòng và ID duy nhất; các sheet `Review Queue`, `Instructions`, `Allowed Values` còn nguyên; tất cả gold fields vẫn blank; tất cả dòng vẫn `NEEDS_HUMAN_REVIEW`; và mọi candidate có `candidate_gold_promotion=FORBIDDEN`. Việc mở queue hoặc có provisional fields **không tạo verified gold**.

## Gate Ragas/ARES và release

| Gate | Trạng thái | Lý do |
|---|---|---|
| Candidate artifact schema/provenance | `PASS_WITHIN_SCOPE` | Đủ 1.000 dòng, dedup, sanitizer và policy checks đạt |
| Ragas pilot | `REPRODUCIBLE_PILOT` | Chỉ pilot 3 golden cases trước đó, seed 42; không mở rộng thành full benchmark |
| Ragas full 1.000 | `BLOCKED` | Có 0 eligible gold rows |
| ARES full | `BLOCKED` | Chưa có human validation set |
| Real RAG 1.000 câu | `BLOCKED` | Không có gold answer reviewed và không có provisional answer hợp lệ |
| SCP release gate | `BLOCKED` | Thiếu gold, human review, full Ragas/ARES, task-kernel/chaos/security/recovery evidence |

## Việc cần để tiếp tục đúng quy trình

Người duyệt cần mở `rag_gold_v2_human_review_queue_enriched_v1.xlsx`, kiểm tra candidate source, context và evidence quote, sau đó điền `gold_source_url`, `gold_answer`, `gold_chunk_ids`, `evidence_quote`, `reviewer_id`, `reviewed_at` và quyết định review theo đúng Instructions. SCP chỉ được promote các dòng có đủ canonical URL, evidence, chunk ID ổn định và reviewer provenance. Sau tối thiểu 50 dòng được người dùng xác nhận, pipeline mới có thể tạo verified subset và chạy Ragas/ARES trên tập eligible; không được suy ra điểm full 1.000 từ pilot.

## Verdict cuối

**CANDIDATE_ARTIFACT_READY / OVERALL_RELEASE_BLOCKED / REAL_RAG_1000_NOT_PROVEN.** Artifact candidate đã sẵn sàng để người dùng review, nhưng mục tiêu “SCP trả lời được toàn bộ bài thi 1.000 câu bằng câu trả lời được kiểm chứng” **chưa đạt và không được báo là đã đạt**.

## References

[1] `phase3_candidate_enrichment_full_v2_sanitized.jsonl` — artifact đã sanitizer và hash kiểm chứng.

[2] `phase3_candidate_enrichment_v2_postcondition.json` — postcondition validator report.

[3] `phase3_candidate_enrichment_quality.json` — quality/provenance analysis và samples.

[4] `rag_gold_v2_human_review_queue_enriched_v1.xlsx` — review queue enriched cho người dùng xác nhận.

[5] `rag_gold_v2_human_review_queue_enriched_v1_manifest.json` — manifest, hash và policy bảo vệ gold.

[6] `phase3_full_gate_report.json` — gate Ragas/ARES hiện vẫn BLOCKED vì 0 eligible gold rows.
