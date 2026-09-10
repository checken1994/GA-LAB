# D5 — Independent review digest (M1 Boot & Background)

Cực kỳ quan trọng: đây là **digest** do bên được review tự tổng hợp từ output của 2 reviewer, **không phải**
bản ghi nguyên văn. Full transcript của 2 subagent nằm trong session log của ZCode (session
`sess_59cd1d3c-1419-4a90-9164-7120c1262090`), **không** được lưu thành file trong repo. Điều này tự nó là
một giới hạn provenance: nếu cần bằng chứng nguyên văn, phải export từ session log.

Hai reviewer chạy song song, **read-only**, cùng repo, cùng HEAD `62afcd707ea94ffc72ab755232b29eddad69b8d3`,
không chia sẻ ngữ cảnh với chuỗi fix (khác agent, khác phiên suy luận). Mỗi reviewer tự viết công cụ riêng
(reviewer 1 viết scanner AST độc lập; reviewer 2 tự parse `findings.json` gốc và tự chạy lại pytest).

| | Reviewer 1 — `m1_static_verifier` | Reviewer 2 — `m1_dod_auditor` |
|---|---|---|
| Nhiệm vụ | Bác bỏ 6 tuyên bố T1–T6 về code/evidence | Kiểm đầy đủ + tự nhất hồ sơ D0–D8 |
| Verdict | **APPROVE_WITH_LIMITS** | **REJECT** (cho tuyên bố "M1 CLOSED") |

## Reviewer 1 — kết quả

| # | Tuyên bố | Kết quả |
|---|---|---|
| T1 | 6 khối `except: pass` → log, hành vi không đổi | **ĐÚNG (có caveat)** — pre=6, post=0 pass-only; multiset exception type không đổi; 11 fallback-handler còn lại là pre-existing, đúng như D6 tự disclose |
| T2 | 0 TODO/FIXME/XXX | **ĐÚNG** |
| T3 | Header đúng định dạng ở 4 module | **ĐÚNG về định dạng** (`lifespan.py:2`, `background_jobs.py:1`, `retry_policy.py:2`, `api_server.py:1`); **SAI về artifact dẫn chiếu** lúc audit (closure record chưa tồn tại) |
| T4 | T01 exit 0 | **ĐÚNG** — `35 passed in 7.76s`, exit 0 |
| T5 | Commit 62afcd7 chỉ chứa file trong scope | **ĐÚNG** — 12 file, out-of-scope = 0 |
| T6 | File phạm vi trùng byte với pin | **SAI theo byte thô** (12/16 lệch sha256, chỉ do CRLF↔LF), **ĐÚNG theo nội dung** (14/14 chuẩn hoá EOL bằng nhau; `git diff --exit-code` = 0) |

Phát hiện phản bác: **F1** thiếu closure record + D4 EVIDENCE_GAP mâu thuẫn nhãn CLOSED (CAO);
**F2** `logger` là F821 trong `lifespan.py`, gồm dòng mới — chỉ sống nhờ rebind của `api_server.py` (TRUNG BÌNH–CAO);
**F3** evidence D1/D3/D6/D7 ghi `git HEAD at run` = parent, không phải pin (TRUNG BÌNH);
**F4** D2 chưa được commit (TRUNG BÌNH); **F5** D2 build từ worktree bẩn, SHA là nhãn inject (TRUNG BÌNH);
**F6** 1/6 log ở mức DEBUG nên vô hình ở mức INFO mặc định (THẤP); **F7** log dùng `%r` cho giá trị env (THẤP);
**F8** noise OTEL exporter sau pytest (THẤP); **F9** 11 fallback-handler còn lại (INFO).

## Reviewer 2 — kết quả

Gap xếp mức độ (nguyên văn bảng của reviewer): **G1 BLOCKER** không có `M01-closure.json`;
**G2 BLOCKER** D4=EVIDENCE_GAP mâu thuẫn CLOSED; **G3 HIGH** D2 chưa commit; **G4 HIGH** lệnh ghi trong D2.8
không tái lập output; **G5 HIGH** D1/D3 chạy ở HEAD trước pin và phụ thuộc `tests/conftest.py` chưa commit;
**G6 HIGH** không có artifact D5 độc lập; **G7 MEDIUM** image build từ tree bẩn, nhãn "SHA-pinned" quá mạnh;
**G8 MEDIUM** sha256 evidence là bytes CRLF nên lệch blob pin; **G9 MEDIUM** evidence được tạo trong lúc audit;
**G10 LOW** `6328d51` chạm `reports/expert-panel/` ngoài whitelist; **G11 LOW** tắt L3 gate không có artifact
phê duyệt trong repo; **G12 LOW** không có spec D0–D8 / STATUS-LEDGER, còn rác `.tmp-m1-t01-run1.txt`,
"số 194 HIGH" không khớp scan thật.

Reviewer 2 ghi nhận các điểm trung thực: D4 verdict EVIDENCE_GAP nêu đúng và đủ số liệu; D6 AST scan tái lập
khớp 100%; D7 khớp; D1/D3 số pass khớp; D2 tự phơi limitation ở D2.9; ghi chú "grep quirk" trong D2.7 là thật.

## Xử lý sau review (do bên đóng mạch thực hiện)

| Gap | Xử lý trong commit closure |
|---|---|
| G1 / F1 (closure record) | Tạo `M01-closure.json` (commit này) |
| G2 / F1 (mâu thuẫn CLOSED) | Đổi trạng thái M1 → `CLOSED_WITH_KNOWN_GAP` ở `CIRCUIT-FLOW-MAP.md` + `M01-runbook.md` + closure record |
| G3 / F4 (D2 chưa commit) | Commit `D2-docker.txt` (commit này) |
| G4 (lệnh D2.8 sai) | Đính chính ở `CORRECTIONS-AND-HASHES.md` C1, chạy lại cả hai lệnh |
| G8 / T6 (CRLF hash) | Ghi cả `sha256_worktree` và `sha256_lf` trong `CORRECTIONS-AND-HASHES.md` C2 + closure record |
| G5 (D1/D3 không tái lập từ pin) | Ghi vào `known_gaps` (không thể sửa: `tests/conftest.py` thuộc mạch khác, ngoài scope lock) |
| G6 (thiếu D5) | Chính digest này — 2 reviewer độc lập, read-only |
| G7 / F5 (image từ tree bẩn) | Giữ nguyên D2.9 + ghi `known_gaps` |
| G9 | Ghi `commit_pattern_note` (D2 buộc phải chạy sau pin) |
| G10 / G11 / G12 | Ghi `known_gaps` |
| F2 (F821 logger) | Ghi `known_gaps` + `CORRECTIONS-AND-HASHES.md` C3 (không sửa để giữ pin) |
| F3 | Ghi `known_gaps` |
| F6 / F7 / F9 | Ghi `known_gaps` (chủ đích / pre-existing / ngoài hợp đồng) |

Các gap **không** xử lý được trong phạm vi này vẫn giữ nguyên trong `known_gaps`. Việc reviewer 2 verdict
`REJECT` được giữ nguyên trong closure record — không được xoá hoặc làm mềm.
