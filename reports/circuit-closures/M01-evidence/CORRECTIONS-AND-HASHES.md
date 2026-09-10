# M01 corrections and hash binding

Sinh boi buoc dong mach M1, sau khi 2 reviewer doc lap bao gap. Cac muc duoi day la dinh chinh
co ghi chu; khong xoa/sua evidence da commit o `62afcd7`.

## C1. Dinh chinh D2.8 - lenh ghi trong evidence khong phai lenh da chay

`D2-docker.txt` muc D2.8 ghi comment `# command: for f in <scope>; do diff <(git show $PIN:$f) $f; done`,
nhung lenh thuc thi la `git diff --quiet <pin> -- <file>`. Lenh trong comment KHONG tai lap duoc output
(worktree CRLF, blob LF). Chay lai CA HAI de doi chieu:

### C1.1 lenh dung nhu da chay: `git diff --quiet <pin> -- <file>`

```
scp/api_server_parts/lifespan.py                               exit=0 -> IDENTICAL (no diff)
scp/api/background_jobs.py                                     exit=0 -> IDENTICAL (no diff)
scp/policy/retry_policy.py                                     exit=0 -> IDENTICAL (no diff)
scp/api_server.py                                              exit=0 -> IDENTICAL (no diff)
scripts/run_scp_acceptance.py                                  exit=0 -> IDENTICAL (no diff)
tests/T01_boot/test_flow_01_boot_background_scp_standard.py    exit=0 -> IDENTICAL (no diff)
compose.yml                                                    exit=0 -> IDENTICAL (no diff)
Dockerfile                                                     exit=0 -> IDENTICAL (no diff)
.env.example                                                   exit=0 -> IDENTICAL (no diff)
```

### C1.2 lenh ghi trong evidence (byte tho, khong chuan hoa EOL)

```
scp/api_server_parts/lifespan.py                               diff line count = The system cannot find the file specified.
scp/api/background_jobs.py                                     diff line count = The system cannot find the file specified.
scp/policy/retry_policy.py                                     diff line count = The system cannot find the file specified.
scp/api_server.py                                              diff line count = The system cannot find the file specified.
scripts/run_scp_acceptance.py                                  diff line count = The system cannot find the file specified.
tests/T01_boot/test_flow_01_boot_background_scp_standard.py    diff line count = The system cannot find the file specified.
compose.yml                                                    diff line count = The system cannot find the file specified.
Dockerfile                                                     diff line count = The system cannot find the file specified.
.env.example                                                   diff line count = The system cannot find the file specified.
```

Ket luan: noi dung giong nhau (C1.1 sach). Khac biet o C1.2 do `core.autocrlf=true` lam worktree CRLF con
blob LF. Day la loi ghi chep cua evidence, dinh chinh tai day.

## C2. EOL binding - sha256 worktree (CRLF) vs sha256 LF-normalized (= noi dung blob)

| file | sha256_worktree | sha256_lf | bang nhau |
|---|---|---|---|
| scp/api_server_parts/lifespan.py | `ac47e4333c3b4809cd74745a4770b83826f9db85261244fe8aa76e7a929e0ecc` | `fec7b6435040cabef85e27991fc6ac51213afe98078f14e01f518c7b0cc8f9c7` | CO |
| scp/api/background_jobs.py | `56b98da21e37e65bc14583999512900e8c9573892bf6edcc70be542010be6531` | `56b98da21e37e65bc14583999512900e8c9573892bf6edcc70be542010be6531` | khong (LF-only) |
| scp/policy/retry_policy.py | `5671d328af93b1fb85a4bfb8323fbf4c90358c08927a6730d706bc38cd4bb906` | `5671d328af93b1fb85a4bfb8323fbf4c90358c08927a6730d706bc38cd4bb906` | khong (LF-only) |
| scp/api_server.py | `57b5cbac9f0cadca5d03c48afba67749f3ef891981365c54a1128c7e709725b8` | `35f2d2e95b872cd913a4cb5c5be1beee46d5eddd67582ef5e617d05f6ef1fff7` | CO |
| scripts/run_scp_acceptance.py | `ca5c96c0347d98f38c8865b5471dc89610a75017bfefff53f5f0130dcb16da77` | `2f37145c7f003f4b4307094b2c9a69c58344f38e85fab0faa02fe2b7f697f2b5` | CO |
| tests/T01_boot/test_flow_01_boot_background_scp_standard.py | `056d11da1d52adc73d3f9ba9f30b2bc4362ebe9f9b3898a197d0785aa7e72629` | `9ea14bb3487c8502f1b74c1b2d0c36725958585b8152b1e0a263cc70055dee8e` | CO |
| compose.yml | `aef79d575e78d3ca6354789c6a43809abf6008ec978901d5dcfc117eb6cbdb88` | `8b0b221def8ebe5bd9e4e15370a755cdc25c57ac63c2ad09f75ecd7c8b9ee68b` | CO |
| Dockerfile | `ec5563e0c03e85956ddc027225a85df613b55ef0c7eb5dcfea33e9988a7b43fb` | `6964b8f3ccf320b327e5c197ca4572dc4fa5bcfc64a0d2d494c0a4044265fef9` | CO |
| .env.example | `1fec1d0113f8d7daff56107cd046f387e90cfbf4c432395c30e8999703949c4e` | `18e714ff9eba35d89cddee5dd6a436868a5afae2384d8263bf0b1f434e4760ec` | CO |
| reports/circuit-closures/M01-evidence/D1-T01-pytest.txt | `ad35d25e29c75e3f1e3050ad0d67c11e48e3ec54367219459fa9936fabc5421c` | `6e1b9e7a06b31e56a3506965f602451109eb9c95dd260c8340586c6034d2fe5d` | CO |
| reports/circuit-closures/M01-evidence/D2-docker.txt | `9146cff8a769bf1463f322f00d12d1bd527a9b07dd2ef59831121326046e6bb8` | `6d16bc55a921e51d49b91314ca28724572b8d4f948ac0e464238b9a2ae008e1f` | CO |
| reports/circuit-closures/M01-evidence/D3-adversarial-pytest.txt | `06a2aa9ad0fd399aba15a82d1e791f13611327b174e97dd4e3799cae9ab4ebb1` | `51a4b92c55a407f118a8823cec2baab4b98026b695c3039cc92937b61b993f34` | CO |
| reports/circuit-closures/M01-evidence/D4-mimosa-latest.json | `cf9a00eff0874ea139fe92db6d7e8d3c5f8781b09dd80b1d3150a4d72e311d45` | `323f1d2680286641e8577365b9b66f0039cc55b63b13357cfdaeb9c6e15e82d6` | CO |
| reports/circuit-closures/M01-evidence/D4-mimosa-deepscan.json | `fb8f180bbdd62b302ad373f823aecc3a57ce1d44ce3a0a6c24f9a72550781ef8` | `6bbafc16f51563dea1b0630939e34dccae8608f50222a65aab112d54fe76fdfd` | CO |
| reports/circuit-closures/M01-evidence/D6-ast-scan.txt | `0186da7e691f707b5db4077aff2c6e77155db4650f6b060a5bc2f9f5aa8997c7` | `0542fb4b7444552a4e8ec608f5bb4b9c5ae5889fd70e1cec331eb9ae7a960433` | CO |
| reports/circuit-closures/M01-evidence/D6-runtime-probe.txt | `2e7d2fdf7265746b5bda4802e21853cda5332b52f8a61f5baf13a29bb511040e` | `4f8a03f8bd5ec6f61fba388c3e54c0c945edfb79d7936de921bceee0bb246607` | CO |
| reports/circuit-closures/M01-evidence/D7-todo-scan.txt | `31fb183a3a18d8c6f74aa672c421ad4bad64bfd53bcc2ffca6e84851115de28a` | `ce9a0d1004670126de92c4004d97449ee0651763f0adc993409717912da92feb` | CO |
| reports/circuit-closures/CIRCUIT-FLOW-MAP.md | `deef34bd2f437b8d980278a23503b75643aae9edfcc137b6175e3feb507e3e76` | `deef34bd2f437b8d980278a23503b75643aae9edfcc137b6175e3feb507e3e76` | khong (LF-only) |
| reports/circuit-closures/M01-runbook.md | `9727e3c996b7a65cb7007175f4d4410496719f2ca234027584a9ce0cb8833bde` | `9727e3c996b7a65cb7007175f4d4410496719f2ca234027584a9ce0cb8833bde` | khong (LF-only) |

`sha256_lf` (chuan hoa CRLF->LF) la gia tri CO THAM QUYEN va on dinh tren moi nen tang: no bang dung noi
dung blob luu trong git.

`sha256_worktree` chi mo ta may nay tai thoi diem dong mach, vi `core.autocrlf=true`:
- voi cac file dang o dang CRLF tren dia, verifier checkout lai se ra CRLF => khop `sha256_worktree`;
- voi cac file moi ghi o dang LF (D5-reviewer-digest.md, CIRCUIT-FLOW-MAP.md, M01-runbook.md),
  `sha256_worktree` hien bang `sha256_lf`, nhung sau mot lan checkout moi git se ghi CRLF => khi do
  `sha256_worktree` se KHAC gia tri ghi o day.

=> Khi verify: dung `sha256_lf` (chuan hoa truoc khi bam) lam moc; dung so byte tho `sha256_worktree`
tru khi biet chac che do EOL cua checkout.

## C3. F821 `logger` trong lifespan.py (reviewer 1, phan hoi F2)

```
grep -c logger lifespan.py = 52
so lan getLogger trong lifespan.py = 0
module-level logger defined: False
after api_server import, module-level logger: False
2026-09-10 19:37:53,981 | INFO    | scp.api | [Security] HTTPS redirect disabled (set SCP_FORCE_HTTPS=1 in prod)
2026-09-10 19:37:53,981 | INFO    | scp.api | [Security] CSRF protection: Bearer token auth
C:\Users\check\AppData\Local\Programs\Python\Python312\Lib\site-packages\requests\__init__.py:113: RequestsDependencyWarning: urllib3 (2.7.0) or chardet (6.0.0.post1)/charset_normalizer (3.4.3) doesn't match a supported version!
  warnings.warn(
2026-09-10 19:37:54,327 | INFO    | scp.autofix | [R7-Full] IMP-6 (rollback token) + IMP-9 (dry-run) injected into AutoFixEngine
2026-09-10 19:37:54,348 | INFO    | scp.api | [OTel] tracing disabled: SCP_OTEL_ENABLED=0
276:def _rebind_part_function(fn):
286:_async_fact_check = _rebind_part_function(_async_fact_check_part._async_fact_check)
287:_ask_impl = _rebind_part_function(_ask_impl_part._ask_impl)
289:lifespan = asynccontextmanager(_rebind_part_function(_lifespan_raw))
```

Ket luan: `lifespan.py` KHONG tu dinh nghia `logger`; no chi chay duoc vi `scp/api_server.py` rebind ham bang
globals cua api_server (noi co `logger`). Duong app/test da duoc reviewer chay that va an toan, nhung goi
module truc tiep (raw import / refactor / static analysis) se `NameError` dung tai nhanh fail ma M1 muon
"fail loudly". Day la khuyet diem CO SAN (51 cho truoc commit, dong moi them la cho thu 52) va nam ngoai
pham vi 6 vi tri `except: pass` cua hop dong. Ghi nhan chinh thuc, KHONG sua trong commit nay: sua se doi
SHA pin da do runtime => phai chay lai D1+D2+D4. Follow-up de xuat: them `logger = logging.getLogger("scp.api")`.

## C4. So lieu HIGH: 194 (hook L3) vs 184 (deep scan)

Hook L3 thong bao `194 high`; deep scan co seal bao `high=184` (medium=14, low=98, businessLogic=1).
Hai nguon khac nhau (hook gate vs MCP deep scan; co the khac ruleset/thoi diem), nen KHONG dung 194 nhu
mot con so scan da kiem chung. Closure record dung so cua deep scan co seal.

## C5. Trang thai chinh xac cua X1 (runtime probe D6)

`D6-runtime-probe.txt` chung minh nhanh `SCP_PORT` sai THAT SU phat log WARNING `[MACH1-FIX-8]` va van
fallback ve 8000 (hanh vi khong doi). 5 nhanh log moi con lai KHONG duoc kich hoat trong boot sach cua D2
(`MATCH_COUNT=0` cho `MACH1-FIX-8` trong log container) => D6 co bang chung tinh (AST) + 1 bang chung runtime,
khong phai ca 6.

## C6. PHU LUC RE-PIN (2026-09-10, sha_pin MOI 765075312bdc55373a86d9c5577ac62140c7ad64)

DOC MUC NAY TRUOC KHI DUNG BANG HASH O C2 / C1 / C5.

- C3 DA DUOC XU LY tai PIN2: `import logging` da co san trong `scp/api_server_parts/lifespan.py` va
  dong `logger = logging.getLogger("scp.api")` da duoc them. Cross-check bang tool doc lap (ruff, khac
  scanner D6): `ruff check --select F821` -> TRUOC 52 loi `Undefined name logger`, SAU `All checks passed!`.
  Import truc tiep module tra ve `<Logger scp.api (INFO)>` va la CUNG object voi `scp.api_server.logger`
  (`m.logger is a.logger == True`) nen khong co double-emit / khong them handler.
- F7 CUNG DA DUOC XU LY tai PIN2: dong log SCP_PORT khong con dua raw env value va khong con dua message
  cua exception (voi `ValueError`, message CHUA chinh raw value) vao log. No chi con type loi + do dai +
  preview da cat 24 ky tu va da thay control char bang `?`. Probe case B (value chua newline + dong log
  gia `CRITICAL`): ghi ra dung 1 dong vat ly, payload khong lot vao log. Hanh vi fallback ve 8000 KHONG doi
  (case A/B/C deu `configured_port=8000`).
- BANG HASH O C2 (va cac so lieu C1/C5) CHI CON HIEU LUC TAI sha_pin CU `62afcd7`. Sau PIN2, hash cua
  `scp/api_server_parts/lifespan.py`, `scp/api_server.py` va cua D1/D3/D6-ast/D6-runtime-probe/D7 DA DOI.
  Nguon hash CO THAM QUYEN cho trang thai hien tai la `reports/circuit-closures/M01-closure.json`
  (muc `checklist` + `evidence`, ghi ca `sha256` LF va `sha256_worktree`).
- C4 giu nguyen hieu luc: khong dung 194 nhu mot con so scan da kiem chung.
- GHI CHU PROVENANCE: phu luc nay do chinh chuoi re-pin tu ghi sau khi do lai, KHONG phai mot bai review
  doc lap. PIN2 chua qua D5 doc lap (xem `known_gaps` trong M01-closure.json).

