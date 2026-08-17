# Reality check: Đánh giá Gemini về SCP DNA

## Kết luận ngắn

Đánh giá Gemini có ích như một bản đồ chỉ dẫn: nó đã nhận ra nhiều module thật trong repository và nêu đúng một số giới hạn kỹ thuật. Tuy nhiên, nó đã trộn ba loại bằng chứng khác nhau: **code có trong repo**, **test/CI pass** và **hệ thống chạy thật trên PC**. Ba loại này không thay thế nhau.

> Verdict tổng thể: **PARTIALLY_SUPPORTED**. Không có căn cứ để gọi SCP “rất hoàn thiện”, “vượt trội” hay production-ready chỉ từ các file được đọc.

## Evidence đã đối chiếu

| Claim từ Gemini | Kết quả đối chiếu | Mức evidence | Giải thích ngắn |
|---|---|---|---|
| AutoFix có `PROTECTED_PATHS` chặn sửa phần quyền/bảo mật | Có | A — static | `scp/autofix/runner_phases/ast_scan.py` chứa danh sách này; bản hiện tại có 15 path, không phải 12 như trích dẫn. Chưa chứng minh mọi đường sửa file đều đi qua gate này. |
| Falsification/WHY engine tồn tại | Có file/module | A — static | Module tồn tại; chưa đủ để kết luận causal reasoning, chống ảo giác hay hiệu quả hơn Reflexion/DoWhy. |
| Hands Planner có lease, fencing, journal hash/recovery | Có bản vá và reality probe trước đó | B–C, phạm vi hẹp | Đã kiểm chứng contract lease fencing và journal integrity trong workload test; chưa chứng minh an toàn với mọi browser/OS action. |
| CI/reality test chạy | Có | B — integration | GitHub Release Gate gần nhất `e6f676b` success. Đây là PASS trong scope CI, không phải production proof. |
| Bun LLM Bridge chạy port 11434 | Sai với runtime hiện tại | CONTRADICTED | Commit `863264e` đã bỏ llm-bridge khỏi Supervisor vì Ollama thật giữ port 11434. Runtime SCP hiện dùng Ollama external, `SCP_LLM_PROVIDER_MODE=ollama_only`. |
| Stream=true là buffered single chunk | Có | A — static | `mini-services/llm-bridge/index.ts` ghi `X-Stream-Mode: buffered-single-chunk`. Nhưng bridge này không còn nằm trong chuỗi Supervisor hiện tại. |
| 5 production flags là hàng rào runtime đã bật | Chỉ đúng một phần | B — runtime config | Supervisor ép các child flag về `0`, nên không được coi các flags này đang "bật để bảo vệ". File `.env` ngoài repo còn flags cần xử lý; child-safe runtime khác root env. |
| FastLearning/Durable KB đã có 6 lessons, 4 patterns và tiến hóa bền vững | Không đủ evidence | INSUFFICIENT | Runtime audit cho thấy FastLearning có 1 cycle thật lưu 3 fact; chưa chứng minh lesson được promote thành active policy. Evolution ledger 52/52 chỉ `STARTING`, không có terminal success. |
| 11 real antibodies hoạt động và giảm 100% CPU | Không đủ evidence | INSUFFICIENT | Code kể về antibodies không chứng minh tất cả được gọi trên workload thật, accuracy, coverage hay % CPU. Các tên hàm Gemini nêu không khớp trực tiếp khi tìm bằng tên chính xác. |
| 50+ connectors có reputation scoring | Có thể có catalog code | A — static | Chưa chứng minh API keys, endpoint, freshness, error handling hoặc connector nào chạy thành công production. |
| SCP vượt LangChain/AutoGen/SWE-agent/Devin | Không thể kết luận | UNKNOWN | Không có benchmark chung, workload cùng điều kiện, số đo cost/latency/success/security, hay external evaluation. |

## Những điểm Gemini nhận ra đúng

Gemini đúng khi nêu ba hướng cải thiện: streaming thật thay vì buffer, chia nhỏ các file rất lớn, và chuẩn hóa đa nền tảng/packaging. Nhưng ưu tiên của SCP không nên bắt đầu bằng Docker hay causal math graph.

Lỗ hổng bằng chứng lớn nhất hiện nay nằm ở chuỗi: **Internet learning → lesson → policy candidate → validate → active policy → tác động được đo lại**. Chuỗi này vẫn chưa có proof end-to-end. V100 crawler có object nhưng runtime status từng là `total_crawls=0`; local/news learning chưa tự chạy định kỳ; Evolution ledger thiếu trạng thái kết thúc; endpoint FastLearning status từng không khớp ledger.

## Thứ tự cần làm thực tế

| Ưu tiên | Việc cần làm | Reality test cần có | Rollback |
|---:|---|---|---|
| P0 | Nối observability: status API đọc đúng singleton worker/ledger | Một FastLearning run cho cùng `run_id` hiện giống nhau ở log, DB, API và dashboard | Chỉ đổi projection/read path, backup DB |
| P0 | Đóng evolution lifecycle | Mỗi `STARTING` có terminal `SUCCESS`/`FAILED`/`TIMEOUT` kèm reason và artifact hash | Feature flag `SCP_EVOLUTION_AUTO=0` giữ mặc định |
| P1 | Prove policy handoff staging | Lesson staging được validate, candidate hash, promote có approval, active policy tác động đúng test mới | Atomic backup policy và rollback hash |
| P1 | Benchmark external truth | Chạy sandbox tách biệt AI Agent Security/Secure Coding workload có score, time, cost và artifact | Sandbox disposable, không credentials |
| P2 | SSE thật và POSIX/Docker | Client nhận incremental tokens; Linux integration run có process cleanup proof | Giữ buffered mode và desktop Windows release làm fallback |

## Câu hỏi còn mở

1. Có bao nhiêu AutoFix candidate thực sự đi tới patch được áp dụng và không tạo regression sau đó?
2. Có lesson/pattern nào đã được external truth tái xác thực sau khi lưu không?
3. Có policy nào đang active trên PC do learning tạo ra không?
4. Có connector Internet nào có SLA, key hợp lệ và evidence fresh ngoài các crawl đang có không?

## Cập nhật đối chiếu runtime — 17/08/2026

Đối chiếu lại trên PC Windows đã cho kết quả dưới đây. Đây là evidence mới hơn phần nhận xét ban đầu, nhưng vẫn không biến các câu hỏi mở thành PASS.

| Câu hỏi Gemini | Quan sát mới | Verdict cập nhật |
|---|---|---|
| AutoFix candidate → patch → không regression | Không có `data/autofix_runs.jsonl` tại thời điểm kiểm tra, nên không có chuỗi artifact để đếm hoặc kiểm chứng. | **BLOCKED** |
| Lesson/pattern được external truth xác thực lại | Không có provenance ledger nào được quan sát cho external re-validation sau khi lesson được lưu. | **BLOCKED** |
| Policy learning đang active | `data/active_policies.json` không tồn tại trên PC lúc kiểm tra. | **VERIFIED: không có active policy** |
| Internet connector có SLA/evidence fresh | Không có manifest SLA, evidence freshness hoặc record gọi connector đã redact trong phạm vi audit. | **BLOCKED** |

Hai runner hiện có đã được chạy lại sau patch telemetry: `python -m pytest -q` cho **101 passed, 2 warnings** và `tests/run_reality_tests_portable.py` cho **74/74 pass, 0 fail, 0 timeout**. Cả bốn service dashboard, scheduler, backend và Ollama đều phản hồi HTTP 200 trên route phù hợp vào thời điểm kiểm tra.

Kết quả này nâng độ tin cậy của các contract/regression trong phạm vi suite, nhưng không chứng minh AutoFix phức tạp, external learning hoặc policy handoff. Patch lifecycle mới cũng chỉ chứng minh trường hợp Evolution bị tắt ghi terminal `DISABLED`, không chứng minh Evolution production đang chạy.

Có một giới hạn provenance cần giữ rõ: GitHub `main` đã có patch telemetry `3028fb2` và evidence report `a927a0d`; PC thật có logic tương đương đã được reality-test nhưng local repository còn history cũ, 76 file dirty và local commit riêng. Không thực hiện `pull`, `rebase` hay `reset --hard` tự động vì có nguy cơ đè thay đổi local chưa phân loại.

## Kết luận

Gemini đã mô tả **tiềm năng kiến trúc** khá tốt, nhưng đánh giá đã đi quá xa ở các từ như “rất hoàn thiện”, “vượt trội” và “có thể duy trì tri thức không suy thoái”. SCP có các safety primitive đáng giá; phần còn thiếu là evidence end-to-end, observability thống nhất và benchmark độc lập. Theo SCP DNA: **Reality over Model; PASS within scope không phải TRUE.**
