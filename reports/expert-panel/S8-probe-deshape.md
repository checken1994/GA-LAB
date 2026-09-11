# S8 — De-shape 6 HIGH Mimosa trong 4 probe script (micro)

- Agent: S8 (micro) — nhánh `audit/runtime-guard-AUDIT-20260909`
- Scan tham chiếu: scan-2026-09-11T15-22-16.575Z (L3 gate, 6 HIGH)
- Skill binding: `scp-dna` — SHA256(`.agents/skills/scp-dna/SKILL.md`) =
  `4aada0be4873598dc50c3a7f38d90151429bb5263c511a838ed1cdcb4d594d10`

## Findings xử lý

| File | Finding | Fix |
|---|---|---|
| `reports/circuit-closures/M02-evidence/_probe_ask_main.py:11` | SSRF (`urllib.request.urlopen`) | `safe_urlopen(req, timeout=timeout, allow_internal=True)` |
| `reports/circuit-closures/M02-evidence/_probe_ask_std.py:11` | SSRF (`urllib.request.urlopen`) | `safe_urlopen(req, timeout=timeout, allow_internal=True)` |
| `reports/circuit-closures/M03-evidence/_probe_http.py:23` | SSRF (`urllib.request.urlopen`) | `safe_urlopen(req, timeout=60, allow_internal=True)` |
| `reports/circuit-closures/M03-evidence/_probe_http.py:72` | path-traversal (`open(<var>, "w")`) | `Path(...)/"D3-m3-runtime.json"` + `out.open("w")` |
| `reports/circuit-closures/M04-evidence/_probe_http.py:40` | SSRF (`urllib.request.urlopen`) | `safe_urlopen(req, data=data, timeout=30, allow_internal=True)` |
| `reports/circuit-closures/M04-evidence/_probe_http.py:147` | path-traversal (`open(os.path.join(<var>), "w")`) | `Path(...)/"D3-m4-runtime.json"` + `.open("w")` |

`allow_internal=True` là bắt buộc: target của probe là loopback (127.0.0.1:8000/8002/8003)
và `validate_url()` trong `scp/security/url_safety.py` chặn loopback mặc định
(cùng pattern production đã dùng cho Ollama 127.0.0.1 — docstring `safe_urlopen`).

## Hash trước → sau (SHA256)

- `_probe_ask_main.py`: `1d6f7003da439d47814a9977be944511e9d9c47e7e77e3500adf2acfaf026ec6` → `110691949365ffc4d38e0e352226251a1a997208d3654c1abac8f0d0ba51a441`
- `_probe_ask_std.py`: `a238bc1f3a36f3d05260c92f34eaea93b5cfa9d6884d6498ced3898ad3b66c16` → `50222e999520a40d7e82ca412f200434d08fa9495b86c99732a3269afc56474e`
- `M03-evidence/_probe_http.py`: `91c48b65a59d12a15af4e303fd125179c8d29b91e954a77fb159ee479d69ee52` → `785bca5fe62722476ec0dd2d1ff8b068188f4f340477701ddcda32ce042b5b64`
- `M04-evidence/_probe_http.py`: `1fc224a1960ac2aa7f144f846d6674188f2b50178392d17d757524525b7d664c` → `4431cb78ee1faaefa911af8cdb23762086eb36ba458f4d3c37af2312c9fedb94`

## Verify (evidence)

1. `python -m py_compile` cả 4 file → OK (`PY_COMPILE_OK_ALL_4`).
2. Grep sau fix trên 4 file:
   - `urllib.request.urlopen` → 0 match.
   - bare builtin `open(` (regex `(^|[^_a-zA-Z.])open\(`) → 0 match; chỉ còn
     `safe_urlopen(...)` và `Path(...).open(...)` (M03:75, M04:150).
3. Reality test M02 (container `scp-scp-api-1` đang sống, port 8000 /health=200):
   - `_probe_ask_main.py` chạy trong container (`docker exec -i ... python -`) → exit 0,
     JSON đầy đủ (auth minted, probe A/A2/B trả về như kỳ vọng, kernel sqlite OK).
   - `_probe_ask_std.py` → exit 0, JSON đầy đủ (verdict FAIL/KILL withheld như D3 gốc,
     ledger_status OK, kernel_recent_tasks OK).
   - Cả hai chạy end-to-end qua đường `safe_urlopen` → hành vi giữ nguyên, cùng URL,
     cùng idempotency key (path duplicate-handling), KHÔNG ghi file evidence.
4. M03/M04 KHÔNG chạy được runtime: instance tạm 127.0.0.1:8002 (scp-m3-std) và
   127.0.0.1:8003 (scp-m4-probe) đã tardown (curl health → down). `py_compile` +
   grep là bằng chứng đủ cho 2 file này; logic fetch giữ nguyên tham số
   (Request object, timeout, data) — chỉ đổi hàm gọi.
5. `git status --porcelain reports/circuit-closures/` → chỉ 4 file probe script thay đổi;
   các file evidence .txt/.json không bị đụng.

## Commit

- `chore(evidence): de-shape probe scripts per L3 gate (outputs unchanged)` — 5 file
  (4 probe script + log này). 1 commit duy nhất theo giới hạn task.

## Open questions / giới hạn

- PASS ở đây = "scanner-pattern đã remove + py_compile OK + grep 0 + M02 chạy thật exit 0".
  Rescan Mimosa chưa chạy trong session này — cần rescan L3 gate để xác nhận 6 HIGH biến mất.
- M03/M04 chỉ được chứng minh ở mức syntax/import-shape, không ở mức HTTP runtime
  (instance tạm không còn). Nếu gate yêu cầu runtime proof, cần dựng lại instance tạm.
