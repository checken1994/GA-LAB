# SCP codegraph, 429, RAG và proof gaps — V2

**Snapshot code:** `dd6df2422302bdeb7c945a597a8c68f40b5f7bb1` trên canonical `main`; phần code và artifact này đã được kiểm tra bằng main CI `32952487961`. Báo cáo này dùng nguyên tắc **evidence maturity**, không biến code tồn tại hoặc test pass thành tuyên bố production tuyệt đối.

## 1. Codegraph hiện tại

Codegraph được tạo bằng AST từ thư mục `scp/`. Graph chỉ ghi cạnh import nội bộ đã resolve; lời gọi động, plugin, subprocess và HTTP call không được suy ra nếu không có bằng chứng tĩnh. Snapshot hiện có **453 module/file nodes**, **852 import edges**, **53 focused nodes** và **230 focused edges**. Bảy phân khúc lớn nhất là `autofix` 72, `data_sources` 68, `core` 59, `runtime` 56, `meta` 51, `security` 35 và `api` 25.

| Artifact | Giá trị |
|---|---|
| Commit codegraph | `10296595f5cb24dce9cb3127334fb879199a91d1` |
| AST nodes | 453 |
| Internal import edges | 852 |
| Focused nodes / edges | 53 / 230 |
| Generator | `tools/build_codegraph_current.py` |
| Full graph | `reports/codegraph_20260826/codegraph.json`, `.csv`, `.mmd` |
| Focused graph | `reports/codegraph_20260826/codegraph_focused.mmd` và `.png` |

Graph cho thấy nhánh `/ask` đi qua `LLMGateway/Judge` và `AskKernelAdapter` vào `TaskKernel`; nhánh Hands hiện đã đi qua `TaskKernelHandsBridge` tại route `/v3/hands/execute` cho các action có `mutates_state=True`. Graph vẫn không tự chứng minh mọi nhánh đã chạy end-to-end.

## 2. Hai loại HTTP 429

**429 ở SCP HTTP boundary** xảy ra trước khi model được gọi. `/ask` chạy `DoSProtectionEngine.check_request()` trước pipeline Judge/Gateway. Minute/hour limiter và circuit breaker có thể trả 429; trong trường hợp đó chưa có model request nên đổi model là sai tầng. Response hiện truyền `Retry-After` để client backoff.

**429/402 từ OpenRouter** xảy ra sau khi provider đã nhận request. Ở tầng này `OpenRouterProvider.chat()` có fallback theo chuỗi paid model → task-specific free model → `openrouter/free`; reproduction có kiểm soát đã chứng minh paid-429 chuyển được sang `openai/gpt-oss-20b:free`. Đây là provider fallback, không phải retry của HTTP DoS guard.

| Nguồn lỗi | Model đã được gọi? | Hành vi đúng |
|---|---:|---|
| SCP minute/hour/circuit guard | Không | Trả 429, giữ `Retry-After`, client backoff và giữ idempotency key |
| OpenRouter provider quota/rate limit | Có | Provider fallback theo policy, ghi provider outcome |
| Hands driver result không rõ | Không áp dụng | Không retry mù; chuyển TaskKernel sang `UNKNOWN`, cần reconcile |

## 3. RAG và “dataset chính thức”

Ragas là thư viện và API đánh giá; `evaluate()` nhận dataset, metrics và tùy chọn LLM/embeddings [1] [2]. ARES là framework/judge pipeline cần dữ liệu human-annotated, few-shot và unlabeled theo contract của nó [3] [4]. BEIR/KILT là các benchmark/corpus/task riêng, có qrels hoặc provenance riêng [5] [6]. Không có một “official RAG dataset” có thể tự biết gold chunk và gold answer cho 1.000 câu tiếng Việt hiện tại của SCP.

Vì vậy phải tách hai lane. **External lane** chạy BEIR/KILT hoặc benchmark công khai giữ nguyên corpus, split, qrels và metric. **In-domain lane** của SCP phải có canonical URL, quote nằm trong source, gold chunk IDs, gold answer được review độc lập, freshness và provenance. Artifact 50 dòng hiện tại còn là candidate; không được gọi là human-verified Gold, official Ragas data hay ARES data.

## 4. Proof mới đã hoàn thành

### 4.1 Capability epoch/revoke

Hands có capability authority bền vững bằng JSON state, revoke và restore đều tăng epoch; token cũ bị stale kể cả sau restore. Các check nằm ở policy gate và ngay trước dispatch. API status/revoke/restore đã có integration tests và main CI trước đó.

### 4.2 Safe golden task

`tests/test_golden_task_chain_contract.py` chứng minh safe chain planner → policy → tool → postcondition → audit artifact với fake controller, không tuyên bố PC side-effect thật. Đây là **integration proof**, chưa phải chứng minh mọi connector thực.

### 4.3 TaskKernel–Hands side-effect bridge

`TaskKernelHandsBridge` đã được nối vào production-facing `/v3/hands/execute` và planner executor. Action mutating có task, lease, idempotency claim và checkpoint trước driver call. Kết quả verified được commit với verifier/evidence ref. Kết quả mutating không verified hoặc exception sau dispatch được ghi `UNKNOWN` với provider/driver request identity; retry chỉ được phép sau `POST /v3/hands/reconcile`.

Runtime proof trên **`127.0.0.1:8002`** đã quan sát được: managed process start → `COMPLETED`; stop process owned → `COMPLETED`; stop non-owned PID → `UNKNOWN`, `requiresRecovery=true`, `safeToRetry=false`; reconcile `NOT_APPLIED` → `QUEUED`. Service sau đó đã dừng và port 8002 được xác nhận free. Artifact sanitized nằm tại `reports/runtime_proof_20260826_hands_bridge.json`.

Giới hạn: đây là bounded local managed-process path, chưa chứng minh mọi connector/provider bên ngoài và không thể retroactively cancel một side-effect đã chạy.

## 5. Ma trận trạng thái hiện tại

| Capability | Trạng thái evidence | Khoảng trống còn lại |
|---|---|---|
| API health và DoS 429 boundary | `RUNTIME_PROVEN` trong profile 8002 | Chưa chứng minh client benchmark tự backoff hoàn chỉnh |
| OpenRouter 429 fallback | `INTEGRATION_PROVEN` | Chưa phải mọi provider/network failure |
| Codegraph | `RELEASE_PROVEN` | Graph tĩnh không chứng minh runtime semantics |
| TaskKernel recovery/reconcile contract | `INTEGRATION_PROVEN` | Cần tiếp tục process/connector diversity |
| Hands capability revoke | `INTEGRATION_PROVEN` | Chưa phải distributed cancellation |
| Safe planner chain | `INTEGRATION_PROVEN` | Fake/safe driver, chưa là mọi side-effect |
| Local Hands side-effect → UNKNOWN/reconcile | `RUNTIME_PROVEN` bounded | Chưa bao phủ connector bên ngoài |
| Queue fairness/quota/deadline | `INTEGRATION_PROVEN` | Chưa phải multi-process/multi-host chaos proof |
| Provider timeout → task-specific fallback | `INTEGRATION_PROVEN` | Chưa phải live provider outage hoặc distributed recovery |
| 50 reviewed factual Gold | `BLOCKED` | Human/independent review còn 0/50 |
| Official Ragas score | `BLOCKED` | Chưa có verified rows và provider/embedding profile hợp lệ |
| ARES score | `BLOCKED` | Thiếu formal precondition sets/package |
| Full 1.000-question factual RAG | `BLOCKED` | Candidate history còn empty answer/context/request errors |

Theo feature matrix 15 mục, hiện có **3 runtime-proven, 7 integration-proven, 1 release-proven và 4 blocked**; không còn mục `UNPROVEN` trong 15 capability này, nhưng 4 mục RAG/ARES vẫn bị chặn bởi precondition dữ liệu. Tỷ lệ có release/integration/runtime evidence là **11/15 = 73,3%**; runtime tuyệt đối là **3/15 = 20,0%**; weighted evidence score là **60,0%**. Đây không phải RAG accuracy, không phải benchmark score và không phải tỷ lệ code đã hoàn thiện.

## 6. Việc chưa được phép tuyên bố

Chưa được tuyên bố SCP là Agent OS production-safe tuyệt đối, chưa được tuyên bố toàn bộ connector có reconcile, chưa được tuyên bố 1.000 câu đạt Real RAG, chưa được tuyên bố có Gold 50 được human review, và chưa được tuyên bố có điểm Ragas/ARES chính thức. Những kết luận đó cần evidence mới, độc lập và có provenance riêng.

## References

[1]: https://docs.ragas.io/en/stable/ "Ragas — Introduction and systematic evaluation loops"
[2]: https://docs.ragas.io/en/stable/references/evaluate/ "Ragas — evaluate() reference"
[3]: https://aclanthology.org/2024.naacl-long.20/ "ARES: An Automated Evaluation Framework for Retrieval-Augmented Generation Systems"
[4]: https://github.com/stanford-futuredata/ARES "Stanford FutureData ARES repository and data contract"
[5]: https://github.com/beir-cellar/beir "BEIR official repository"
[6]: https://aclanthology.org/2021.naacl-main.200/ "KILT benchmark paper"
