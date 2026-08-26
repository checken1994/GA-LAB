# SCP Human Review Workflow

## Người dùng không cần biết code

Mở HTML queue bằng trình duyệt, nhập một `Reviewer ID`, mở từng URL nguồn, đọc câu hỏi/câu trả lời và chọn một trong ba quyết định: `VERIFIED`, `REJECTED`, hoặc `NEEDS_MORE_EVIDENCE`. Nếu nguồn không mở được hoặc câu hỏi có thông tin hiện tại/high-stakes mà nguồn không đủ mới, chọn `NEEDS_MORE_EVIDENCE`.

HTML chỉ là giao diện nhập liệu cục bộ. Nó không tự ký, không tự tạo Gold và không thể biến review của model thành review của người thật. CSV xuất ra phải được một người có quyền review ký/đóng gói bằng bước finalize.

## Tạo queue

Từ root GA-LAB:

```bash
python3 benchmark/review_workflow.py build-queue \
  benchmark/gold_anchor_50_v2_candidates.jsonl \
  reports/human_review_queue_50.csv \
  reports/human_review_queue_50.html
```

## Finalize quyết định reviewer

Nếu tổ chức review có secret key quản lý riêng, không commit key vào repository; truyền nó qua biến môi trường:

```bash
SCP_REVIEW_HMAC_KEY='do-not-commit-this-key' \
python3 benchmark/review_workflow.py finalize-decisions \
  reports/reviewer-decisions.csv \
  reports/reviewer-decisions-finalized.csv
```

Bước này chỉ thêm `decision_hash` và `review_signature` cho các dòng đã có quyết định. Dòng trống vẫn trống. Nếu không truyền key, quyết định VERIFIED sẽ bị validator chặn.

## Validate trước khi nộp cho Ragas/Gold gate

```bash
SCP_REVIEW_HMAC_KEY='review-key-from-authorized-reviewer' \
python3 benchmark/review_workflow.py validate-decisions \
  benchmark/gold_anchor_50_v2_candidates.jsonl \
  reports/reviewer-decisions-finalized.csv \
  reports/reviewer-validation.json
```

Chỉ khi validator trả `PASS_WITHIN_SCOPE` cho các dòng cụ thể, source URL khớp, thời gian có timezone, hash đúng và chữ ký hợp lệ thì các dòng đó mới **đủ điều kiện kỹ thuật để xem xét**. Ragas runner và người duyệt vẫn phải kiểm tra thêm ground truth, citation provenance và phạm vi dữ liệu. `eligible_for_gold` không phải là tuyên bố rằng reviewer đã đánh giá đúng nội dung; nó chỉ là kết quả kiểm tra record.

## Quy tắc fail-closed

Thiếu reviewer ID, timestamp, URL, evidence quote cho VERIFIED, source khớp, decision hash hoặc HMAC signature đều bị `BLOCKED`. Không dùng HTTP 200, model confidence, token overlap, independent LLM review, hoặc câu trả lời tự sinh để thay thế human verification.
