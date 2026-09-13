# C-S2 — World-State Hook Fix (`/ask` → `evidence_refs=[run_id]`)

Agent: SCP Worker **C-S2** (no-commit). Ngày: 2026-09-13.
Repo: `C:\Users\check\Downloads\scp` — branch `audit/runtime-guard-AUDIT-20260909`, HEAD `d4d8cf0cc503d071d05332a34169caf110422574` (không đổi trong suốt task).

## Claim được kiểm chứng

Arch audit 52-mảnh @9ec8d6b (commit `e0696f5`): world_state hook trong
`scp/api_server_parts/_ask_impl.py` raise ở MỌI judge PASS và bị nuốt ở mức
warning → `world_state` không bao giờ nhận record từ `/ask`.

## Scope

| Trường | Giá trị |
|---|---|
| Commit/snapshot | `d4d8cf0` + working tree (không commit) |
| Test profile | pytest T02_contract (156 test) + 3 test mới |
| Input/task | POST `/ask` thật qua FastAPI TestClient + fixture provider HTTP cục bộ |
| Thời điểm | 2026-09-13 |

## Root cause (AUDIT-FIRST, evidence)

Hook cũ (`_ask_impl.py` @HEAD, block "3. World State"):

- Gọi `_eea.record_event(..., evidence_refs=[], actor_id="scp-judge")`.
- `EntityEventAuthority.record_event` → `TemporalAuthority.record_observation`
  với default `epistemic_status="OBSERVED"`.
- `scp/world_state/temporal_authority.py:91-92`:

  ```python
  if epistemic_status == "OBSERVED" and not evidence_refs:
      raise WorldStateError("OBSERVED assertion requires evidence_refs - unaudited world writes are forbidden")
  ```

→ `WorldStateError` raise ở **mọi** PASS, bị `except Exception` + `logger.warning`
bắt (fail-open cho /ask nhưng write KHÔNG BAO GIỜ thành công). Nguyên nhân là
**schema mismatch có chủ đích của store** (hợp đồng X08 cấm world write không
audited), không phải store chưa init hay API signature sai.

## Sửa tại điểm lỗi (smallest reversible patch)

`scp/api_server_parts/_ask_impl.py` — 1 hunk duy nhất (không đụng file khác):

1. Lấy provenance thật của run: `request.state.scp_run.run_id` — được
   `traced_request` (api_server.py:499) gắn vào request, cùng cơ chế mà
   `stage_request` đã dùng; chính là run_id mà HTTP response mang về.
2. `evidence_refs=[_ask_run_id]` → write đạt hợp đồng X08, thành công.
3. Nếu không có run_id (boundary không gắn ledger): KHÔNG bịa evidence — skip
   write + `logger.warning` "world write skipped (unaudited world writes are
   forbidden)". (Branch này được hợp đồng store bảo vệ — nếu truyền `[]` sẽ raise
   WorldStateError; hiện tại là skip chủ động có log.)
4. Store lỗi → vẫn `except` + `logger.warning '[RESTORED-SYSTEMS] world_state
   hook failed: ...'` — fail-open cho hook phụ, /ask không hỏng, lỗi bắt buộc
   quan sát được (không nuốt im lặng).

Rollback: revert 1 hunk trong `_ask_impl.py` + xóa test file mới.

## Test mới — `tests/T02_contract/test_ask_world_state_hook_cs2_scp_standard.py`

Real pipeline (FA-04): fixture chỉ là env/config + HTTP provider cục bộ; store,
judge, ledger, gateway transport là code production.

| Test | Kiểm chứng | Kết quả |
|---|---|---|
| `test_ask_pass_records_world_state_event_with_run_id` | (a)+(c) POST `/ask` thật (auth JWT, judge ready) → 200, response có `run_id`; đọc `world_state.sqlite` **độc lập bằng sqlite3**: tồn tại row `subject=entity:ask_session`, `predicate=event:pass_verdict`, `evidence_refs_json == [run_id]`, `epistemic_status=OBSERVED`, `actor_id=scp-judge`; happy path KHÔNG log "world_state hook failed" | PASS |
| `test_ask_world_state_store_error_fail_open_with_warning` | (b) `EntityEventAuthority.record_event` raise → `/ask` vẫn 200 với verdict chuẩn + warning `[RESTORED-SYSTEMS] world_state hook failed` mang đúng lỗi store (không nuốt im lặng) | PASS |
| `test_ask_pass_without_run_id_is_refused_by_store_contract` | Provenance guard: drive **rebound `_ask_impl`** (globals api_server thật) bằng Starlette Request thật không có `scp_run` → warning "world write skipped" + KHÔNG có `world_state.sqlite` (không bịa evidence) | PASS |

## Lệnh chạy + kết quả ( Reality evidence)

```
python -m pytest tests/T02_contract/test_ask_world_state_hook_cs2_scp_standard.py -q
→ "3 passed in 17.44s", EXIT=0

python -m pytest tests/T02_contract/ -q --deselect "tests/T02_contract/test_flow_02_ask_chat_scp_standard.py::TestFlow02WebSocketChat::test_ws_chat_fail_closed_when_no_answer_source_available"
→ "156 passed, 1 deselected in 82.18s", EXIT=0

python tools/t00_meta_audit.py
→ "[T00 Meta-Audit] All integrity checks passed (0 new regressions)", EXIT=0
```

## Deselect (ngoại lệ được duyệt — ghi rõ)

- `test_ws_chat_fail_closed_when_no_answer_source_available` là RED
  **pre-existing environmental** (đã được S20d chứng minh trước task này).
- Lưu ý kỹ thuật: node-id deselect trong brief
  (`...::test_ws_chat_fail_closed_...`) **thiếu class** `TestFlow02WebSocketChat::`
  nên pytest không match, test vẫn chạy. Run đầu với node-id đúng của test đó:
  `1 failed, 156 passed` — failure Y HỆT dạng đã ghi khi chạy **đơn lẻ, độc lập
  với file test mới** (`1 failed in 2.26s`, assertion `get_gateway()._provider_chain("chat")`
  chứa groq/cerebras/nvidia... do .env thật leak vào provider chain — không liên
  quan diff của C-S2 vì diff chỉ là 1 hunk world_state hook). Run sau với
  **node-id đầy đủ** → `156 passed, 1 deselected`, EXIT=0.

## Postconditions

| Điều kiện | Quan sát | Verdict |
|---|---|---|
| Hook ghi record world_state khi PASS | row SQLite với `evidence_refs == [run_id]`, khớp `run_id` response | VERIFIED (integration) |
| `run_id` provenance khớp response | equality test trong CS2-WS-1 | VERIFIED |
| Store lỗi → /ask 200 + warning | CS2-WS-2 | VERIFIED |
| Không raise trên happy path | CS2-WS-1 (record tồn tại + 0 hook-failure warning) | VERIFIED |
| Không bịa evidence khi thiếu run_id | CS2-WS-3 (không DB file + warning) | VERIFIED |
| t00_meta_audit không regression | exit 0, "0 new regressions" | VERIFIED |

## Limitations (chưa chứng minh)

- **Container runtime proof (cấp D/đầy đủ cấp C containerized): BỎ theo ngân
  sách.** Container `scp-scp-api-1` chạy code bake trong image, KHÔNG bind-mount
  source (compose volumes chỉ mount data) → patch chưa nằm trong container;
  rebuild + restart vượt 10 phút và sẽ phá container chung mà agent B-S1 đang
  dùng song song. `docker logs` grep "world_state hook failed" = 0 hit →
  INSUFFICIENT (container chưa từng serve judge-PASS trong giờ qua — không suy
  diễn gì từ 0 hit).
- Mức bằng chứng đạt được: **B (integration)** — toàn bộ stack thật trong process
  (FastAPI + traced_request + adapter + judge + gateway transport HTTP thật +
  SQLite store thật), postcondition đọc độc lập từ file SQLite. Không thay thế
  cho runtime proof trong Docker.
- Diff của C-S2 không bao gồm các file đangModified khác trong working tree
  (`admin_v100.py`, `domain_store.py`, `judge.py`, `tests/T07_learning/...`) —
  đó là working tree của agent B-S1 song song; T02_contract đã PASS trên tổng
  thể working tree hiện tại.

## git diff --stat (phần C-S2)

```
 scp/api_server_parts/_ask_impl.py | 46 ++++++++++++++-------
 tests/T02_contract/test_ask_world_state_hook_cs2_scp_standard.py | 422 ++++++++++++++
```

(`_ask_impl.py`: đúng 1 hunk — world_state hook. File test mới: 422 dòng.)

(Working tree còn chứa edit của B-S1: `admin_v100.py`, `knowledge/domain_store.py`,
`runtime/judge.py`, `tests/T07_learning/test_judge_knowledge_wire.py` — ngoài phạm vi C-S2.)

Không `git add`/`git commit` đã thực hiện (no-commit đúng quy trình).

## Skill binding — SHA256

| File | SHA256 |
|---|---|
| `.agents/skills/scp-dna/SKILL.md` | `4aada0be4873598dc50c3a7f38d90151429bb5263c511a838ed1cdcb4d594d10` |
| `.agents/skills/scp-reality-verifier/SKILL.md` | `a9d65ce53b18f8310ceeb302b18b341a0e1b8b19cddc7f46d4fa6ee99432269e` |

## Final verdict

**VERIFIED_WITHIN_SCOPE**: world_state hook giờ ghi `evidence_refs=[run_id]`
thành công trên judge PASS qua `/ask` thật; store lỗi fail-open có log; không
raise trên happy path; T02_contract 156/156 (1 deselected environmental, lý do
đã ghi) + t00_meta_audit exit 0. Không tuyên bố "hết lỗi hệ thống" — còn hạn chế
container runtime proof như mục Limitations.
