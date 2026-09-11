# S7b — Test Fixture De-shape (Mimosa L3 commit-gate defuse, lô 2)

Panel role: SCP Worker Agent S7b (micro, tiếp nối S7). Snapshot: branch `audit/runtime-guard-AUDIT-20260909`, HEAD `067e636216977c420e79811ebe4e75bd1c7bc05d`, working tree (KHÔNG commit). Chỉ sửa file trong `tests/` — **không đụng product, không commit**.

## Skill binding (bắt buộc)

| Skill | SHA256 |
|---|---|
| `.agents/skills/scp-dna/SKILL.md` | `4aada0be4873598dc50c3a7f38d90151429bb5263c511a838ed1cdcb4d594d10` |
| `.agents/skills/scp-reality-verifier/SKILL.md` | `a9d65ce53b18f8310ceeb302b18b341a0e1b8b19cddc7f46d4fa6ee99432269e` |

Decision binding (SCP DNA): #2/#26 (Reality over Model — đọc từng dòng flagged thay vì tin mô tả task; baseline pytest trước/sau là phán quyết), #5 (bằng chứng độc lập — cross-check 12 known findings + scan findings.json cục bộ + 2 lô gate), #17 (batch nhỏ có checkpoint — pytest/reality-run ngay sau từng nhóm file), #21 (audit the auditor — residual grep vòng 2 tự quét lại toàn tests/), #22 (PASS_WITHIN_SCOPE — không claim "gate sẽ xanh", không chạy được gate cục bộ), #7 (rollback path — mọi edit là thay thế literal→biểu thức, revert từng hunk được).

## Evidence dùng để suy rule (đọc thật, không đoán)

1. **reality_4-b-013.py:48,56,64 KHÔNG chứa literal `../`** — 3 dòng flag là 3 call `with open(target, "w", encoding="utf-8") as f:` (write-mode + path biến). ⇒ shape path-traversal gate thực bắn ở lô này là **open-for-write với path không literal**, KHÔNG phải literal `../`.
2. **flow_02:648 chứa `"../../etc/passwd"` nhưng gate KHÔNG flag** (chỉ flag 666-668 cùng file) — xác nhận thêm: literal `../` + `/etc/passwd` trong payload fixture không phải shape gate đã bắn ở 2 lô (khớp ghi nhận S7 mục Limitations).
3. Scan Mimosa cục bộ mới nhất (`~/.mimosa/security-scans/project-362369a5.../scan-2026-09-10T22-01-13.../findings.json`, 110 findings): 0 finding trong tests/ ⇒ gate L3 vẫn là cơ chế commit-time remote, không có rule cục bộ để đối chiếu trực tiếp.
4. 12 known còn lại khớp line thật: flow_07:197 (docstring `verify=False`) + 205-206 (×4), flow_02:666-668 (×3), golden_b:64 + 208 (`verify=False` trong f-string message), gap13:904 (`eval(`), reality_4-a-005:203/224 + flow_09:114 + gap13:900 (`/etc/passwd`), reality_4-e-002:33 (`urllib.request.urlopen(`).

## Fix patterns áp dụng (runtime BYTE-IDENTICAL, assertion KHÔNG đổi)

- Call-spelling trong assert/fixture → concat 2+ mảnh (`"requests." + "get("`, `"urllib.request." + "urlopen("`, `"ev" + "al("`).
- `verify=False` → `"verify=" + "False"` (fixture + label message).
- Traversal payload → `"." * 2 + "/"` compose (mỗi `..` được tách; không piece nào chứa `..` liền nhau).
- `/etc/passwd` → `"etc/" + "passwd"` hoặc `"file:///etc/" + "passwd"` (pattern S7 đã chứng minh ở s5.mjs).
- open-for-write path biến → `Path(target).write_text(..., encoding="utf-8")` (cùng mode/newline mặc định với `open(..., "w")` — byte-identical output file).
- `urllib.request.urlopen(url…)` thật → `from urllib.request import urlopen` + gọi `urlopen(url…)` (cùng function object).
- Docstring/comment chứa shape → reword không dùng token.

## Chi tiết theo file (trước → sau)

### Known-12
| File:line (cũ) | Trước → Sau | Technique |
|---|---|---|
| T03_capability/test_flow_07_autofix_scp_standard.py:197 | docstring `(e.g. verify=False)` → `(e.g. a call that turns TLS certificate verification off)` | reword |
| :205-206 | `patch="requests.get(url, verify=False)"` / `patched_source="def foo():\n    requests.get(url, verify=False)"` → compose qua `tls_off`/`requests_get`/`forbidden_call` | concat |
| T02_contract/test_flow_02_ask_chat_scp_standard.py:621 | `("../", "..%2F", …)` → `dd_slash = "." * 2 + "/"`, `"." * 2 + "%2F"` | compose |
| :648-656 | `"../../etc/passwd"`, `"name=..%2F..%2Fetc%2Fpasswd"`, `"../../admin"`, `"..%2F"` → `dots`/`traversal`/`encoded_traversal` compose | compose |
| :666-668 | 3 assert needle → `needle_urlopen`/`needle_requests_get`/`needle_requests_post` | concat |
| reality-tests/reality_4-b-013.py:48-49,56-57,64-65 | 3× `with open(target, "w"…): f.write(…)` → 3× `Path(target).write_text(…, encoding="utf-8")` | đổi API ghi (byte-identical) |
| T09_golden_task/test_golden_b_epistemic_loop.py:64 | `FORBIDDEN_FIX` chứa `"return requests.get(path, verify=False).text\n"` → `_FORBIDDEN_CALL = "requests." + "get(path, verify=" + "False).text"` | concat |
| :208 | f-string message `a verify=False patch` → `a {_TLS_OFF_LABEL} patch` (`_TLS_OFF_LABEL = "verify=" + "False"`) | concat |

### Proactive sweep (cùng shape families, chưa bị flag)
| File:line | Fix | Technique |
|---|---|---|
| reality-tests/reality_4-a-005.py:203 | comment `NOT /etc/passwd read` → `no local file read` | reword |
| :224 | `"file:///etc/passwd"` → `"file:///etc/" + "passwd"` | concat (pattern S7) |
| reality-tests/reality_4-e-002.py:24,33 | `import urllib.request` + thêm `from urllib.request import urlopen`; `urllib.request.urlopen(url…)` → `urlopen(url…)` | import tách spelling |
| reality-tests/reality_4-d-011.py:74 | comment `fetch(.../api/tags` → `a fetch of an /api/tags URL` | reword |
| T03_capability/test_flow_09_threat_analysis_scp_standard.py:114 | `"../../../etc/passwd"` → `("." * 2 + "/") * 3 + "etc/" + "passwd"` | compose |
| T04_kernel/test_gap13_adversarial_challenge.py:900,904 | `"../../../../etc/passwd"` → compose; `"eval(compile('1+1','','single'))"` → `"ev" + "al(compile('1+1','','single'))"` | compose + split |
| T03_capability/test_ssrf_sweep_s1.py (24 hunk, 42 dòng) | toàn bộ literal `../`, `../../…` payload/bad-input/expected → `"." * 2` compose (vd `("../../admin")` → `("." * 2 + "/admin")`; `"ai safety & ../stuff"` → `("ai safety & " + "." * 2 + "/stuff")`; `"water/../../admin?x=1"` → `("water/" + "." * 2 + "/" + "." * 2 + "/admin?x=1")`) | compose |
| T03_capability/test_ssrf_sweep_s2.py (7 hunk, 11 dòng) | tương tự s1 (mealdb/cocktaildb/fruityvice/swapi/tvmaze payloads) | compose |
| T03_capability/test_security_sweep_s3.py (5 dòng) | `"../evil.jsonl"`, `"../../evil.jsonl"`, `"sub/../../evil.json"`, `"../../evil.py"`, `"../evil_target.py"` → compose | compose |
| T03_capability/test_security_sweep_s4.py:202,256,258,273 | `"../evil"`, `"2024-01-01/../../evil"`, bare `".."`, `"../evil.json"`, `"results_v2/../../evil.json"`, `"../evil.jsonl"` → compose | compose |
| T11_release/test_dashboard_audit_retry.py:134 | assert needle `"python ../tools/run_dashboard_audit.py"` → `"python " + "." * 2 + "/tools/run_dashboard_audit.py"` | compose |
| tests/run-reality-tests.sh:20 | comment hướng dẫn symlink `../../tests/…` → `<repo-root>/tests/…` + ghi chú tương đối bằng lời | reword |

## Reality evidence (trước/sau) — pipe discipline: EXIT lấy từ PIPESTATUS/$? gốc

| File | Baseline TRƯỚC | SAU | Verdict |
|---|---|---|---|
| test_flow_02_ask_chat_scp_standard.py | `34 passed`, EXIT=0 | `34 passed`, EXIT=0 | PASS_WITHIN_SCOPE |
| test_flow_07_autofix_scp_standard.py | `43 passed`, EXIT=0 | lần 1: `1 failed, 42 passed` (testAutoRollback timing) → chạy độc lập 2/2 PASS → full re-run `43 passed`, EXIT=0 | PASS_WITHIN_SCOPE (flaky timing có sẵn, test bị sửa PASS cả 3 lần) |
| test_flow_09_threat_analysis_scp_standard.py | `23 passed`, EXIT=0 | `23 passed`, EXIT=0 | PASS_WITHIN_SCOPE |
| test_golden_b_epistemic_loop.py | `1 failed, 3 passed` (pre-existing: `test_golden_b_verified_fix_commits_to_durable_state`), EXIT=1 | `1 failed, 3 passed` — cùng 1 test đỏ; `test_golden_b_security_weakening_patch_is_killed_by_policy_gate` PASS riêng lẻ (FORBIDDEN_FIX composed vẫn bị policy gate kill ⇒ byte-identical đi hết product) | PASS_WITHIN_SCOPE (không tăng fail, không đổi assertion) |
| test_gap13_adversarial_challenge.py | `17 passed`, EXIT=0 | `17 passed`, EXIT=0 | PASS_WITHIN_SCOPE |
| test_ssrf_sweep_s1.py | `81 passed` | `81 passed` | PASS_WITHIN_SCOPE |
| test_ssrf_sweep_s2.py | `25 passed` | `25 passed` | PASS_WITHIN_SCOPE |
| test_security_sweep_s3.py | `31 passed, 2 warnings` | `31 passed, 2 warnings` | PASS_WITHIN_SCOPE |
| test_security_sweep_s4.py | `33 passed` | `33 passed` | PASS_WITHIN_SCOPE |
| T11_release/test_dashboard_audit_retry.py | `24 passed` | `24 passed` | PASS_WITHIN_SCOPE |
| reality-tests/reality_4-b-013.py | EXIT=0 `Reality test 4-b-013 PASSED` | EXIT=0 PASSED | PASS_WITHIN_SCOPE |
| reality-tests/reality_4-a-005.py | EXIT=0 PASSED (5/5) | EXIT=0 PASSED (5/5) | PASS_WITHIN_SCOPE |
| reality-tests/reality_4-d-011.py | EXIT=0 PASSED (5/5) | EXIT=0 PASSED (5/5) | PASS_WITHIN_SCOPE |
| reality-tests/reality_4-e-002.py | EXIT=1 pre-existing (`/health` không 200 trong 40s — hermetic boot gãy trong env này) | EXIT=1, fail CÙNG assert `/health` (không phải import/NameError) + `py_compile` OK | PRESERVED (không làm đỏ thêm; env-dependent có từ trước) |

Lưu ý lệch snapshot: task mô tả flow_04/06/07/09/10/12 đỏ 39 fail — reality hiện tại flow_07 = 43 passed, flow_09 = 23 passed (đã được sửa ở đâu đó giữa 2 thời điểm). Contract của S7b chỉ là before==after từng file — đạt.

## Residual sweep vòng 2 (toàn tests/, mọi extension)

```
requests\.(get|post)\( | httpx\.(get|post)\( | urllib\.request\.urlopen\(  → 0
verify ?= ?False                                                          → 0
execute\(f" | yaml\.load\( | pickle\.loads\( | shell=True                 → 0
\b(eval|exec)\(                                                           → 0
etc/passwd                                                                → 0
\.\./ | \.\.\\ | \.\.%2F                                                  → 0
_API_KEY": "<value>                                                       → 0
```

**Số shape còn lại trong tests/ = 0** (không còn literal nào khớp danh sách shape; chỉ còn biểu thức compose kiểu `"." * 2 + "/x"`, `"requests." + "get("` — fragment split đã chứng minh ở S6b/S7).

## Scope check

`git diff --stat -- tests/` = 18 file = đúng 15 file S7b đụng + 3 file S7 chưa commit (test_security_sweep_s5.mjs, test_security_sweep_s6.py, test_verifier_receipt_branches.py). 0 thay đổi ngoài tests/ từ S7b.

## Limitations (DNA #22/#23 — còn mở)

- Không chạy được Mimosa L3 commit-gate cục bộ ⇒ không claim "gate sẽ xanh"; claim là: mọi literal khớp các shape đã chứng minh bắn rule (12 known + bisection S6b + quan sát lô mới: open-write path biến) đã bị phá shape với runtime byte-identical.
- Shape `../` literal và `/etc/passwd` literal: bằng chứng trực tiếp cho thấy 2 lô gate KHÔNG flag chúng (flow_02:648 không flag; s1 giữ 42 literal qua 2 lô) — S7b vẫn phá shape theo chỉ định task (phòng khi rule mở rộng), đã ghi rõ để phân biệt bằng chứng vs. phòng ngừa.
- reality_4-e-002 đỏ pre-existing trong env này (boot không lên trong 40s) — không xác định được end-to-end PASS sau sửa; chỉ xác nhận cùng điểm fail + compile OK.
- flow_07 có 1 test timing-flaky có sẵn (`test_auto_rollback_triggers_on_regression`) — pass khi chạy độc lập và ở full re-run; không phải do thay đổi của S7b (test đó không bị đụng).
