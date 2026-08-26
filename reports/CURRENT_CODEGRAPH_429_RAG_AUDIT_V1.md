# Audit hiện tại của SCP: codegraph, HTTP 429 và chuẩn RAG

**Snapshot được kiểm tra:** commit `1131e4219b09e6bc4f0fe55330679809fbc44c55` trên `main`. Báo cáo này phân biệt rõ điều đã quan sát, suy luận được và phần chưa chứng minh.

## 1. Codegraph hiện tại

Codegraph được tạo bằng AST từ thư mục `scp/`. Graph chỉ ghi cạnh import nội bộ có thể resolve được; nó không giả định rằng mọi lời gọi động, plugin, subprocess hoặc HTTP call đều xuất hiện trong graph. Kết quả là **451 module/file nodes**, **849 import edges** và một graph tập trung gồm **51 nodes, 227 edges**. Mỗi node có đường dẫn tương đối, số dòng, trạng thái parse và SHA-256 của file tại snapshot.

| Thành phần | Kết quả |
|---|---:|
| Snapshot commit | `1131e4219b09e6bc4f0fe55330679809fbc44c55` |
| AST nodes | 451 |
| Internal import edges | 849 |
| Focused nodes | 51 |
| Focused edges | 227 |
| Graph generator | `tools/build_codegraph_current.py` |
| Full graph | `reports/codegraph_20260826/codegraph.json`, `.csv`, `.mmd` |
| Focused graph | `reports/codegraph_20260826/codegraph_focused.mmd` |

Luồng tập trung quan trọng hiện tại là:

> `/ask` (`scp.api_server`) → `LLMGateway/Judge` → `judge_parts` → governance/policy/adversary/reverify → `AskKernelAdapter` → `TaskKernel` + `trace_ledger`; nhánh hands đi qua planner → executor → action registry/process manager; nhánh RAG có `canonical_retriever` và capability vector DB.

Codegraph cho thấy một điểm cần chú ý: `scp.runtime.judge_parts.judgecore_mixin.py` còn **3.523 dòng**, `scp.hands.planner.py` **871 dòng**, `scp.autofix.policy_gate.py` **851 dòng** và `scp.task_kernel.py` **834 dòng**. Đây là dấu hiệu kiến trúc lớn và khó audit, nhưng số dòng không phải bằng chứng rằng chức năng bên trong đã chạy end-to-end.

## 2. Vì sao gọi API gặp 429 nhưng không đổi model?

Câu trả lời ngắn là: **429 mà người dùng thấy nhiều khả năng là 429 của chính SCP ở lớp HTTP DoS/rate-limit, không phải 429 của nhà cung cấp LLM. Hai loại lỗi nằm ở hai tầng khác nhau.**

### 2.1. 429 của SCP xảy ra trước khi gọi model

Trong `scp/api_server.py` tại đoạn xử lý `/ask`, SCP gọi `judge.dos_protection.check_request(client_ip)` trước khi vào pipeline judge. Nếu alert có `action_taken` là `block` hoặc `throttle`, route trả HTTP 429 ngay. Vì request bị chặn ở đây, `LLMGateway`, Ollama và OpenRouter **chưa được gọi**, nên không có model nào để chuyển sang.

`DoSProtectionEngine` có ba nguồn chặn chính:

| Nguồn 429 | Điều kiện | Model fallback có chạy không? |
|---|---|---:|
| Per-IP minute rate limit | Từ 60 request/phút/IP | Không |
| Per-IP hour rate limit | Từ 1.000 request/giờ/IP | Không |
| Circuit breaker | 10 verdict `UNKNOWN`/`SPECULATIVE` liên tiếp, sau đó cooldown | Không |
| Provider quota/rate limit | OpenRouter trả 429/402 trong lúc đã gọi model | Có, trong `OpenRouterProvider` |

Trước remediation, route `/ask` luôn trả JSON lỗi chung và không truyền `Retry-After` từ `DoSAlert`. Bản sửa đã bổ sung `status_code=429` và `Retry-After` động cho minute/hour limiter, đồng thời route truyền `recommended_headers` ra HTTP response. Circuit-breaker vốn đã có `Retry-After: 5`.

### 2.2. 429 của OpenRouter mới kích hoạt đổi model

Trong `scp/llm_gateway/client.py`, `OpenRouterProvider.chat()` có chain riêng:

> paid model → task-specific free model → `openrouter/free` → trả `None` nếu tất cả thất bại.

`LLMGateway.chat()` còn có route Ollama theo task. Vì vậy cơ chế chuyển model **đã tồn tại ở tầng provider**. Reproduction cô lập đã chứng minh khi paid model giả lập trả `HTTP 429 (quota/rate-limit)`, code gọi tiếp `openai/gpt-oss-20b:free` và nhận được câu trả lời fallback. Kết quả: **2/2 regression assertions pass**.

Ngược lại, reproduction DoS cho thấy request thứ hai sau khi đạt giới hạn có `alert_type=rate_limit`, `action_taken=block`, `status_code=429`, và `model_fallback_invoked=false`. Đây là hành vi đúng của guard: đổi model không thể làm một request bị chặn ở HTTP boundary trở thành hợp lệ.

### 2.3. Live proof trên port 8002

Một service đúng snapshot `1131e42` được chạy trên `127.0.0.1:8002`, egress deny, DB/trace tách riêng. Harness gửi 12 request có session riêng. Kết quả quan sát được là **12/12 HTTP 429**, cả 12 có `Retry-After: 5`, body là `rate_limit_error`. Giá trị 5 giây khớp circuit-breaker cooldown; đây không phải bằng chứng OpenRouter trả 429. Server sau đó đã dừng và port 8002 được giải phóng.

Điều này giải thích vì sao việc “tự chuyển sang AI khác để gỡ lỗi” không xảy ra: **SCP đang tự bảo vệ trước khi bước chọn model bắt đầu**. Nếu client tiếp tục gửi dồn request, đổi model ở server sẽ làm tình hình DoS tệ hơn. Client/benchmark runner phải đọc `Retry-After`, backoff, giữ idempotency key và chỉ gửi lại sau cooldown.

## 3. Vì sao RAG không lấy một bộ “thông tin chuẩn hóa chính thức” mà phải tự tạo?

Có một nhầm lẫn quan trọng: **Ragas và ARES là framework đánh giá, không phải một kho Gold duy nhất cho mọi câu hỏi.**

Tài liệu Ragas mô tả đây là thư viện giúp biến kiểm tra cảm tính thành vòng lặp đánh giá có hệ thống; hàm `evaluate()` nhận một `dataset`, danh sách metrics và tùy chọn LLM/embeddings [1] [2]. Dataset phải chứa đúng câu hỏi, contexts/retrieved contexts, answer và/hoặc ground truth phù hợp với metric. Ragas không thể tự biết “đoạn văn đúng” cho 1.000 câu tiếng Việt riêng của SCP nếu người xây benchmark chưa cung cấp nguồn chuẩn và gold chunk.

ARES cũng không phải kho đáp án sẵn. Paper ARES mô tả hệ thống dùng synthetic training data, lightweight judges và một tập human-annotated cho prediction-powered inference [3]. Repository ARES yêu cầu human validation set, few-shot examples và tập unlabeled query-document-answer lớn hơn [4]. Nói cách khác, ARES cần dữ liệu đánh giá đúng cho hệ thống đang đo.

Có các benchmark công khai để dùng thay vì tự tạo toàn bộ, nhưng mỗi benchmark đo một phạm vi khác:

| Benchmark/framework | Có gì | Có thay thế trực tiếp bộ 1.000 câu tiếng Việt của SCP không? |
|---|---|---:|
| Ragas | Metrics và evaluation API | Không; không phải corpus Gold |
| ARES | Judge/evaluation pipeline + data contract | Không; vẫn cần annotation/input |
| BEIR | Nhiều tập IR công khai, qrels và metric retrieval như NDCG/MAP/Recall/Precision [5] | Không trực tiếp; có thể dùng làm external retrieval lane |
| KILT | Nhiều task knowledge-intensive trên cùng snapshot Wikipedia, có đánh giá provenance [6] | Không trực tiếp; cần task/corpus tương thích |
| In-domain SCP dataset | Câu hỏi thật của người dùng, nguồn Việt Nam, freshness/legal/medical/finance | Cần thiết cho mục tiêu SCP, nhưng phải review độc lập |

Script cũ `tools/build_standard_rag_corpus.py` đang tự lấy **chunk đầu tiên** từ contexts, đặt `source_date='2026-08-17'` cho mọi dòng và ghi `gold_annotation_status='NOT_HUMAN_VERIFIED'`. Đây là **scaffolding chuẩn hóa nội bộ**, không phải Gold chính thức. Việc phải tự tạo artifact là cần thiết để lưu `canonical_url`, `source_title`, `chunk_id`, `chunk_hash`, quote, freshness và provenance cho đúng câu hỏi; nhưng cách builder cũ tạo dữ liệu chưa đủ nghiêm ngặt để dùng chấm điểm.

Cách đúng là dùng **hai lane tách biệt**:

1. **External reproducibility lane:** chạy BEIR/KILT hoặc benchmark công khai tương thích, giữ nguyên qrels/corpus/split chính thức và báo cáo metric retrieval theo đúng benchmark.
2. **SCP in-domain lane:** dùng câu hỏi tiếng Việt của SCP, fetch nguồn gốc có thẩm quyền, trích quote nằm trong source, gán gold chunk, review độc lập, ghi ngày hiệu lực/freshness và chỉ sau đó đưa vào Ragas/ARES.

Không được lấy điểm ở lane công khai để tuyên bố bộ câu hỏi riêng của SCP đã đạt. Ngược lại, không được gọi artifact tự tạo hiện tại là “official Ragas dataset”.

## 4. Những phần chưa hoàn thiện nghĩa là gì?

“Chưa hoàn thiện” không có nghĩa là không có code. Nó có nghĩa là **chưa có bằng chứng đủ mạnh ở đúng tầng cần chứng minh**. Ví dụ một method `reconcile_unknown()` có thể tồn tại và unit test pass, nhưng nếu chưa có process thật chết sau side-effect rồi reconcile với provider, thì claim production recovery vẫn là `UNPROVEN`.

| Phần | Bằng chứng hiện có | Trạng thái thật |
|---|---|---|
| Codegraph | AST snapshot 451 nodes/849 edges | Có snapshot, không chứng minh runtime semantics |
| HTTP DoS guard | Unit/reality test; live 429 + Retry-After | Đã chứng minh boundary guard; chưa tự động retry client |
| Provider fallback | Reproduction paid 429 → free model pass | Đã chứng minh trong OpenRouter path; chưa chứng minh mọi provider/network failure |
| Phase 3 Gold 50 | JSONL/CSV/XLSX nhất quán; 9 source-contained machine quotes | `CANDIDATE_NOT_PROVEN`, human verified 0/50 |
| Official Ragas score | `evaluate()` diagnostic thật nhưng embedding 404; runner admitted 0 | `BLOCKED_NO_VERIFIED_ROWS` |
| ARES | Thiếu human set, few-shot, unlabeled set và package importable | `BLOCKED_PRECONDITIONS` |
| 1.000 câu RAG | Candidate pipeline cũ có request errors/no context/empty answers | Gate `BLOCKED` |
| Connector side-effect → kernel reconcile | Method/test tĩnh có, call vào connector thật chưa đủ | `UNPROVEN` |
| Capability revoke xuyên tool layer | Có symbol/policy nhưng chưa có golden end-to-end | `UNPROVEN` |
| Queue fairness/quota/deadline | Có module/config, chưa có stress/chaos evidence đủ | `UNPROVEN` |
| Provider timeout/recovery | Có timeout ở một số adapter, chưa chứng minh side-effect uncertainty end-to-end | `UNPROVEN` |
| Golden task planner → policy → tool → observation → verifier → audit | Nhiều mảnh rời, chưa có một artifact chain hoàn chỉnh | `E2E_NOT_PROVEN` |

## 5. Kết luận

Lỗi 429 hiện được giải thích đúng theo tầng. **Nếu 429 xuất hiện ở `/ask`, SCP không nên đổi model; nó phải backoff theo `Retry-After` vì request chưa hề tới model. Nếu 429 xuất hiện từ OpenRouter sau khi model đã được gọi, gateway đã có fallback paid → free → auto-router.** Hai trường hợp này trước đây bị nhìn như một lỗi duy nhất nên gây hiểu nhầm.

RAG cũng được phân biệt đúng: **Ragas/ARES cung cấp cách đo; BEIR/KILT cung cấp một số benchmark/corpus công khai; còn bộ câu hỏi riêng của SCP cần in-domain Gold có provenance và review độc lập.** SCP đã tạo artifact chuẩn hóa để lưu những thông tin đó, nhưng artifact hiện tại mới là candidate scaffold; chưa được phép gọi là Gold/Ragas/ARES chính thức.

### References

[1]: https://docs.ragas.io/en/stable/ "Ragas — Introduction and systematic evaluation loops"
[2]: https://docs.ragas.io/en/stable/references/evaluate/ "Ragas — evaluate() reference"
[3]: https://aclanthology.org/2024.naacl-long.20/ "ARES: An Automated Evaluation Framework for Retrieval-Augmented Generation Systems, NAACL 2024"
[4]: https://github.com/stanford-futuredata/ARES "Stanford FutureData ARES repository and evaluation data contract"
[5]: https://github.com/beir-cellar/beir "BEIR — A heterogeneous benchmark for information retrieval"
[6]: https://aclanthology.org/2021.naacl-main.200/ "KILT: A Benchmark for Knowledge Intensive Language Tasks"
