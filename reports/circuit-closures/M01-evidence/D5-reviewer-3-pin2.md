# Đánh giá ĐỘC LẬP M1 (Boot & Background) — PIN2

- **Reviewer**: subagent_03 (ngoài chuỗi fix, read-only tuyệt đối)
- **PIN cần review**: `765075312bdc55373a86d9c5577ac62140c7ad64` (PIN2)
- **Repo**: `C:\Users\check\Downloads\scp` — branch `audit/runtime-guard-AUDIT-20260909`
- **Tham chiếu**: `reports/circuit-closures/M01-closure.json`, `M01-evidence/*`, `CLOSURE-CONTRACT.md`
- **Ràng buộc đã tuân thủ**: KHÔNG sửa file trong repo, KHÔNG commit, KHÔNG chạy pytest toàn suite, KHÔNG docker build/up. Chỉ dùng: `git show/log/status/rev-parse`, `Get-FileHash`, `ruff --select F821`, script AST tự viết trong workspace của reviewer, `docker ps`, `curl /health` (đọc).
- **Thời điểm review**: 2026-09-10 (~20:05 +07:00)

> Lưu ý quan trọng về HEAD: tại thời điểm review `git rev-parse HEAD` = **`067e636216977c420e79811ebe4e75bd1c7bc05d`** (commit docs "re-pin closure record"), tức HEAD ≠ PIN2. Chi tiết ở hàng 3a.

---

## Bảng Claim | Bằng chứng tự thu | VERDICT | Ghi chú

| # | Claim | Bằng chứng tự thu | VERDICT | Ghi chú |
|---|-------|-------------------|---------|---------|
| 1a | F821 `logger` đã có binding đúng (`logging.getLogger("scp.api")`) và **cùng object** với `scp.api_server.logger` | `git show 7650753 -- scp/api_server_parts/lifespan.py` thêm 7 dòng, có `logger = logging.getLogger("scp.api")` đặt ở **module level** (sau imports, trước `@asynccontextmanager`). `import logging` đã có sẵn (dòng 16). `Select-String scp/api_server.py` → dòng 64: `logger = logging.getLogger("scp.api")`. Cả hai dùng **cùng tên** "scp.api"; `logging.getLogger` cache theo tên ⇒ **cùng object** (hệ quả tất yếu của stdlib, không cần import nặng để chứng minh). `ruff check --select F821 scp/api_server_parts/lifespan.py` → **All checks passed!**; `git show bae6196:...lifespan.py \| ruff ... F821 -` → **Found 52 errors** (đúng 52→0). | **XÁC NHẬN** | Đúng cả (a) binding đúng tên và (b) cùng object. Số 52 khớp claim D6. |
| 1b | Không đổi **hành vi fallback port 8000** | Đọc `_scp_service_identity()` trong `scp/api_server.py` (dòng 74+): logic giữ nguyên `_port=None` → quét `sys.argv` (1..65535) → `if _port is None: _port = 8000`. Diff PIN2 **chỉ** đổi chuỗi thông điệp `logger.warning(...)` (thêm type lỗi + len + preview 24 ký tự đã lọc control char), KHÔNG chạm luồng điều khiển. Assert runtime trong `D6-runtime-probe.txt` case A/B/C đều `configured_port=8000`. | **XÁC NHẬN** | Hành vi fallback bất biến; chỉ nội dung log đổi (đúng mục tiêu F7). |
| 1c | Diff **tối thiểu**, không lén sửa gì khác | `git show 7650753 --stat` = **8 file**: `scp/api_server.py`, `scp/api_server_parts/lifespan.py`, `CLOSURE-CONTRACT.md` (mới) + 5 evidence txt. Toàn bộ nằm trong `scope_files` M1. Thân diff `api_server.py` chỉ là khối log-hygiene trong `_scp_service_identity` (+9 dòng/−3 dòng); `lifespan.py` chỉ là +7 dòng binding logger. Không có thay đổi ẩn. | **XÁC NHẬN** | Diff sạch, đúng phạm vi. |
| 2 | **D6**: 0 khối `except: pass` (không log) trong 6 file phạm vi | Tự viết script AST (`.openclaw/tmp/m1_ast_scan.py`, dùng `ast.ExceptHandler` + lọc body chỉ gồm `Pass`/docstring) chạy trên đúng 6 file. Kết quả: `TOTAL_EXCEPT_PASS_ONLY=0` (0 ở cả 6 file: lifespan, background_jobs, retry_policy, api_server, run_scp_acceptance, test_flow_01). Khớp `D6-ast-scan.txt` (`CONTRACT_VIOLATIONS_EXCEPT_PASS_WITHOUT_LOG=0`, `OK ... (0 except:pass handlers)`). | **XÁC NHẬN** | Bằng công cụ độc lập (scanner khác của tôi) → 0, khớp evidence D6. 11 handler "fallback-no-log" còn lại là category khác, pre-existing, ngoài hợp đồng D6. |
| 3a | `sha_pin == git rev-parse HEAD` | `git rev-parse HEAD` = **`067e636...`** (commit `docs(M1): re-pin closure record…`), trong khi trường `"sha_pin"` của closure = **`7650753...`**. Hai giá trị **KHÁC NHAU**. `git log -- M01-closure.json` cho thấy closure record chỉ được tạo/sửa ở `067e636` và `bae6196` — **không** ở commit PIN2. `git show 067e636 --stat` chỉ chạm `reports/circuit-closures/**`. | **PHẢN BÁC** | Bằng chứng bác bỏ đẳng thức `sha_pin == HEAD` tại thời điểm này. LƯU Ý TRUNG THỰC: closure **không** tự khai HEAD==pin; nó ghi rõ trong `commit_pattern_note` + D8 note rằng bản ghi là "commit docs riêng cập nhật SAU sha_pin". Tuy nhiên điều này **vi phạm điều khoản D8** của `CLOSURE-CONTRACT.md` ("commit closure **cùng commit** đóng mạch"). Ngoài ra `067e636` chạm `reports/circuit-closures/**` — là mục nằm trong `scope_files` M1 → theo điều khoản hồi quy, commit chạm file phạm vi đáng lẽ phải chạy lại tối thiểu D1+D2+D4. |
| 3b | Các `sha256` evidence ghi trong closure khớp file trên đĩa | `Get-FileHash` (bytes worktree) cho TẤT CẢ 13 file = đúng `sha256_worktree` của closure (D1 `657f6197…`, D2 `7eb4760e…`, D3 `804ec982…`, D6-ast `84056e85…`, D6-runtime `98f4bd4a…`, D7 `19196a7c…`, D4-latest `cf9a00ef…`, D4-deepscan `fb8f180b…`, CORRECTIONS `f9765b14…`, D5 `7b76aba3…`, CLOSURE-CONTRACT `c1ee8b8b…`, FLOW-MAP `deef34bd…`, runbook `9727e3c9…`). Script LF-normalize (CRLF→LF) cho TẤT CẢ 13 file = đúng `sha256` (LF) của closure. **13/13 khớp cả hai cột.** | **XÁC NHẬN** | Không có hash sai/조작. Cơ chế dual-hash (LF vs worktree) được giải thích hợp lý ở `CORRECTIONS-AND-HASHES.md` C2. |
| 3c | Mục nào ghi **PASS** mà **KHÔNG** có bằng chứng hợp lệ | (i) **D1/D3 = PASS**: evidence là thật (35 passed / 47 passed, exit 0) nhưng chạy ở HEAD `bae6196` (parent) trên worktree bẩn, KHÔNG phải checkout sạch của PIN2 — đã tự khai trong note + known_gaps F… (ii) **D5 = PASS**: 2 reviewer độc lập chỉ review `6328d51/62afcd7` (**trước** PIN2), PIN2 **chưa** qua bất kỳ reviewer độc lập nào — note tự nêu rõ; (iii) **D2/D6/D7 = PASS**: tôi kiểm chứng được trực tiếp (xem hàng 2, 5, và TODO-scan). | **KHÔNG ĐỦ CƠ SỞ** (cho riêng nhãn D5=PASS tại PIN2) — các mục còn lại: XÁC NHẬN có giới hạn | D1/D3 có bằng chứng thật, hạn chế provenance đã khai báo → có thể chấp nhận "PASS kèm giới hạn". Nhưng dán nhãn **D5=PASS** khi PIN2 chưa có review độc lập là **khai quá (over-label)**, dẫu nội dung note minh bạch. Đúng bản chất nên là "PASS@prev-pin / PIN2 UNREVIEWED". |
| 3d | 3 known_gaps cốt lõi (D4 EVIDENCE_GAP, D2 build từ working tree, D5 PIN2 chưa review) ghi **trung thực** | (1) D4 EVIDENCE_GAP: có mặt nguyên văn trong `known_gaps` mục đầu + checklist D4 `status=EVIDENCE_GAP`; nêu đúng hook ledger `scanned_files=0, 6/6 failed, revision fe4bc8d` và deep scan `runStatus=inconclusive/completeness=partial`. (2) D2 build từ working tree: có mặt, kèm chi tiết "SHA là nhãn inject qua build arg, KHÔNG phải content digest". (3) D5 PIN2 chưa review: có mặt nguyên văn ("PIN MOI 7650753 KHONG duoc reviewer doc lap nao review lai"). | **XÁC NHẬN** | Cả 3 gap cốt lõi được ghi đầy đủ, không tô hồng. `falsification_status = PARTIALLY_FALSIFIED_AT_PIN` + `status = CLOSED_WITH_KNOWN_GAP` (không phải "CLOSED sạch") phản ánh đúng sự thật. |
| 4 | Hash 2 file mimosa hook phải khớp giá trị quy định | `Get-FileHash` tại `C:\Users\check\.zcode\cli\plugins\cache\zcode-plugins-official\mimosa\1.0.3`: `hooks\hooks.json` = **`8887077F06F206E91578961096BB4919EB04E1DA6D0B5AC11E8EA68692E75F63`** ✓; `payload\hooks\git-gate-hook.mjs` = **`7E8B5CC044EF330A3811745B9BA350FEAA3D792D9F5499B4CE746C2DAC36A941`** ✓. | **XÁC NHẬN** | Khớp chính xác cả 2 hash kỳ vọng. Việc bypass L3 gate rồi **restore byte-exact** đã được thực hiện đúng (dù bản thân hành vi bypass là ngoài repo, không thuộc commit nào — đã khai trong known_gaps). |
| 5 | `/health` container đang chạy có `service_identity.commit == PIN2` | `docker ps` → container `56dd7f8618de`, image `7f02c6d61d2c`, Up, `127.0.0.1:8000->8000/tcp`. `curl http://127.0.0.1:8000/health` → `"service_identity":{..., "commit":"765075312bdc55373a86d9c5577ac62140c7ad64", "configured_port":8000, ...}`. `/ready` → `{"status":"ready","checks":{"judge":"ok","background_scheduler":"ok"}}`. | **XÁC NHẬN** | `commit` trong /health **ĐÚNG** = PIN2. Container/image digest khớp `container_image_digest` (`7f02c6d6…`) trong closure. Boot sống, readiness ready. |

---

## Phát hiện bổ sung (ngoài các claim được hỏi)

- **E1 — Bất nhất trạng thái (minor):** 4 module header vẫn ghi `# SCP CIRCUIT: M1 Boot & Background — STATUS: **CLOSED**`, trong khi closure record và `CIRCUIT-FLOW-MAP.md`/`M01-runbook.md` ghi `**CLOSED_WITH_KNOWN_GAP**` (do D4 = EVIDENCE_GAP). Header chưa được cập nhật cho khớp. Không phải lỗi cố ý, nhưng là điểm không nhất quán cần sửa ở lần chỉnh tài liệu kế tiếp.
- **E2 — Vi phạm điều khoản D8 (đã khai):** closure record không nằm cùng commit với commit đóng mạch (PIN2), mà ở commit docs `067e636` phía sau → đi ngược "commit closure cùng commit đóng mạch" của `CLOSURE-CONTRACT.md`. Được ghi rõ trong `commit_pattern_note`/D8 note nên là minh bạch, không phải giấu.
- **E3 — `CORRECTIONS-AND-HASHES.md` C2 dùng hash CŨ:** bảng C2 liệt `lifespan.py`/`api_server.py` theo hash tại `62afcd7` (`ac47e433…`, `57b5cbac…`), không phải PIN2. Nhưng phụ lục **C6** đã ghi rõ "BẢNG HASH Ở C2 CHỈ CÒN HIỆU LỰC TẠI sha_pin CŨ 62afcd7", nguồn có thẩm quyền hiện tại là `M01-closure.json`. ⇒ Không gây hiểu lầm nếu đọc C6. (Hash PIN2 đúng là `2251ca18…` / `ac085d53…` — đã xác minh ở hàng 3b.)
- **E4 — Provenance D2/D6-runtime:** file evidence phát sinh SAU pin (buộc phải build/đo theo SHA pin), nằm trong commit `067e636`. Đã khai trong known_gaps. Không ảnh hưởng tính đúng đắn của nội dung (tôi tái xác minh được bằng mắt).
- **E5 — `D4-mimosa-deepscan.json`:** xác nhận `deep_scan_m1_scope_findings = 0`, `m1_scope_findings = []`, và `m1_scope_files_checked` liệt đúng **6 file** phạm vi. Khớp claim D4 "0 finding trong phạm vi M1". (Nhưng tổng thể scan `inconclusive` → đúng lý do KHÔNG nâng D4 lên PASS.)

---

## Kết luận reviewer

### VERDICT TỔNG: **APPROVE_WITH_LIMITS**

**Lý do (dựa trên bằng chứng tự thu, không dựa lời khai):**

Được chấp thuận vì **mọi claim kỹ thuật cốt lõi của PIN2 đều đúng và tái xác minh được độc lập**:
1. F821 `logger` đã được bind đúng (`logging.getLogger("scp.api")`, module-level) và **cùng object** với `scp.api_server.logger`; ruff F821 52→0 (tôi tự chạy, khác công cụ với scanner D6). ✔
2. Hành vi fallback port 8000 **không đổi**; diff **tối thiểu, đúng phạm vi** (8 file, không thay đổi ẩn). ✔
3. D6 "0 khối except:pass" — scanner AST **độc lập** của tôi cho 0/6 file. ✔
4. Toàn bộ **13/13** sha256 evidence (cả LF và worktree) khớp file trên đĩa. ✔
5. 2 mimosa hook **restore byte-exact** đúng hash quy định. ✔
6. `/health` đang chạy: `service_identity.commit == PIN2`; `/ready` ready/ok. ✔
7. 3 known_gaps cốt lõi (D4 EVIDENCE_GAP, D2 build từ working tree, D5 PIN2 chưa review) được ghi **trung thực, không tô hồng**; `falsification_status = PARTIALLY_FALSIFIED_AT_PIN` và `status = CLOSED_WITH_KNOWN_GAP` phản ánh đúng. ✔

**Giới hạn (lý do KHÔNG phải APPROVE sạch):**
- **L1 (PHẢN BÁC):** `sha_pin` (7650753) ≠ `git rev-parse HEAD` (067e636); closure record không nằm trong commit đóng mạch → vi phạm điều khoản D8 (dẫu đã tự khai minh bạch).
- **L2 (KHAI QUÁ):** nhãn **D5 = PASS** trong khi PIN2 **chưa** được reviewer độc lập nào review (review độc lập chỉ ở 6328d51/62afcd7). Nội dung note minh bạch, nhưng nhãn "PASS" gây hiểu nhầm mức độ hoàn thành.
- **L3:** D1/D3 có bằng chứng thật nhưng chạy trên worktree dirty ở HEAD parent, không phải checkout sạch PIN2 (đã khai).
- **L4:** D4 vẫn `EVIDENCE_GAP` (đúng, đã khai) → M1 **không thể** coi là "sạch".
- **L5 (minor):** 4 module header còn ghi `STATUS: CLOSED`, lệch với `CLOSED_WITH_KNOWN_GAP`.

**Không phát hiện:** bất kỳ bằng chứng bịa đặt, hash sai, hay thay đổi mã ngoài phạm vi. Tính trung thực của `M01-closure.json` ở mức **tốt**: các giới hạn/pin mới chưa review đều được tự phơi bày.

**Khuyến nghị (nếu muốn đóng sạch):** (1) chạy D1+D2+D4 lại trên **checkout sạch của PIN2** và tạo D5 **mới** cho chính PIN2; (2) đưa closure record vào **cùng commit** đóng mạch theo D8; (3) sửa header 4 module về `CLOSED_WITH_KNOWN_GAP`.

---

### Phụ lục — Lệnh/bằng chứng thô đã dùng (read-only)
- `git rev-parse HEAD` → `067e636216977c420e79811ebe4e75bd1c7bc05d`
- `git show 7650753 --stat` → 8 file (2 .py + 6 reports/circuit-closures/**)
- `Get-FileHash -Algorithm SHA256` (13 evidence + 6 scope file + 2 mimosa hook)
- `py -3.12 -m ruff check --select F821` (api_server.py, lifespan.py worktree, lifespan.py @PIN2, lifespan.py @bae6196 → 52 errors)
- Script AST độc lập: `.openclaw/tmp/m1_ast_scan.py` → `TOTAL_EXCEPT_PASS_ONLY=0`
- Script LF-normalize: `.openclaw/tmp/lf_hash.py` → 13/13 khớp `sha256` LF
- `Select-String 'TODO|FIXME|XXX'` (6 file) → 0 matches
- `docker ps` → `56dd7f8618de` image `7f02c6d61d2c` (127.0.0.1:8000->8000/tcp)
- `curl /health` → commit `765075312bdc55373a86d9c5577ac62140c7ad64`; `curl /ready` → ready/judge=ok/background_scheduler=ok
