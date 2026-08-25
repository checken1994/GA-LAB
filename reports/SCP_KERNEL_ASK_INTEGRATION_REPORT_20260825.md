# Báo cáo tích hợp Kernel vào `/ask` và lọc candidate RAG — 25/08/2026

## 1. Kết luận ngắn

Đợt này đã tạo được một **integration candidate có bằng chứng trong phạm vi kiểm tra**, chưa phải tuyên bố production-ready hay Agent OS hoàn chỉnh. Task Kernel lấy từ bản PC `scp-agent-structure-debt` tại commit `cb132a5`, trong đó fencing token mới nhất đã được kiểm tra trực tiếp ở `_assert_lease`: lease cũ bị từ chối khi không còn là token mới nhất. Bundle đã được đưa vào nhánh `integration/kernel-ask-20260825` tách từ GA-LAB `23f41b7`, không sửa trực tiếp `main` và không dùng port 8000.

Route `/ask` thật hiện được bọc bởi kernel khi request có `rag_enabled`, `contexts` hoặc `retrieved_context`. Nhánh RAG này chỉ dùng câu trả lời ứng viên và evidence do request cung cấp; nó không tự gọi web hoặc LLM fallback. Kernel tạo task, chuyển state, cấp lease, ghi checkpoint/idempotency, gọi handler, kiểm tra độc lập rồi mới cho `COMPLETED`. Nếu thiếu evidence, prompt injection, global kill, retry trùng hoặc lỗi handler thì hệ thống fail-closed hoặc chuyển sang `HUMAN_REVIEW`/`CANCELLED`/`FAILED`.

> Verdict tổng hợp: **PASS_WITHIN_SCOPE / CANDIDATE_NOT_PROVEN**. Điều này nghĩa là các kiểm tra đã đạt trong workload và snapshot được ghi rõ; chưa đủ để nói toàn bộ SCP đã hoàn thiện hoặc RAG 1.000 câu đã đúng.

## 2. Vì sao phải sửa theo cách này

**Tại sao candidate phải lọc trước human review?** Bộ đầu vào có 1.000 câu nhưng canonical fetch hiện tại có nhiều kết quả lệch câu hỏi. Nếu mở review cả 1.000 hàng, người review phải tốn công vào các hàng có tín hiệu thấp. Vì vậy đã dùng short query và `shared_term_count` làm heuristic pre-review. Heuristic này chỉ để sắp xếp ưu tiên, không tạo `gold_answer` và không tự tạo `gold_chunk_ids`.

**Tại sao DDG không được coi là nguồn thành công toàn phần?** DDG HTML/lite trên PC bị timeout và probe sandbox trả challenge chống bot. Không bypass CAPTCHA/challenge. DDG Instant Answer API được thử bằng `curl` có timeout; full screening sandbox có 189 phản hồi API, nhưng các kết quả được chọn cuối cùng đều rơi về `canonical_fetch_existing` vì URL DDG không đạt điều kiện source hợp lệ. Do đó shortlist hiện là **canonical shortlist có DDG short-query screening**, chưa phải DDG source-validated corpus.

**Tại sao không gọi K-2/K-3 đã đóng?** Tìm kiếm trực tiếp trong source, lịch sử Git, scripts acceptance và reports không tìm thấy định nghĩa chính thức của nhãn `K-2` hoặc `K-3`. Vì vậy báo cáo không tự gán tên. Các điểm hở có bằng chứng cụ thể đã được sửa và test riêng, nhưng chỉ gọi theo hành vi: `retrieved_context` bị bỏ qua, logical identity dùng thời gian/UUID, xử lý dict response, duplicate retry và failure state.

## 3. Kết quả candidate pre-review

| Hạng mục | Kết quả thực tế | Ý nghĩa |
|---|---:|---|
| Input câu hỏi | 1.000 | Đúng bộ benchmark đã hash trước khi xử lý |
| Screening rows | 1.000 | Không mất hàng trong bước screening |
| DDG API phản hồi trong full run sandbox | 189 | Chỉ là tín hiệu bổ sung; không đồng nghĩa source được chọn |
| Strict high-signal | 62 | `shared_term_count >= 2` và coverage `>= 0,20` |
| Shortlist cuối | 191 | Tối đa 200; dữ liệu thật chỉ đủ 191 hàng đạt cutoff relaxed |
| High-signal trong shortlist | 62 | Có thể review trước |
| Review-signal trong shortlist | 129 | Đạt cutoff relaxed, cần reviewer xác minh trực tiếp |
| Source được chọn trong shortlist | 191 canonical | DDG không được coi là source hợp lệ trong các hàng cuối |
| Gold answer/gold chunk IDs | Để trống | Không tự tạo gold truth |
| Trạng thái gold | `SOURCE_FETCHED_NOT_REVIEWED` | Chưa được chuyên gia duyệt |

Shortlist cuối sử dụng cutoff kỹ thuật `shared_term_count >= 1` và coverage `>= 0,08` để đạt quy mô gần 200 mà vẫn giữ tín hiệu lexical khác 0. Đây là **cutoff review-signal**, không phải ngưỡng chứng minh factual correctness. 62 hàng đạt ngưỡng mạnh được gắn `HIGH_SIGNAL`; 129 hàng còn lại gắn `REVIEW_SIGNAL` để người review biết chúng yếu hơn.

Đã bổ sung script screening v2 có `--limit`, `--start-offset`, `--workers 1`, timeout, rate-limit, checkpoint atomic và progress log. Pilot PC bounded đúng 20 dòng đã hoàn tất: screening có 20 dòng, checkpoint/progress đủ 20, DDG API trên PC có 0 phản hồi thành công và 4 hàng canonical đủ strict cutoff. Không chạy lại HTML DDG và không bypass challenge.

## 4. Ma trận core giữa hai repository

Inventory được lấy từ Git, không dùng con số ước lượng “403” làm sự thật.

| Phân loại | Số file |
|---|---:|
| `scp-agent` tracked | 689 |
| GA-LAB tracked | 1.172 |
| Common paths | 475 |
| Common blob-identical | 435 |
| Common blob-different | 40 |
| Chỉ có `scp-agent` | 214 |
| Chỉ có GA-LAB | 697 |
| Shared kernel paths | 6 |
| Kernel-only trong `scp-agent` | 14 |
| Stack-only trong GA-LAB | 174 |

Chính sách hợp nhất là: 435 file giống nhau được giữ theo hai repository; 40 file khác nhau không bulk-copy mà phải review theo seam; 14 file kernel-only được lấy thành bundle nhỏ có test; 174 file stack-only của GA-LAB vẫn là integration surface. Trong đợt này không ghi đè mù toàn bộ 475 file.

## 5. Những thay đổi kernel và `/ask`

| Thành phần | Thay đổi |
|---|---|
| `scp/task_kernel.py` | Port bản PC `cb132a5`, có durable SQLite journal/projection, state machine, lease TTL, heartbeat, fencing token, checkpoint, idempotency, kill switch, recovery decision và independent commit gate |
| `scp/trace_ledger.py` | Append-only trace có redaction và hash chain |
| `scp/verifier.py` | Independent postcondition verifier, không hỏi model đã xong chưa |
| `scp/ask_kernel_adapter.py` | Adapter v2 cho `/ask`: stable identity, `retrieved_context`, duplicate retry block, verifier v2, fail-closed response và exception recovery |
| `scp/api_server.py` | Route `/ask` thật gọi adapter cho request RAG; JudgeCore bình thường vẫn giữ nguyên cho request không có RAG evidence |
| RAG branch | Chỉ nhận evidence trong request, công bố `rag-verified`/`input_context_only`, không gọi web/LLM fallback |

Stable identity ưu tiên header `X-SCP-Idempotency-Key` hoặc `Idempotency-Key`. Nếu không có header, identity dùng session và hash của question/context; không còn dùng `time_ns()` hoặc UUID để tạo task ID. Vì vậy retry cùng logical request không tự dispatch handler lần hai.

## 6. Kiểm thử tĩnh và contract

| Gate | Kết quả | Phạm vi |
|---|---|---|
| Pytest collection | 116 test được collect | Không phải `no tests ran` |
| Targeted kernel + adapter | 13 passed | Fencing, recovery, retrieved-only, missing evidence, kill, retry, crash |
| Full pytest | 116 passed, 2 warnings | Toàn bộ GA-LAB integration branch |
| Critical Ruff | PASS | `E9,F63,F7,F82` trên file thay đổi |
| Strict full Ruff | Chưa sạch | Bundle kernel reference giữ một số legacy style/import warnings; không dùng profile này làm functional acceptance |
| Python compile | PASS | API, adapter, kernel, trace, verifier, tests |
| Bandit | exit 0 | Bundle kernel/adapter |

Đã có test cho hai worker claim, expiry/latest fencing, global kill, terminal immutability, checkpoint tamper, journal tamper, projection rebuild, idempotency, independent verifier, retrieved-context-only, missing context, injection marker, duplicate retry và handler crash.

## 7. Runtime evidence chỉ trên 8002

Service được chạy bằng `SCP_PORT=8002`, host `127.0.0.1`, production mode tắt, egress deny và DB/trace riêng. Trước start và sau clean stop đều không có listener trên 8000; port 8000 không được khởi động hoặc gọi.

| Case | HTTP/result | State/evidence |
|---|---|---|
| Health | `200` | Service thật trên `127.0.0.1:8002` |
| Golden context-backed | `200`, `PASS`, `UPHOLD`, `SUCCESS`, `OK` | `rag-verified`, provenance `input_context_only`, grounded ratio `1.0`, task `COMPLETED` |
| Kernel journal | PASS | 9 events, hash chain hợp lệ |
| Checkpoint/idempotency | PASS | `rag-read` checkpoint và logical action record tồn tại |
| Trace | PASS | 2 entries, hash chain hợp lệ |
| Missing context | `FAIL`, `ESCALATE`, withheld | Task `HUMAN_REVIEW` |
| Prompt injection | `FAIL`, `KILL`, withheld | Không trả nội dung ứng viên |
| Global kill | `FAIL`, `KILL`, withheld | Handler không chạy, task `CANCELLED`, kill đã tắt lại sau test |
| Retry cùng idempotency key | `FAIL`, `KILL`, withheld | Không tạo task thứ hai/không chạy handler lần hai |
| Handler crash | Unit/integration `RuntimeError` | Task `FAILED`, trace vẫn hợp lệ |

Lần runtime đầu tiên trước khi thêm explicit context-RAG branch đã bị withheld vì JudgeCore hiện tại không tự đọc `contexts`/`rag_enabled`. Evidence failure đó được giữ riêng để chứng minh quy trình đã quan sát và tự sửa, không xóa mâu thuẫn. Sau sửa, golden runtime v2 đạt toàn bộ postconditions trong scope.

## 8. Mức bằng chứng và giới hạn còn lại

| Claim | Mức bằng chứng | Đánh giá |
|---|---|---|
| Bundle Task Kernel có contract cơ bản | Static + integration | `PASS_WITHIN_SCOPE` |
| `/ask` thật nối kernel | Runtime C trên workload context-backed | `PASS_WITHIN_SCOPE` |
| Global kill/retry/missing/injection fail-closed | Runtime trên 8002 | `PASS_WITHIN_SCOPE` |
| RAG 1.000 câu factual đúng | Chưa có gold độc lập đầy đủ | `UNPROVEN` |
| Ragas/ARES metric đầy đủ | Chưa chạy trên gold đã review | `UNPROVEN` |
| Provider/browser chaos và OS sandbox/egress end-to-end | Chưa chứng minh đầy đủ | `UNPROVEN` |
| Production port 8000 | Không kiểm tra theo yêu cầu | `NOT_TOUCHED` |
| K-2/K-3 | Không có định nghĩa chính thức để đối chiếu | `UNRESOLVED_LABELS` |

Vì vậy không được gọi đây là “SCP đã giải xong 1.000 câu RAG”, “production-ready”, hoặc “Agent OS release”. Kết quả đúng hơn là **Agent Runtime candidate cho nhánh RAG context-backed**, với kernel lifecycle đã có evidence trong workload nhỏ.

## 9. Rollback và provenance

Snapshot gốc GA-LAB vẫn là `23f41b7efae89b3b1e2a96c50cae51021ac9098d`. Nhánh phục hồi được tạo là `backup/pre-kernel-ask-20260825`. Nhánh thay đổi là `integration/kernel-ask-20260825`; chỉ fast-forward vào `main` khi commit, test gate, runtime evidence và remote check đều đúng parent.

Artifact chính nằm trong `reports/core_repo_matrix_20260825/`, `reports/ddg_pilot20_20260825/`, `reports/runtime_8002_20260825_v2/`, cùng các file shortlist trong `data/`. File screening 1.000 dòng và queue 191 dòng dùng dữ liệu đầu vào đã hash; queue không ghi đè queue review gốc 1.000 dòng.

## 10. Tài liệu evidence chính

| Evidence | Nội dung |
|---|---|
| `data/rag_ddg_short_alignment_screening_20260825.jsonl` | 1.000 screening records |
| `data/rag_gold_review_queue_ddg_short_20260825.jsonl` | 191 pre-review rows |
| `data/rag_gold_review_queue_ddg_short_20260825.csv` | Bản CSV cho human review |
| `reports/ddg_short_review_final_summary_20260825.json` | Summary/cutoff/source note |
| `reports/ddg_pilot20_20260825/` | Bounded 20-row checkpoint/progress proof |
| `reports/core_repo_matrix_20260825/` | Inventory và 40 shared-different paths |
| `reports/runtime_8002_20260825_v2/golden_evidence_report.json` | Golden task postconditions |
| `reports/runtime_8002_20260825_v2/runtime_evidence_summary.json` | Tổng hợp negative/kill/trace/journal evidence |
| `tests/test_task_kernel_acceptance.py` | Kernel contract tests |
| `tests/test_ask_kernel_integration.py` | `/ask` adapter integration/recovery tests |

**Tác giả:** Manus AI
