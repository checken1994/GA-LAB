# SCP DNA — Self-Correcting Pipeline

SCP DNA là một hệ thống **Self-Correcting Pipeline**: kiểm tra bằng evidence, hỏi “Tại sao?”, sửa có kiểm soát, xác minh, phản tư và lưu learning state durable. Nguyên tắc trung tâm là **DNA #22: PASS không đồng nghĩa TRUE**.

Repository này chứa source code SCP, desktop Control Center, dashboard, sidecar services, tests và tài liệu audit. **Secret `.env` thật và runtime data không được commit lên GitHub.** Chỉ `.env.example` và các fixture/test data an toàn mới thuộc repository.

## Trạng thái hiện tại

- **HEAD:** R39 — `17f340283b7e8f314777f30b6a1fddfd1145e5ec`
- **Backend:** Python/FastAPI, mặc định loopback `127.0.0.1:8000`
- **Desktop:** Electron 43.4.0, electron-builder 26.15.3, app version 1.6.0
- **Dashboard:** Next.js service, mặc định `127.0.0.1:3000`
- **LLM Bridge:** Bun/TypeScript, Ollama-compatible contract tại `127.0.0.1:11434`, chuyển upstream tới OpenRouter và fallback provider khi được cấu hình
- **Loop Scheduler:** Bun/TypeScript, mặc định `127.0.0.1:3030`
- **Evidence gần nhất trên PC thật:** 55 pytest passed; 73/73 portable reality passed; packaged safe auth `200/401/401/200`
- **Evolution R39:** `bugs_found=1`, `bugs_fixed=1`, `verified=1`, `stored=1`; durable KB có 6 lessons và 4 evolved patterns

Đây là trạng thái **hardened production-candidate**, không phải tuyên bố hệ thống đã chứng minh mọi loại tấn công hoặc mọi môi trường triển khai.

## Cài đặt và chạy trên Windows

### Cài đặt lần đầu

Double-click `install-scp.bat`. Script tạo Python virtual environment, cài Python dependencies, cài sidecar/dashboard dependencies và tạo thư mục runtime cần thiết.

### Cấu hình

Tạo `.env` local từ `.env.example`, sau đó đặt secrets qua môi trường hoặc secret files. Không commit `.env` thật. Trước khi chạy production, năm dangerous flags phải bằng `0`:

```text
SCP_DEV_MODE=0
SCP_SKIP_STARTUP_GATE=0
SCP_AUTO_APPROVE_TIER3=0
SCP_TIER3_ALLOW_RELAXATION=0
SCP_TIER3_ALLOW_BAREEXCEPTPASS=0
```

### Chạy và dừng

Double-click `start-scp.bat` để khởi động stack hoặc `launch-scp-desktop.bat` để mở Electron Control Center. Dùng `stop-scp.bat` để dừng stack.

## Ports và contracts

| Thành phần | Port | Contract |
|---|---:|---|
| Dashboard | 3000 | HTTP UI |
| Python API | 8000 | FastAPI, health/auth/audit/evolution routes |
| LLM Bridge | 11434 | Ollama-compatible `/api/tags`, `/api/chat`, `/api/generate` |
| Loop Scheduler | 3030 | Closed-loop scheduler/admin surface |

Các service mặc định bind loopback. LLM Bridge là façade tương thích Ollama, không nên được hiểu là Ollama process nguyên bản; upstream provider phải được cấu hình và kiểm chứng riêng.

## Repository map

```text
.
├── scp/                         # Python backend, security, WHY, AutoFix, learning
├── dashboard/                   # Next.js dashboard
├── mini-services/
│   ├── llm-bridge/              # Bun Ollama-compatible provider bridge
│   └── loop-scheduler/           # Bun bounded scheduler
├── desktop/                     # Electron shell, preload, packaging/runtime
├── tests/                       # pytest, contract tests, reality tests
├── benchmark/                   # benchmark inputs and analysis assets
├── data/                        # local runtime output; ignored from release
├── docs/                        # audit, remediation, history and architecture
├── scripts/                     # operational/maintenance helpers
├── tools/                       # diagnostic and integration helpers
├── .env.example                 # safe configuration template only
└── README.md                    # this entry guide
```

## Test

```powershell
.\scp\venv\Scripts\python.exe -m pytest -q
.\scp\venv\Scripts\python.exe tests\run_reality_tests_portable.py
```

The portable runner writes runtime output to `data/reality-tests-results.json`. Test output and runtime ledgers are not release evidence by themselves; interpret them with the corresponding audit manifest and scope.

## Tài liệu chính

- [Lịch sử xây dựng SCP](docs/SCP_BUILD_HISTORY.md)
- [Kiến trúc hệ thống hiện tại](docs/SCP_ARCHITECTURE_CURRENT.md)
- [Continuity archive](docs/SCP_CAU_CHUYEN_GA_TAI_SAO_CONTINUITY_ARCHIVE.md)
- [Public release guide](docs/PUBLIC_RELEASE_GUIDE.md)
- [Worklog](docs/WORKLOG.md)

## Security và release hygiene

Không commit các file sau: `.env`, provider keys, auth/password/token secrets, SQLite runtime databases, JSONL ledgers, generated logs, private backups và packaged private artifacts. Khi thay đổi production boundary, phải có backup, rollback path, reality test và manifest hash.

Installer Windows cần được rebuild từ runtime backend hash-pinned, kiểm tra Authenticode nếu có signing certificate và kiểm tra cài đặt trên môi trường độc lập trước khi gọi là production-ready.

## License / project context

SCP DNA được phát triển trong GA LAB với mục tiêu xây dựng một hệ thống tự kiểm chứng, tự sửa có kiểm soát và có khả năng học từ evidence nhưng không trao quyền quyết định cuối cùng cho sự đồng thuận của model.
