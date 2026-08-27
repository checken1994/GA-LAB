# Triển khai SCP trên VPS Linux

Tài liệu này mô tả cách chạy SCP trên một VPS Ubuntu có thể duy trì độc lập với máy Windows cá nhân. Đây là **deployment recipe cho API/runtime candidate**, không phải lời chứng nhận production-ready.

## 1. Chọn VPS

Danh sách [free-for-dev](https://github.com/ripienaar/free-for-dev) là danh sách cộng đồng, không phải cam kết giá hoặc SLA của nhà cung cấp. Hai lựa chọn phù hợp nhất đã được đối chiếu với tài liệu chính thức:

| Lựa chọn | Phù hợp | Giới hạn quan trọng | Đánh giá cho SCP |
|---|---|---|---|
| [Oracle Cloud Always Free](https://www.oracle.com/cloud/free/) | VPS Linux nhỏ hoặc ARM có nhiều RAM hơn | Cần xác minh tài khoản; capacity theo region; tài nguyên idle có thể bị reclaim; không có SLA “miễn phí” cho hệ thống quan trọng | **Ứng viên tốt nhất cho proof-of-concept** nếu tạo được VM |
| [Google Cloud Free Tier](https://docs.cloud.google.com/free/docs/free-cloud-features) | API-only smoke test nhẹ | e2-micro khoảng 1 GB RAM; giới hạn region/băng thông; billing account; trial có thời hạn và resource có thể bị dừng/xóa nếu không chuyển tài khoản | **Ứng viên nhẹ**, không phù hợp chạy Ollama/local model |
| VPS đã có sẵn của người dùng | Triển khai thực tế nếu có SSH/root hoặc user sudo | Phải biết IP/hostname, hệ điều hành, tài nguyên, firewall, domain và chi phí | **Ưu tiên nếu đã có quyền hợp lệ** |

Với SCP, nên bắt đầu bằng **API loopback + Caddy TLS**, sau đó mới bật dashboard, scheduler, model bridge và external provider. Không đưa port `8002` ra Internet trực tiếp.

## 2. Kiến trúc an toàn

```text
Internet
   │
   ▼
Caddy :443  ── TLS, request limit, security headers
   │
   ▼
SCP API 127.0.0.1:8002  ── systemd, user scp, production guard
   │
   ├── local data/ and audit artifacts
   ├── optional scheduler 127.0.0.1:3030
   └── optional model service 127.0.0.1:11434
```

SCP mặc định chạy bằng `python3 -m scp` trên `127.0.0.1:8002`. Production guard yêu cầu `SCP_PRODUCTION_MODE=1`, `SCP_EGRESS_MODE=deny` hoặc `allowlist`, không bật bypass flags, và auth secret tối thiểu 16 ký tự. Khi bind public trực tiếp, guard còn yêu cầu `SCP_FORCE_HTTPS=1`; recipe này không bind public trực tiếp mà dùng Caddy.

## 3. Điều kiện cần trước khi triển khai

Cần có một VPS Ubuntu 22.04/24.04, SSH user có quyền `sudo`, IP hoặc hostname, dung lượng tối thiểu khoảng 20 GB cho API candidate, và domain nếu muốn HTTPS công khai. Cần quyết định rõ có chạy model trên VPS hay gọi model bên ngoài. Không nên đặt token vào Git, README, command line, screenshot hoặc log.

Hiện tại không có VPS/SSH credential nào được kết nối với task này. Vì vậy, việc tạo tài khoản cloud, xác minh danh tính/thẻ, lấy IP và đăng nhập SSH chưa được thực hiện.

## 4. Chuẩn bị VPS — operator chạy sau khi có quyền

Các lệnh dưới đây là hướng dẫn, chưa được chạy vào VPS trong quá trình chuẩn bị tài liệu.

```bash
sudo apt-get update
sudo apt-get install -y git python3 python3-venv python3-pip caddy ufw
sudo useradd --system --home /opt/scp --shell /usr/sbin/nologin scp || true
sudo install -d -o scp -g scp -m 0750 /opt/scp /etc/scp/secrets
sudo install -d -o scp -g scp -m 0750 /opt/scp/data /var/lib/scp /var/log/scp
```

Clone đúng commit đã kiểm chứng, không dùng source đang thay đổi:

```bash
sudo -u scp git clone https://github.com/checken1994/GA-LAB.git /opt/scp
sudo -u scp git -C /opt/scp checkout 2c1c61314cf0322557840942c9cb07c355731430
sudo -u scp python3 -m venv /opt/scp/.venv
sudo -u scp /opt/scp/.venv/bin/pip install --require-hashes -r /opt/scp/scp/requirements.txt
```

Nếu lock/hash policy hiện tại chưa hỗ trợ `--require-hashes`, phải dùng đúng dependency procedure của release gate và ghi rõ limitation; không tự bỏ pin để cài nhanh.

Tạo auth secret **trực tiếp trên VPS**, không gửi secret trong chat:

```bash
sudo sh -c 'umask 077; tr -dc "A-Za-z0-9" </dev/urandom | head -c 40 > /etc/scp/secrets/auth_password'
sudo chown root:scp /etc/scp/secrets/auth_password
sudo chmod 0640 /etc/scp/secrets/auth_password
```

Copy template và kiểm tra bằng mắt trước khi bật service:

```bash
sudo install -o root -g scp -m 0640 /opt/scp/deploy/vps/scp.env.example /etc/scp/scp.env
sudoedit /etc/scp/scp.env
```

Giữ `SCP_EGRESS_MODE=deny` cho lần smoke đầu tiên. Chỉ chuyển sang `allowlist` khi đã lập action inventory, domain allowlist, secret plan và test egress deny/allowlist.

## 5. Bật API bằng systemd

```bash
sudo install -o root -g root -m 0644 /opt/scp/deploy/vps/scp-api.service /etc/systemd/system/scp-api.service
sudo systemctl daemon-reload
sudo systemctl enable scp-api.service
sudo systemctl start scp-api.service
sudo systemctl is-active scp-api.service
curl --fail http://127.0.0.1:8002/health
```

Nếu health fail, dừng ở đây. Xem trạng thái và log đã redact bằng `systemctl status scp-api` và `journalctl -u scp-api --since "5 minutes ago"`; không đưa secret hoặc raw private log vào issue công khai.

## 6. Bật Caddy TLS

Sao chép [`Caddyfile.example`](Caddyfile.example) thành `/etc/caddy/Caddyfile`, thay `example.com` bằng domain thật, rồi kiểm tra:

```bash
sudo caddy validate --config /etc/caddy/Caddyfile
sudo systemctl reload caddy
curl --fail https://example.com/health
```

Mở firewall tối thiểu:

```bash
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw allow OpenSSH
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw enable
sudo ufw status verbose
```

Không mở `8002`, `3030` hoặc `11434` ra Internet. Nếu cần dashboard, triển khai nó như một service loopback riêng và chỉ proxy qua Caddy sau khi kiểm tra auth/rate-limit.

## 7. Smoke và release evidence

Tối thiểu cần lưu các metadata sau: commit, OS/Python version, service state, configured/actual ports, health response status, Caddy validation, firewall state, dependency install result và thời điểm. Không lưu secret values.

Các gate nên chạy trên VPS hoặc trong CI cùng commit:

```bash
cd /opt/scp
/opt/scp/.venv/bin/python -m compileall -q scp
/opt/scp/.venv/bin/python -m pytest -q
/opt/scp/.venv/bin/python run_reality_tests_portable.py
/opt/scp/.venv/bin/python tools/verify_snapshot_manifest.py reports/ROOT_SCP_SNAPSHOT_MANIFEST_20260826.json
curl --fail http://127.0.0.1:8002/health
```

Auth-negative probe cần kiểm tra endpoint không có token bị từ chối; không in response body chứa dữ liệu riêng tư. Một health `200` chỉ chứng minh liveness, không chứng minh golden task, RAG correctness, recovery, security hoàn chỉnh hoặc 24/7.

## 8. Rollback

Rollback phải giữ nguyên dữ liệu audit cần thiết và không dùng `git reset --hard` trên máy đang vận hành:

```bash
sudo systemctl stop scp-api.service
sudo -u scp git -C /opt/scp fetch origin
sudo -u scp git -C /opt/scp checkout <known-good-commit>
sudo -u scp /opt/scp/.venv/bin/pip install -r /opt/scp/scp/requirements.txt
sudo systemctl start scp-api.service
curl --fail http://127.0.0.1:8002/health
```

Nếu không chứng minh được trạng thái trước khi rollback hoặc có side effect đang dở, chuyển sang `RECONCILING`/`HUMAN_REVIEW`; không retry mù.

## 9. Giới hạn của free VPS

Oracle Always Free có thể phù hợp cho API candidate và một số service nhẹ, nhưng capacity, reclaim và account terms làm cho nó không tương đương SLA production. Google e2-micro quá nhỏ cho full SCP + dashboard + Ollama. Chạy local Ollama trên VPS free có thể thiếu RAM/CPU; gọi provider ngoài thì phải mở egress có allowlist và quản lý secret đúng cách.

Do đó, kết quả đầu tiên trên VPS nên được gọi là **VPS deployment candidate / `CANDIDATE_NOT_PROVEN`**, không phải production-ready. Cần thêm backup/restore, monitoring, rate limit, domain/TLS validation, chaos/recovery test, load/endurance test và independent security review trước khi dùng cho dữ liệu hoặc side effect quan trọng.

## References

[1]: https://github.com/ripienaar/free-for-dev "Community free developer services list"
[2]: https://www.oracle.com/cloud/free/ "Oracle Cloud Free Tier"
[3]: https://docs.oracle.com/iaas/Content/FreeTier/freetier_topic-Always_Free_Resources.htm "Oracle Always Free Resources"
[4]: https://docs.cloud.google.com/free/docs/free-cloud-features "Google Cloud Free Program and Free Tier"
[5]: https://github.com/checken1994/GA-LAB/blob/main/scp/__main__.py "SCP Linux entrypoint"
[6]: https://github.com/checken1994/GA-LAB/blob/main/scp/security/production_guard.py "SCP production guard"
