# Phase 3 RAG của SCP — Công bố kỹ thuật về remediation evidence

**Trạng thái: bản phát hành candidate evidence; chưa phải benchmark RAG đã xác minh.**

SCP đã phát hành gói evidence Phase 3 theo nguyên tắc fail-closed tại commit [`a92776ffc7da1c70cc209428cb224494c816471e`](https://github.com/checken1994/GA-LAB/commit/a92776ffc7da1c70cc209428cb224494c816471e). Gói này giữ nguyên bộ candidate lịch sử 50 dòng và bổ sung ledger review JSONL/CSV/XLSX có version, metadata fetch nguồn độc lập, quote đúng nằm trong source ở nơi quan sát được, validator nghiêm ngặt, runner Ragas thật, audit điều kiện ARES và ma trận proof gap.

Bản phát hành này **cố ý không tuyên bố** 50 câu đã trở thành Gold được xác minh, Ragas đã tạo điểm chính thức, ARES đã chạy, hoặc benchmark 1.000 câu đã hoàn tất. Những tuyên bố đó vượt quá bằng chứng hiện có.

| Hạng mục | Kết quả quan sát được | Ý nghĩa phát hành |
|---|---:|---|
| Số dòng Phase 3 | 50 ID duy nhất | Ledger candidate đầy đủ về cấu trúc |
| Quote máy kiểm tra nằm trong source | 9/50 | Chỉ là candidate evidence; không giả mạo người review |
| Gold đã được người xác minh | 0/50 | Chặn promote Gold |
| Dòng được runner Ragas v2 nhận | 0/50 | Không có điểm benchmark chính thức |
| Điểm ARES | `null` | Preconditions bị chặn |
| Pilot `/ask` isolated | 3/3 HTTP 200 | Cả 3 là `UNKNOWN`/`ESCALATE`; không có factual pass |
| Release gates | 172 pytest pass; compile, Ruff, Bandit medium/high, dashboard build và npm audit pass trên CI | Gate mã nguồn/artifact, không phải proof chất lượng RAG |

## Đã sửa gì

Extractor cũ được **supersede**, không âm thầm rewrite. Builder mới không bao giờ lấy answer làm evidence quote. Nó fetch source độc lập, lưu HTTP status, thời điểm fetch, content hash, cache path, canonical URL, chunk hash và trạng thái quote containment; đồng thời giữ các câu temporal, pháp lý, y tế và tài chính ở trạng thái blocked cho đến khi có nguồn hiện hành có thẩm quyền và review độc lập. Những mapping sai đã quan sát, gồm CH-0036, CH-0042, CH-0049 và CH-0050, vẫn bị đánh dấu rõ là `SOURCE_MISMATCH_NEEDS_REBUILD`.

Ba định dạng JSONL, CSV và Excel được kiểm tra có cùng 50 ID và cùng schema. Validator trả về `PASS_WITHIN_SCOPE`, không có lỗi row count, ID trùng, hash, quote containment hoặc lệch header giữa các định dạng. Điều đó chỉ chứng minh file nhất quán nội bộ; **không chứng minh answer đúng sự thật**.

## Ranh giới phương pháp Ragas và ARES

Ragas cung cấp các metric đánh giá từng thành phần của pipeline LLM/RAG, gồm faithfulness, answer relevancy, context precision và context recall [1]. Context precision đánh giá retriever có xếp các chunk liên quan cao hơn chunk không liên quan hay không [2]. Vì vậy SCP bổ sung `benchmark/run_ragas_v2.py`, runner chỉ gọi API chính thức `ragas.evaluate()` sau khi Gold vượt qua admission gate rõ ràng.

Runner thật được thử trên output runtime đã ghi lại của SCP. Nó nhận 0 dòng vì có 32 dòng runtime HTTP 429 và 18 dòng Gold chưa đủ điều kiện. Runner không dùng token-overlap fallback và phát hành `BLOCKED_NO_VERIFIED_ROWS`. Một diagnostic một dòng đã gọi `ragas.evaluate()` thật với Ragas 0.1.7 và `gpt-5-mini`, nhưng endpoint embedding trả HTTP 404 cho các metric cần embedding. Diagnostic chỉ dùng LLM-judge có thể hoàn tất, nhưng sample trả context precision 0.0, context recall 0.0 và faithfulness `NaN` sau một lỗi parse output của judge. Đây là bằng chứng về hành vi thực thi, **không phải điểm benchmark**.

ARES đánh giá context relevance, answer faithfulness và answer relevance bằng dữ liệu synthetic, lightweight judge và một tập human-annotated cho prediction-powered inference [3]. Repository ARES chính thức nêu ba đầu vào cần có: ít nhất 50 query-document-answer đã được con người gán nhãn, tập few-shot và tập unlabeled lớn hơn để đánh giá [4]. SCP hiện chưa có các đầu vào đã xác minh này; môi trường Windows cũng không import được package `ares`. Vì vậy ARES trả `BLOCKED_PRECONDITIONS`, điểm là `null`.

## Bằng chứng runtime và release

SCP chỉ được chạy trên loopback isolated `127.0.0.1:8002`, egress deny và thư mục database/trace riêng. Health response nhận diện commit `e97bd879...` trong pilot baseline. Ba câu hỏi duy nhất trả HTTP 200, nhưng cả ba bị governance đưa về `UNKNOWN`/`ESCALATE`; sau đó runtime được dừng và xác nhận cả port 8000 lẫn 8002 đều không còn listener. Bản phát hành cuối được fast-forward merge vào `main`, sau đó SCP Release Gate trên GitHub Actions chạy thành công tại [32940493975](https://github.com/checken1994/GA-LAB/actions/runs/32940493975).

CI xanh chứng minh gate mã nguồn có thể tái lập, không chứng minh mọi câu trả lời đều đúng. Vì vậy proof-gap matrix vẫn giữ các mục wiring connector side-effect, capability revoke xuyên tool layer, fairness/quota của queue, timeout/recovery của provider và chuỗi golden task planner-to-audit ở trạng thái `UNPROVEN` hoặc `STATIC_PROVEN_ONLY` khi chưa có evidence end-to-end.

## Các artifact trong repository

| Artifact | Mục đích |
|---|---|
| [`gold_anchor_50_v2_candidates.jsonl`](https://github.com/checken1994/GA-LAB/blob/main/benchmark/gold_anchor_50_v2_candidates.jsonl) | 50 candidate record có provenance và blocked status |
| [`gold_anchor_50_v2_review_ledger.xlsx`](https://github.com/checken1994/GA-LAB/blob/main/benchmark/gold_anchor_50_v2_review_ledger.xlsx) | Ledger review Excel cùng schema 50 dòng |
| [`validate_phase3_gold_v2.py`](https://github.com/checken1994/GA-LAB/blob/main/tools/validate_phase3_gold_v2.py) | Validator schema xuyên JSONL/CSV/XLSX |
| [`run_ragas_v2.py`](https://github.com/checken1994/GA-LAB/blob/main/benchmark/run_ragas_v2.py) | Runner chỉ dùng Ragas chính thức, fail-closed |
| [`ares_preconditions_v2.json`](https://github.com/checken1994/GA-LAB/blob/main/benchmark/ares_preconditions_v2.json) | Kết quả ARES precondition, score là null |
| [`phase3_proof_gap_matrix_v1.json`](https://github.com/checken1994/GA-LAB/blob/main/reports/phase3_proof_gap_matrix_v1.json) | Trạng thái proof gắn với evidence cho các claim còn lại |

## Bài đăng Reddit

**Tiêu đề:** SCP Phase 3 RAG evidence remediation: 50 candidate nhất quán cấu trúc, 0 Gold đã xác minh, không giả điểm Ragas/ARES

Chúng tôi đã phát hành bản cập nhật Phase 3 của SCP theo proof-first. Gói gồm 50 record duy nhất ở JSONL, CSV và Excel; metadata fetch nguồn độc lập; quote nằm trong source cho 9 dòng; runner Ragas fail-closed; và báo cáo ARES precondition. Validator pass contract dữ liệu, nhưng Gold promotion vẫn bị chặn vì cả 50 dòng cần review độc lập.

Chúng tôi cũng chạy thật đường API Ragas 0.1.7. Runner benchmark nhận 0 dòng thay vì chấm dữ liệu candidate. Diagnostic một dòng đã đi tới `ragas.evaluate()` nhưng vướng endpoint embedding; diagnostic LLM-only cho thấy context precision/recall bằng 0 ở sample quan sát được. ARES không được chấm vì chưa có human set, few-shot set và unlabeled set đúng yêu cầu. Release này cố ý thận trọng: CI xanh, nhưng chưa tuyên bố chất lượng factual RAG.

Câu hỏi chính để cộng đồng review là provenance schema và admission gate đã đủ chặt trước khi thu thập annotation độc lập hay chưa. Vui lòng đọc commit và artifact; không coi output token-overlap cũ là Ragas.

## Chuỗi X

1/ Cập nhật SCP Phase 3: chúng tôi đã phát hành commit `a92776f`. Đây là **candidate evidence release**, chưa phải benchmark RAG đã xác minh.

2/ Ledger 50 dòng nhất quán giữa JSONL/CSV/XLSX. Có 9 dòng có quote nằm trong source do máy kiểm tra. Cả 50 vẫn candidate-only; không giả mạo human review.

3/ Runner Ragas thật fail-closed: 0 dòng admitted, 0 proxy fallback, không có official score. Diagnostic đã gọi `ragas.evaluate()` nhưng endpoint embedding trả 404.

4/ ARES là `BLOCKED_PRECONDITIONS`: thiếu human set đã xác minh, few-shot set, unlabeled evaluation set và package importable. Không có điểm ARES.

5/ Pilot SCP 8002: 3/3 HTTP 200, cả 3 `UNKNOWN`/`ESCALATE`. CI và post-merge gate xanh, nhưng factual RAG và nhiều proof gap Agent OS vẫn chưa được chứng minh.

## Tài liệu tham chiếu

[1]: https://docs.ragas.io/en/v0.1.21/concepts/metrics/ "Ragas Metrics — đánh giá theo thành phần"
[2]: https://docs.ragas.io/en/stable/concepts/metrics/available_metrics/context_precision/ "Ragas Context Precision"
[3]: https://aclanthology.org/2024.naacl-long.20/ "ARES: An Automated Evaluation Framework for Retrieval-Augmented Generation Systems, NAACL 2024"
[4]: https://github.com/stanford-futuredata/ARES "Repository ARES của Stanford FutureData và data contract"
