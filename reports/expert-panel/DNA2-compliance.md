# Agent DNA-2 — Compliance DNA/Skill Log

Chiến dịch compliance (tiếp nối DNA-1): **Part A** — M12 G2b multi-source empty-PASS
violation (DNA #22, open item #1 của DNA-1) + **Part B** — records/docs hygiene
(F1–F5 + D7 + flow map refresh).

## Mandatory skill bindings (SHA256)

| Skill | SHA256 |
|---|---|
| `.agents/skills/scp-dna/SKILL.md` | `4aada0be4873598dc50c3a7f38d90151429bb5263c511a838ed1cdcb4d594d10` |
| `.agents/skills/scp-reality-verifier/SKILL.md` | `a9d65ce53b18f8310ceeb302b18b341a0e1b8b19cddc7f46d4fa6ee99432269e` |
| `.agents/skills/scp-runtime-audit/SKILL.md` | `63680fd1f1826b967f0c71367836ce0c773894f21bbf8abb33d43b005184851f` |
| `.agents/skills/scp-release-evidence-gate/SKILL.md` | `81b2cc0e3b3be91d7780a28b5fd8a4757f05cb46fba33eab9904e056cba63ce6` |

DNA áp dụng: #22 (PASS ≠ TRUE — trọng tâm Part A), #12 (small reversible), #26
(reality authority), #23/#25 (open questions / missing pieces).

## Scope

| Trường | Giá trị |
|---|---|
| Branch / base | `audit/runtime-guard-AUDIT-20260909` @ `3a36b32` (HEAD lúc nhận task) |
| Thời điểm | 2026-09-12 |
| Test profile | `python -m pytest` (pytest.ini, basetemp = system temp) |
| Input (Part A) | `ai_answer=""` qua `execute_pending_plans` + 2 agreeing sources non-empty |

## Part A — M12 G2b: multi-source empty evidence auto-PASS (DNA #22)

- File: `scp/meta/why_execute_plan.py`, hàm `execute_plan`, nhánh multi-source
  (sau fix của DNA-1): `if list(unique)[0] in ai_val or ai_val in list(unique)[0]`.
- Contract TRƯỚC: `ai_val=""` → `"" in agreed_val` vacuously True → **PASS** với
  2 agreeing sources; ngược lại set source đồng thuận rỗng (`unique == {""}`) →
  `"" in ai_val` → PASS với bất kỳ answer nào. Đây chính là open item #1 trong
  `DNA1-compliance.md` (Limitations).
- Contract SAU (giống hệt DNA-1 single-source): `if not agreed_val or not ai_val:`
  → `UNKNOWN`, conf 0.0, reason `empty_evidence: cannot verify — …`; match thật
  giữ nguyên PASS `min(0.95, threshold + 0.1)`.
- Test pin sửa: `tests/T03_capability/test_flow_12_background_why_scp_standard.py`
  :: `test_why_engine_verifies_past_decisions` — expectation đổi `PASS` →
  `UNKNOWN` + assert `empty_evidence` qua re-execute trực tiếp (STRICTNESS TĂNG,
  khai báo trong docstring test). Thêm test mới
  `test_why_engine_multisource_real_match_still_passes` (control, không
  over-tighten): 2 agreeing sources + answer thật `Temperature=31.0°C…` → PASS.

### Evidence chain

| Bước | Evidence | Kết quả |
|---|---|---|
| Repro pre-fix | flow_12 pin cũ dòng `# 2 agreeing sources, empty answer -> PASS` | violation có sẵn trong test pin |
| Post-fix background path | `execute_pending_plans` (truyền `ai_answer=''`) | row verdict = UNKNOWN, executed_at ghi đủ |
| Post-fix reason | `execute_plan(plan, ai_answer="")` trực tiếp | `empty_evidence: cannot verify — ai_answer is empty/whitespace-only` |
| Control post-fix | 2 sources agreeing + answer thật | PASS (không over-tighten) |
| flow_12 suite | 28 test cũ + 1 control mới | **29 passed, EXIT=0** (commit `4f451df`) |

## Part B — Records/docs hygiene

| Mục | Việc | Commit |
|---|---|---|
| F1 | `M01-closure.json`: thêm block `skill_binding` (4 skill SHA256, giống M02–M14) — JSON round-trip byte-identical (CRLF) trừ insertion; ghi rõ đây là **backfill 2026-09-12**, không có bằng chứng đọc skill tại thời điểm đóng M1 | `c5a6838` |
| F2/F3 | `M02-runbook.md`, `M03-runbook.md`, `M04-runbook.md` tạo mới — nội dung chỉ trỏ evidence có thật trong MXX-evidence + closure records (con số D1/D2/D3 lấy nguyên từ evidence files) | `c5a6838` |
| F3 | `M08-closure.json` G4: ref `data/deep_audit_results.jsonl` → thêm chú thích *runtime artifact in container, not persisted in repo* (reality check: `data/` bị gitignore `**/data/`, file chưa bao giờ git-tracked); `M12-closure.json`: `doubt_ledger.jsonl` / `why_gate_audit.jsonl` (status_note + D3 result) được gắn cùng chú thích | `ee5d038` |
| F4 | `M08-closure.json` status_note: `(egress deny)` → `(external LLM thật chưa chứng minh —见 M13 falsification: egress deny không chặn urllib)` — trung thực với M13 falsification #2 | `ee5d038` |
| F5 | `M13-closure.json` D1 note: disclosure mock seam GitHub — fetch catalog ở D1 chạy qua seam `transport` (`fetch_mock` MagicMock, CAT-4/CAT-5 + lambda mock CAT-1; không test D1 nào fetch GitHub thật); fetch external THẬT duy nhất được chứng minh là D3 probe P6 (top-systems, records=3, deep_readmes=1) | `ee5d038` |
| D7 | Header `# SCP CIRCUIT: MXX — STATUS: CLOSED_WITH_KNOWN_GAP (closure: reports/circuit-closures/MXX-closure.json)` thêm vào **69** file scope .py của M02–M14 (theo scope_files từng closure record; bỏ test/dashboard/mini-services; bỏ 2 file đã có header M01: `scp/api_server.py`, `scp/api_server_parts/lifespan.py`). Byte-exact insertion (không rejoin EOL — file `request_run_ledger.py` blob gốc CRLF), 69/69 file `py_compile` OK, `git diff --numstat` = 69 × (+1/−0). Overlap 2 file dùng chung: `v105_routes.py`→M03 (cũng trong M07), `helpers.py`→M02 (cũng trong M12) | `514f1c9` |
| Flow map | `CIRCUIT-FLOW-MAP.md` (bản working trong repo) refresh 14 mạch theo STATUS-LEDGER + closure records — tất cả `CLOSED_WITH_KNOWN_GAP` tại pin riêng; ghi DNA-2 update note + nghĩa vụ D2/D4 còn nợ sau commit D7. Bản V4 gốc ngoài repo (.gemini) không đụng | commit cuối |

### D7 — hệ lụy regression clause (khai rõ)

Commit `514f1c9` **chạm file phạm vi** của M02–M14 ⇒ theo regression clause của
từng closure record, phải chạy lại tối thiểu D1+D2+D4 cho từng mạch. Đã chạy lại:
D1 của M12 + M02 (63 passed, exit 0). **D2 (rebuild Docker + /health) và D4
(Mimosa scan) CHƯA chạy lại — còn nợ owner**; header M1 giữ nguyên để không vô
hiệu hoá thêm pin `7650753` (M01 reviewer_limits L5).

## Commits

| Commit | Nội dung |
|---|---|
| `4f451df` | fix(M12): multi-source empty evidence must not PASS (DNA #22) — product + pinned test corrected |
| `c5a6838` | docs(closure): M01 skill_sha256 + runbooks M02-M04 (F1-F3) |
| `ee5d038` | docs(closure): honest refs M08/M12/M13 (F4-F5) |
| `514f1c9` | chore(D7): WIRED/CLOSED headers on circuit scope files |
| (commit cuối) | docs(closure): CIRCUIT-FLOW-MAP refresh + DNA-2 compliance log |

## Final pytest (mandate gate)

`python -m pytest tests/T03_capability/test_flow_12_background_why_scp_standard.py
tests/T02_contract/test_flow_02_ask_chat_scp_standard.py -q` → **63 passed, exit 0**
(chạy trước commit D7 và sẽ chạy lại tại HEAD cuối).

## Limitations / Open items (DNA #23, #25)

1. **D2/D4 re-run còn nợ** cho các mạch bị commit D7 chạm file phạm vi (xem trên).
   Cho tới khi đó, các pin M02–M14 ở trạng thái "đã bị commit sau chạm scope, D1
   đã re-run, D2/D4 chưa" — không được đọc là pin còn nguyên hiệu lực D2/D4.
2. Header M01 vẫn ghi `STATUS: CLOSED` (không sửa — đúng theo mandate "đã có →
   bỏ qua" và M01 L5); lệch với trạng thái authoritative `CLOSED_WITH_KNOWN_GAP`
   vẫn là gap đã ghi trong `M01-closure.json`.
3. Part A PASS_WITHIN_SCOPE: fix + test gắn với commit `4f451df` + pytest profile
   trên; không xác nhận hành vi runtime của background loop trong container.
4. Không đụng: GA.md, dashboard/, mini-services/, 4 file WIP đã land, stash,
   bản CIRCUIT-FLOW-MAP V4 ngoài repo.
