# Đánh giá độc lập các đề xuất “Top 1%” cho SCP

## Nguyên tắc đánh giá

Một đề xuất không trở thành remediation chỉ vì công nghệ đó phổ biến. Nó chỉ được xếp ưu tiên khi giải đúng một lỗi đã quan sát được, có tiêu chí pass/fail, rollback và không làm rộng quyền của SCP.

## Nguồn đã đối chiếu

Tài liệu [MDN về Server-Sent Events](https://developer.mozilla.org/en-US/docs/Web/API/Server-sent_events) mô tả SSE là kết nối để **server đẩy event/data một chiều về web page**. Tài liệu [Docker Overview](https://docs.docker.com/get-started/docker-overview/) mô tả container là môi trường chạy đóng gói, cô lập tương đối và nhất quán giữa máy.

| Đề xuất | Nó thực sự giải gì | Nó không giải gì | Quyết định hiện tại |
|---|---|---|---|
| SSE streaming | Giảm polling web, hiển thị job/ledger/pipeline gần thời gian thực | Không sửa Ask semantic, verifier, policy handoff, AutoFix hay Supervisor | **Backlog UX**, không phải remediation P0 |
| Docker/Linux | Reproducible test/deploy cho backend/scheduler và benchmark cô lập | Không thay thế Electron/desktop Windows, không tự sửa quyền/ledger/policy | **Cần cho benchmark/cloud sau này**, chưa ép production desktop chạy Docker |

## SWE-bench: dùng để đo AutoFix, không phải chứng nhận toàn hệ thống

Trang [SWE-bench](https://www.swebench.com/SWE-bench/) xác định benchmark này giao cho model một codebase và GitHub issue để tạo patch; harness dùng Docker nhằm tái lập evaluation. Vì vậy, nó phù hợp để đo phần **AutoFix sửa lỗi phần mềm** của SCP, không đo camera/mic, policy handoff, egress, chống prompt injection hay supervisor Windows.

Quyết định: **benchmark tách biệt trong VM/sandbox, ưu tiên sau P0.** Trước khi chạy cần một adapter không cho model viết vào repo production, bộ commit pin cố định, budget disk/RAM đủ, và metric tách biệt: patch apply rate, test pass rate, regression rate, timeout rate. Không lấy điểm SWE-bench để tuyên bố SCP có thể tự sửa mọi thứ.

## Causal graph / DoWhy: nghiên cứu dài hạn, chưa là remediation

Theo [DoWhy documentation](https://www.pywhy.org/dowhy/), causal inference bắt đầu bằng causal model và các **assumption nhận diện được nêu rõ**, tách identification khỏi estimation, rồi có sensitivity/robustness để falsify graph. SCP hiện chưa có telemetry production đủ sạch cho các biến nguyên nhân-kết quả như “thay đổi policy nào gây cải thiện/tệ đi trong loại task nào”.

Quyết định: **không cài DoWhy vào runtime hiện tại.** Trước hết phải có event schema bất biến, terminal state cho learning/evolution, experiment/control cohort, timestamp chính xác, và dữ liệu rollback. Sau đó thử offline trên bản sao ledger; kết quả chỉ là hypothesis cho review người, không tự bật policy hay AutoFix.

## Thứ tự ưu tiên thực tế

1. Đóng blocker evidence hiện tại: policy handoff production và AutoFix candidate → patch → regression-free.
2. Lập profile security/chaos/soak test tách biệt, không dùng benchmark thay thế.
3. Chạy SWE-bench trong sandbox nếu mục tiêu là công nhận năng lực AutoFix code.
4. Docker hóa **benchmark/CI** trước; đánh giá Docker runtime production sau khi desktop contract rõ.
5. SSE khi polling relay trở thành điểm nghẽn quan sát được.
6. Causal graph chỉ sau khi ledger có dữ liệu terminal và thí nghiệm đủ chất lượng.

## Tiêu chí để làm SSE sau này

Chỉ bắt đầu sau khi có ít nhất 20 job relay liên tiếp với DB/audit đúng. Contract phải có `job_id`, event sequence tăng dần, reconnect replay và fallback polling. Nếu SSE lỗi, trang Ask/Pipeline vẫn phải hoạt động qua polling hiện có.

## Tiêu chí để làm Docker sau này

Docker chỉ chạy trong VM/sandbox hoặc CI trước. Image phải pin dependency/lockfile, không copy `.env`, không mount dữ liệu production ghi được và không publish `8000/11434`. Pass khi cùng một profile test tạo kết quả giống nhau ở hai runner tách biệt; rollback là bỏ image/compose, không thay desktop runtime.
