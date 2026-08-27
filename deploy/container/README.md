# SCP container candidate

Đây là **candidate tái lập cục bộ cho API**, không phải bằng chứng SCP đã triển khai production hay VPS. Sandbox hiện tại không có Docker/Podman nên chưa thể chứng minh build và runtime container end-to-end ở đây.

## Cách chạy an toàn

Từ thư mục gốc repository:

```bash
docker compose -f compose.yml build scp-api
docker compose -f compose.yml up -d scp-api
curl -i http://127.0.0.1:8002/health
curl -i http://127.0.0.1:8002/ready
docker compose -f compose.yml down
```

Mặc định chỉ host loopback `127.0.0.1` được publish. API chạy bằng user không phải root, root filesystem read-only, `/tmp` là tmpfs với `noexec,nosuid,nodev`, toàn bộ Linux capabilities bị drop, và `no-new-privileges` được bật. Dữ liệu runtime nằm trong named volume `scp-data`; source code, `.env`, token, cookie, database và benchmark artifact bị loại khỏi Docker build context bởi `.dockerignore`.

Compose mặc định dùng **isolated local mode**, egress deny, và không khởi động scheduler. Đây là lựa chọn để kiểm tra liveness/readiness mà không tạo audit hoặc mutation ngoài ý muốn. Vì local mode không phải production mode, người vận hành không được suy diễn từ nó rằng auth production, TLS gateway, provider fallback hoặc uptime đã được chứng minh.

## Secret và provider

Không đặt password, bearer token, API key hoặc cookie trong `Dockerfile`, `compose.yml`, image layer hay git. Nếu cần production safety guard, truyền secret bằng Docker secret hoặc secret manager của môi trường triển khai; không commit file secret. `SCP_AUTH_PASSWORD` phải dài tối thiểu 16 ký tự khi `SCP_PRODUCTION_MODE=1`. Khi bind container trên `0.0.0.0`, phải có TLS gateway và cấu hình `SCP_FORCE_HTTPS=1`; compose chỉ publish loopback để giảm bề mặt phơi ra.

Ollama không được bundle trong image. Có thể trỏ `OLLAMA_HOST` tới một bridge đã được operator kiểm soát, nhưng request live tới provider, chất lượng fallback, RAG Gold/Ragas/ARES và uptime dài ngày vẫn là bằng chứng riêng, không được gọi là PASS từ việc image build thành công.

## Scheduler profile

Scheduler chỉ chạy khi bật rõ profile:

```bash
docker compose -f compose.yml --profile loop up -d
```

Profile này vẫn để `SCP_AUTOFIX_MODE=observe` và deterministic-only, vì scheduler có thể gọi `POST /v105/autofix/run-audit`. Việc image khởi động được không đồng nghĩa audit đã an toàn để tự mutation. Hãy kiểm tra log, readiness và policy trước khi dùng một môi trường khác.

## Readiness contract

`/health` là **liveness**: process trả lời được. `/ready` và `/readiness` là **readiness**: chỉ trả HTTP 200 sau khi background judge đã khởi tạo thành công. HTTP 503 ở readiness là trạng thái chưa được promotion, không phải bằng chứng process đã chết.

## Validation status

Đã có static contract tests trong `tests/test_container_contract.py` để ngăn các lỗi dễ thấy như chạy root, copy `.env`, bind host không hạn chế, thiếu healthcheck hoặc bật scheduler mặc định. Build Docker thật, vulnerability scan của image, network policy thực tế và soak test phải chạy trong một host có Docker với log/provenance độc lập.
