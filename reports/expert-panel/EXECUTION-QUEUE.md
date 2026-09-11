# EXECUTION QUEUE — Owner directive 2026-09-11

> "Không cần báo plan. Làm đến khi toàn bộ mạch và 190 lỗi được đóng thì báo cáo 1 lần."
> Chế độ: tự động hoàn toàn, KHÔNG hỏi giữa chừng, agent dispatch SERIAL (account giới hạn 1 agent nền).
> Mọi dispatch: run_in_background=true + no-mock + Docker verify + PIPESTATUS discipline.

## Trạng thái mạch (theo STATUS-LEDGER + tiến độ thật)

- M1: CLOSED_WITH_KNOWN_GAP @ pin 7650753 (closure record D0–D8) ✅
- M2: fixes done + test 34/34 (1a) — CÒN: runtime probe + pin SHA + closure record
- M3,M4,M6,M10,M12: D1_FAIL (7/7/6/5/10 test đỏ) — cần fix
- M5,M7,M8,M9,M11,M13,M14: D1_PASS__NOT_CLOSED — cần runtime probe + closure record

## QUEUE BẢO MẬT (HIGH→0)

| # | Việc | Scope | Trạng thái |
|---|---|---|---|
| S2 | SSRF runtime/ + wiremixin FP 6 | scp/runtime/ + autofix/evolution_parts/wiremixin.py | ĐANG CHẠY |
| S1b | SSRF nốt 29 điểm | scp/data_sources/ + scp/core/ (trừ url_fetcher/api_utils implementation) | CHỜ S2 |
| S3 | path-traversal ~20 + SQLi ~10 + deser 5 + code/cmd-injection 3 + cert 2 | scp/autofix/ | CHỜ |
| S4 | SQLi taskkernel ×2 + core/ (partition/archive, startup_optimizer, smart_cache, storage_manager) + benchmark/ + scripts/ SQLi 6 | scp/core/, scp/task_kernel_parts/, benchmark/, scripts/ | CHỜ |
| S5 | code-injection round9.ts + health route ×4 + llm-bridge core.ts | dashboard/, mini-services/ | CHỜ |
| R1 | Mimosa full rescan → HIGH=0 (fix sót nếu có) | — | CHỜ |
| C1 | Commit toàn bộ (gate mở): sweeps + M2 + circuit-closures staged 22 files | — | CHỜ |

## QUEUE MẠCH (sau khi HIGH=0)

| # | Việc | Trạng thái |
|---|---|---|
| MC2 | M2 closure: runtime probe Docker + pin SHA + closure record D0–D8 | CHỜ |
| MC3 | M3 OpenAI-compat: fix 7 test đỏ (auth-first contract + mock API) → closure | CHỜ |
| MC4 | M4 Control & Hands: fix 7 test đỏ → closure | CHỜ |
| MC6 | M6 Prediction: fix 6 test đỏ → closure | CHỜ |
| MC10 | M10 Streaming: fix 5 test đỏ → closure | CHỜ |
| MC12 | M12 Background WHY: fix 10 test đỏ → closure | CHỜ |
| MC5/7/8/9/11/13/14 | 7 mạch xanh: runtime probe + closure record từng mạch | CHỜ |
| FINAL | Full pytest + Mimosa final scan + bật lại gate + BÁO CÁO DUY NHẤT | CHỜ |

## Quy tắc không đổi
- **MANDATORY SKILL BINDING CHO MỌI AGENT (owner bắt 2026-09-11) — PHẢI FALSIFIABLE, khai báo suông = vô giá trị (owner probe: "không chạy skill = không khác gì không chạy?"):**
  - (1) **Receipt máy đọc được**: dispatch record + progress log PHẢI ghi SHA256 của từng SKILL.md agent đã Read (convention AGENTS.md đã có cho release gate — mở rộng cho mọi agent). Thiếu hash = coi như không chạy skill.
  - (2) **Behavioral markers**: report phải có cấu trúc do skill quy định — verdict theo nhãn (OBSERVED/SUPPORTED_INFERENCE/UNPROVEN hoặc A/B/C/D evidence), mỗi fix có rollback path, open questions cuối, lý do no-mock. Thiếu marker = skill chưa áp dụng = REDO bất kể khai báo gì.
  - (3) **Verifier test ngược**: Agent V phải kiểm tra ngẫu nhiên ≥2 nguyên lý trên work thật (vd "mỗi fix có rollback?" — "PASS có bị mở rộng vượt scope?"). Vi phạm nguyên lý = work đó bị coi là sản phẩm của agent KHÔNG chạy skill → REDO.
  - Mapping skill: security sweep → scp-capability-security-review + scp-reality-verifier; circuit closure → scp-runtime-audit + scp-release-evidence-gate; fix learning/autofix → scp-learning-loop-guard; kernel → scp-task-kernel-review. Luôn + scp-dna.
- **ORCHESTRATOR KHÔNG TỰ SỬA CODE** (owner nhắc lại 2026-09-11): mọi fix qua worker agent; MỌI thay đổi — kể cả do orchestrator sửa inline (5 file: taskkernel, path_guard, speculative_branching, archive, startup_optimizer) — phải qua verifier agent độc lập (review diff + pytest) trước khi tính. Verifier là người khác worker.
- **NO-MOCK MỞ RỘNG (owner chốt 2026-09-11)**: (a) cấm mock trong fix/test mới; (b) khi chạm test cũ có mock → un-mock thành integration thật nếu khả thi; (c) mỗi mạch closure phải un-mock ít nhất các mock che logic cốt lõi của mạch đó (chuẩn Mạch 2 đã làm với DoubtCron). Mock chỉ còn được phép ở: fixture env (monkeypatch.setenv), timing, và server-fixture dữ liệu.
- No skip/xfail/weaken; sửa PRODUCT tại điểm lỗi.
- Mỗi mạch closure: D0–D8 + pin SHA + record vào reports/circuit-closures/ (mẫu M01).
- Progress logs: reports/expert-panel/<agent>.md.
- Test đỏ = điều tra root cause; product bug → sửa product; harness lỗi thật → sửa harness tăng strictness.
- Báo cáo duy nhất ở cuối: verdict từng mạch + HIGH trước/sau + evidence chính.
