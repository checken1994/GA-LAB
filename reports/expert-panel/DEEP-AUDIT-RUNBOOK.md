# DEEP-AUDIT RUNBOOK — 4 vòng chuẩn SCP (đã chạy thật trong campaign 2026-09-10→12)

> Copy-paste chạy được. Binding: scp-dna + skill domain; worker ≠ verifier; PIPESTATUS discipline; commit-per-group.

## Vòng 1 — AUDIT TĨNH (static)

```bash
# Mimosa sealed deep scan (plugin MCP: security_scan_start / security_scan_status)
#   depth: "deep" — sản phẩm: scanDir + findings.json + seal.json (sha256)
# Shape rules (rg) — các pattern đã học:
rg -n "requests\.get\(|requests\.post\(|httpx\.get\(|urllib\.request\.urlopen\(|verify=False|execute\(f\"|yaml\.load\(|pickle\.loads\(|shell=True|eval\(|exec\(" scp/ --include="*.py"
# AST / compile:
python -m py_compile <changed-files>
# Contract gates:
python tools/verify_scp_test_skill_contract.py
python tools/scp_release_verdict.py
# Git tĩnh:
git show --stat <pin>            # scope lock
git diff HEAD -- tests/          # anti-weakening
```
Giới hạn: static-only; `runStatus: inconclusive` → HIGH=0 chỉ đúng trong phạm vi file quét được.

## Vòng 2 — CHẠY THỰC TẾ (runtime)

```bash
# Build bind SHA (bắt buộc --build-arg; env không ăn):
docker compose build --build-arg SCP_GIT_SHA=$(git rev-parse HEAD) scp-api
docker compose up -d scp-api --force-recreate
curl -s http://127.0.0.1:8000/health | python -c "import json,sys; d=json.load(sys.stdin); print(d['service_identity']['commit'])"  # phải == pin
curl -s http://127.0.0.1:8000/readiness

# Probe HTTP thật: negative-first (401/403 = contract) → golden path → adversarial (SSRF target, burst, 429)
# Instance tạm full-profile cho route ngoài profile=core (port 8001..8012, teardown sau)

# D1 pytest — PIPESTATUS discipline:
python -m pytest tests/TXX/... -q 2>&1 | tail -2; echo EXIT=${PIPESTATUS[0]}
# WS/SSE thật: TestClient websocket_connect / httpx stream — assert frame-by-frame
# Kernel thật: TaskKernel tmp SQLite + sqlite3.set_trace_callback (SQL binding observed)
```

## Vòng 3 — XÁC NHẬN TRẠNG THÁI

```bash
# 1. Delta Mimosa: scan lại → so scanId cũ/mới (new/persistent/resolved) — claim "đã fix" phải hiện RESOLVED
# 2. State machine: RestartCount=0; log grep 0 Traceback / 0 "database is locked" / 0 bypass
# 3. Consistency máy (closure records): JSON valid; pin 40-hex; git cat-file -e <pin>^{commit}; evidence tồn tại; STATUS-LEDGER khớp
# 4. Verifier agent ĐỘC LẬP (worker ≠ verifier): evidence vs claim + test ngược nguyên lý (DNA #22/#26)
# 5. Determinism: pytest ×2, probe ×2
```

## Vòng 4 — CHỐT "TẠI SAO" (DNA #1 — hỏi Tại sao 3–5 lần)

- Mọi agent report → orchestrator hỏi **Tại sao** trước khi chấp nhận (owner mandate)
- Mỗi product fail trong closure record có mục **root_cause** bắt buộc — chain đến root thật
  (VD: M12 "5.356 plans stuck" → UPDATE..ORDER BY..LIMIT sai trên SQLite → fail-silently → 13/16 test pass-trắng → test sinh template không có contract thật)
- Mỗi verdict mang `falsification_status` — tự falsify claim của chính mình (VD M13: "egress deny chặn internet" → FALSIFIED)
- Kết thúc bằng known_gaps tường minh + open questions — cấm chốt "xong" trơn (DNA #22/#23)

## Quy tắc xuyên vòng
- Skill binding falsifiable (SHA256 SKILL.md vào mọi report) — khai suông = vô giá trị
- Worker ≠ Verifier; HIGH chỉ tin khi same-SHA; gate: HIGH chặn, medium giải thích, low ghi nhận
- commit-per-group nhỏ; `git diff --cached` phải khớp những gì gate vừa quét trước khi commit
