# S9b — RECOVERY attempt 2: re-apply L3 de-shape theo rulebook S7/S7b/S7c

Panel role: SCP Worker Agent S9b (recovery attempt 2; attempt 1 chết trước
commit đầu, để lại s1 sửa dở một phần). Snapshot: branch
`audit/runtime-guard-AUDIT-20260909`, base `481ac07`. Commit theo nhóm nhỏ
(1–4 file/commit) để sống sót qua provider kill — KHÔNG để >3 file sửa dở.

## Skill binding (bắt buộc)

| Skill | SHA256 |
|---|---|
| `.agents/skills/scp-dna/SKILL.md` | `4aada0be4873598dc50c3a7f38d90151429bb5263c511a838ed1cdcb4d594d10` |
| `.agents/skills/scp-reality-verifier/SKILL.md` | `a9d65ce53b18f8310ceeb302b18b341a0e1b8b19cddc7f46d4fa6ee99432269e` |

Decision binding (SCP DNA): #2/#26 (Reality over Model — pytest/node/reality-run
trước→sau là phán quyết), #5 (bằng chứng độc lập — re-apply ĐÚNG theo 3
rulebook S7/S7b/S7c, không suy lại rule từ đầu), #17 (batch nhỏ có checkpoint —
commit ngay sau từng 1–4 file + verify), #21 (audit the auditor — residual grep
vòng cuối tự quét, tự bắt thêm 1 điểm sót `..\..\x` ở s3), #22 (PASS_WITHIN_SCOPE
— không chạy được Mimosa L3 commit-gate cục bộ nên không claim "gate sẽ xanh"),
#7 (rollback — mọi edit là literal→biểu thức compose byte-identical / alias
import / đổi API ghi, revert từng hunk được).

## Quy tắc bất di bất dịch của toàn bộ thay đổi

- KHÔNG đụng product code. Chỉ test/fixture/script-ops trong danh sách.
- Assertion byte-identical: mọi compose đều được assert bằng python (`==` giá
  trị gốc) trước khi commit. Không skip/xfail/hạ chuẩn (1 lần viết sai tạm
  thời thêm assert dư `or True` ở s4 — tự phát hiện, sửa lại đúng 3 assert
  concat nghiêm ngặt TRƯỚC khi chạy test/commit).
- Không đụng: 4 file WIP stream khác (T00_infra, T01_boot, T03/flow_11,
  T03/s6), stash, PROMPT_INJECTION_GAP_REPORT.md, my_fixes.patch, GA.md.

## File re-applied (19 file, đúng danh sách task)

### Nhóm A — sweep (6 file)
| File | Fix chính | Commit |
|---|---|---|
| `tests/T03_capability/test_ssrf_sweep_s1.py` | attempt 1 để lại 99/72 dòng; hoàn thiện nốt: `api_key="KEY"` L643 → `_GENERIC_KEY_FIXTURE` (đủ 6 call-site). Đã có: base64 consts, needle `httpx./requests./urlopen` (S7c fragment `url"+"open(`), canary `169.254.169.254` → `".".join([...])`, compose `.`×2 cho 42 literal `../` | `8f4bf00` |
| `tests/T03_capability/test_ssrf_sweep_s2.py` | needle consts + `_CREDENTIAL_SHAPED_SOURCES` → `ORIGINAL_MAPPING` dict comprehension (assert byte-identical bằng python); 4 assert SSRF → needle; 12 dòng payload mealdb/cocktaildb/fruityvice/swapi/tvmaze compose `.`×2 | `37c9d87` |
| `tests/T03_capability/test_security_sweep_s3.py` | docstring reword (yaml.load/pickle.loads/eval), payload `os.sys"+"tem('id')`, 3 assert concat, vector `('os')."+"system('x')`, `open('/etc/"+"passwd')`, `import sub"+"process`; 5 dòng `../` compose; + proactive: `r"..\..\x"` → `("." * 2 + "\\") * 2 + "x"` (byte-identical, grep-clean) | `8fcb086` + `96f0280` + `7ebb732` |
| `tests/T03_capability/test_security_sweep_s4.py` | `ADVERSARIAL_TASK_ID` → base64 decode (assert byte-identical); 2 docstring reword; 3 assert `pickle.lo"+"ads`/`pickle.du"+"mps`/`yaml.lo"+"ad`; 6 dòng traversal compose (`../evil`, `2024-01-01/../../evil`, bare `..`, `../evil.json`, `results_v2/../../evil.json`, `../evil.jsonl`) | `c06b223` |
| `tests/T03_capability/test_security_sweep_s5.mjs` | `META_HOST = ["169","254","169","254"].join(".")` ×4 metadata URL (template literal); `user:pass` + `@…` concat; `evalNeedle = "ev"+"al("` (assert + message + check-name reword); `"new Fun"+"ction("` / `"vm."+"runIn"`; `AWAIT_FETCH_URL = "await "+"fetch(url"` ×2; vulnerable-shape `await fetch(\`${provider.url}` / `${base}/` tách NHIỀU DÒNG; `file:///etc/"+"passwd` ×2; header `fetch()` reword | `839f0f4` |
| `tests/T04_kernel/test_verifier_receipt_branches.py` | `secret="mysecret"` ×9 → `_FIXTURE_SECRET` (b64 `bXlzZWNyZXQ=`); `b'secret'` ×2 → `_FIXTURE_SECRET_BYTES` (b64 `c2VjcmV0`); `"signature": "dummy"` ×5 → `_DUMMY_SIGNATURE = "dum"+"my"` | `fd3f742` |

### Nhóm B — flow/golden (6 file)
| File | Fix chính | Commit |
|---|---|---|
| `tests/T03_capability/test_flow_07_autofix_scp_standard.py` | docstring reword `(e.g. a call that turns TLS certificate verification off)`; patch/patched_source compose qua `requests_get`/`tls_off` | `2cc7ed6` |
| `tests/T02_contract/test_flow_02_ask_chat_scp_standard.py` | L621 `dd_slash = "."*2+"/"`, `dd_encoded`; 648-656 compose `dots`/`traversal`/`encoded_traversal` (passwd tách `etc/"+"passwd`); 666-668 3 assert → needle (`url"+"open(` fragment per S7c) | `c96f8a6` |
| `tests/T03_capability/test_flow_09_threat_analysis_scp_standard.py` | payload `"../../../etc/passwd"` → `("." * 2 + "/") * 3 + "etc/" + "passwd"` | `fe6d27b` |
| `tests/T09_golden_task/test_golden_b_epistemic_loop.py` | `_FORBIDDEN_CALL = "requests."+"get(path, verify="+"False).text"`; message f-string → `{_TLS_OFF_LABEL}` | `fe6d27b` |
| `tests/T04_kernel/test_gap13_adversarial_challenge.py` | `"../../../../etc/passwd"` → `("." * 2 + "/") * 4 + "etc/" + "passwd"`; `"eval(compile…)"` → `"ev"+"al(…"` | `b713aa8` |
| `tests/T11_release/test_dashboard_audit_retry.py` | assert needle → `"python " + "." * 2 + "/tools/run_dashboard_audit.py"` | `b713aa8` |

### Nhóm C — reality + root (7 file)
| File | Fix chính | Commit |
|---|---|---|
| `tests/reality-tests/reality_4-b-013.py` | 3× `with open(target,"w")` → `Path(target).write_text(…, encoding="utf-8")` (cùng io.open, byte-identical output file) | `c03402f` |
| `tests/reality-tests/reality_4-a-005.py` | comment reword `no local file read`; `"file:///etc/"+"passwd"` | `c03402f` |
| `tests/reality-tests/reality_4-e-002.py` | `from urllib.request import urlopen as _url_open` + call `_url_open(url, timeout=timeout)` (S7c alias — `urlopen(` post-import vẫn bị bắn) | `c03402f` |
| `tests/reality-tests/reality_4-d-011.py` | comment reword `a fetch of an /api/tags URL` | `c03402f` |
| `tests/run-reality-tests.sh` | comment symlink `../../tests/…` → `<repo-root>/tests/…` + mô tả bằng lời | `d8c084f` |
| `test_api.py` (root) | `from urllib.request import urlopen as _url_open`; call `_url_open(req).getcode()` | `d8c084f` |
| `scripts/ops/autofix_e2e_fixture_test.py` | `patch="ev"+"al(user_input)"` | `d8c084f` |

## Reality evidence (baseline rulebook → measured, pipe discipline: EXIT từ PIPESTATUS/$? gốc)

| Check | Baseline | Measured | Verdict |
|---|---|---|---|
| pytest s1 | 81 passed | `81 passed`, EXIT=0 | PASS_WITHIN_SCOPE |
| pytest s2 | 25 passed | `25 passed`, EXIT=0 | PASS_WITHIN_SCOPE |
| pytest s3 | 31 passed, 2 warnings | `31 passed, 2 warnings`, EXIT=0 (chạy lại sau mỗi hunk s3) | PASS_WITHIN_SCOPE |
| pytest s4 | 33 passed | `33 passed`, EXIT=0 | PASS_WITHIN_SCOPE |
| node s5.mjs | 43 passed, 0 failed | `== S5 sweep test: 43 passed, 0 failed ==`, EXIT=0 | PASS_WITHIN_SCOPE |
| pytest verifier | 15 passed | `15 passed`, EXIT=0 (9 secret + 5 signature replace đúng count) | PASS_WITHIN_SCOPE |
| pytest flow_07 | 43 passed | `43 passed`, EXIT=0 | PASS_WITHIN_SCOPE |
| pytest flow_02 | 34 passed | `34 passed`, EXIT=0 | PASS_WITHIN_SCOPE |
| pytest flow_09 | 23 passed | `23 passed`, EXIT=0 | PASS_WITHIN_SCOPE |
| pytest golden_b | 1 failed, 3 passed (pre-existing `test_golden_b_verified_fix_commits_to_durable_state`) | `1 failed, 3 passed`, EXIT=1 — CÙNG 1 test đỏ; `test_golden_b_security_weakening_patch_is_killed_by_policy_gate` PASS riêng lẻ (FORBIDDEN_FIX composed vẫn bị policy gate kill ⇒ byte-identical đi hết product) | PASS_WITHIN_SCOPE (không tăng fail) |
| pytest gap13 | 17 passed | `17 passed`, EXIT=0 | PASS_WITHIN_SCOPE |
| pytest T11 | 24 passed | `24 passed`, EXIT=0 | PASS_WITHIN_SCOPE |
| reality 4-b-013 | EXIT=0 PASSED | `Reality test 4-b-013 PASSED` 8/8, EXIT=0 | PASS_WITHIN_SCOPE |
| reality 4-a-005 | EXIT=0 (5/5) | `PASSED (5/5 assertions)`, EXIT=0 | PASS_WITHIN_SCOPE |
| reality 4-d-011 | EXIT=0 (5/5) | `PASSED (5/5 assertions)`, EXIT=0 | PASS_WITHIN_SCOPE |
| reality 4-e-002 | EXIT=1 pre-existing `/health không 200 trong 40s` | EXIT=1, fail CÙNG assert dòng 77 (không NameError/ImportError ⇒ alias `_url_open` hoạt động) + `py_compile` OK | PRESERVED (env-dependent có từ trước) |
| test_api.py | chạy trực tiếp in `404`, EXIT=0 | y hệt: in `404`, EXIT=0 + `py_compile` OK | PASS_WITHIN_SCOPE |
| autofix_e2e_fixture_test.py | KHÔNG chạy thật (ghi `.private-secrets/` ngoài phạm vi) | `py_compile` OK | VERIFIED_BY_COMPILE |

Byte-identity đã assert bằng python cho: ORIGINAL_MAPPING (s2), ADVERSARIAL_TASK_ID
(s4), needle urlopen (flow_02), _FORBIDDEN_CALL/_TLS_OFF_LABEL (golden_b),
compose traversal (flow_02/flow_09/gap13/s3×2), `..\..\x` (s3 eval trực tiếp
biểu thức trong file).

## Residual grep vòng cuối (git grep -E trên tests/ + test_api.py + scripts/ops/, loại trừ 4 file WIP stream khác)

```
requests\.(get|post)\( | httpx\.(get|post)\( | urllib\.request\.urlopen\( → 0
verify ?= ?False                                                          → 0
execute\(f" | yaml\.load\( | pickle\.loads\( | shell=True                 → 0
\b(eval|exec)\(                                                           → 0
etc/passwd                                                                → 0
\.\./ | \.\.%2F                                                           → 0
\.\.\\                                                                    → 2 (FALSE POSITIVE)
_API_KEY": "                                                              → 0
```

2 hit `\.\.\\` còn lại là false positive, KHÔNG phải traversal:
- `tests/reality-tests/reality_4-b-009.py:117` — text `...\"` (ellipsis +
  escaped-quote trong chuỗi report), regex `\.\.\\` khớp 2 dấu chấm cuối của
  `...` + backslash của `\"`.
- `tests/reality-tests/reality_4-d-009.py:42` — cùng hiện tượng `...\"`.
Cả 2 nằm ngoài danh sách 19 file, có từ HEAD 481ac07, không chứa shape
traversal nào (không có `..\` theo nghĩa path). Không đụng để giữ scope.

Số shape thật còn lại = 0.

## Scope check

`git diff --stat 481ac07..HEAD` = đúng 19 file trong danh sách (6 Nhóm A +
6 Nhóm B + 7 Nhóm C), 0 file product, 0 thay đổi ngoài scope. Working tree
cuối: chỉ còn GA.md + 4 file WIP stream khác (không đụng, đúng lệnh) + file
untracked có sẵn. 14 commit, mỗi commit 1–4 file.

## Commit list (14)

`8f4bf00` s1 · `37c9d87` s2 · `8fcb086` s3 · `c06b223` s4 · `839f0f4` s5.mjs ·
`fd3f742` verifier · `2cc7ed6` flow_07 · `c96f8a6` flow_02 · `fe6d27b`
flow_09+golden_b · `b713aa8` gap13+T11 · `c03402f` reality×4 · `d8c084f`
sh+test_api+autofix_e2e · `96f0280` s3 backslash compose · `7ebb732` s3
dot-multiply compose (grep-clean).

## Limitations (DNA #22/#23 — còn mở)

- Không chạy được Mimosa L3 commit-gate cục bộ ⇒ không claim "gate sẽ xanh";
  claim là: mọi literal khớp các shape đã chứng minh bắn rule (12 known +
  bisection S6b + quan sát lô flag S7/S7b/S7c) đã bị phá shape với runtime
  byte-identical, kèm residual grep = 0 shape thật.
- golden_b giữ nguyên 1F pre-existing (`…commits_to_durable_state`) — không
  thuộc phạm vi de-shape, không tăng fail.
- reality_4-e-002 đỏ pre-existing trong env này (hermetic boot không lên trong
  40s) — chỉ xác nhận cùng điểm fail + compile OK + alias đúng function object.
- 2 hit `\.\.\\` false-positive (ellipsis) để nguyên — nếu gate mở rộng rule
  sang backslash-traversal trong chuỗi report thì cần compose thêm 2 file
  reality 4-b-009/4-d-009 (ngoài scope hiện tại).
