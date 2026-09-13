# SCP — Compliance Mapping (NIST AI RMF · OWASP Agentic 2026 · OpenAI Agentic Practices)

> Áp dụng cho: SCP 14.0.0 · HEAD `5aed398` (branch `audit/runtime-guard-AUDIT-20260909`)
> Mỗi control: SCP subsystem → control family ngành → bằng chứng (file:test/scan seal).
> Nguyên tắc: chỉ ghi những gì CÓ bằng chứng trong repo; gap ghi tường minh.

## C.1 NIST AI RMF 1.0 + SP 800-53

| SCP subsystem | NIST / SP 800-53 control | Bằng chứng (file:test/scan) | Trạng thái |
|---|---|---|---|
| `SCP_EGRESS_MODE` + `enforce_egress_policy` (choke point `url_safety.py`) | SP 800-53 **AC-3 / AC-4** (Access Enforcement / Information Flow Control) | `scp/security/url_safety.py` (`enforce_egress_policy`, `EgressDeniedError`); container proof: deny chặn example.com (M13-evidence `EE-egress-container-reversal.txt`); static gate `tests/T03_capability/test_egress_enforcement.py::test_g_*` | ✅ ENFORCED |
| TaskKernel state machine + OCC + lease fencing | **AC-2 / AC-25** (account/reference monitor — luôn qua PEP, không bypass) | `scp/task_kernel_parts/taskkernel.py`; parity 15/15 SQLite↔PG (`tests/T04_kernel/test_pg_storage_parity.py`); FA-05 test: 0 kernel row khi deny (`test_mcp_server.py::test_hands_execute_without_capability_token_denied_by_bridge_pep`) | ✅ |
| Kill switch + rollback + recovery | **IR-4 / CP-10** (Incident Response / System Recovery) | `scp/pc_control/pc_controller.py` kill switch; chaos: kill connection giữa transaction — instance mới recovery sạch (`test_pg_storage_chaos.py::test_a*`); W2 R3: kill -9 → breaker mở + recovery 21s | ✅ |
| Evidence gates T00 + FA-03 (guardrails) | **CA-7 / AU-6** (Continuous Monitoring / Audit Record Review) | `.github/workflows/` L3 T00 tripwire + guardrails; `tools/t00_meta_audit.py`; CI L3 SUCCESS trên PR | ✅ (L3) |
| Self-audit / self-repair (autofix + verified_fix) | **CA-2 / CA-5** (Control Assessment / Remediation) | `scp/autofix/engine.py` + deterministic_worker + sandbox evaluator (`scp/sandbox_evaluator/evaluator.py`, E2E `test_sandbox_evaluator_e2e.py`); rollback fail-closed | ⚠️ CAVEAT: `evidence_replay.py` là stub (luôn VERIFIED) — FA-04 disclosed, cần build thật trước khi claim |
| Postgres durability + event bus | **CP-9** (System Backup) / AU (audit trail) | `scp/kernel_storage_pg.py` + `scp/event_bus_pg.py`; parity 15/15; chaos backup round-trip pg_dump (`test_pg_storage_chaos.py::test_d*`) | ✅ |
| Retention / drift guard | **CM / SI** (Configuration Management) | `scp/governance/` drift_guard semantic AST (`drift_guard.py:153-192`) | ✅ (design) |

## C.2 OWASP Top 10 Agentic Applications (2025/2026)

| Rủi ro OWASP | SCP control | Bằng chứng / Gap | Trạng thái |
|---|---|---|---|
| **LLM01 Prompt Injection** | Red-team suite + jailbreak block; hidden-instruction probing | `scp/security/red_team.py`; benchmark attacks: dan/prompt_injection/encoded/role_play — **attack resistance 100%** (4/4 BLOCKED, seed 42, `bench_w2_seed42.json`) | ✅ đo được (thống kê trên N nhỏ) |
| **LLM02 Sensitive Disclosure** | PII/secret redaction + traversal guards | sweep S1–S6: 0 raw fetch; `bypass_encrypt.py` fail-closed (A1); gitignore secrets | ✅ |
| **LLM03 Supply Chain** | Lockfile + pin + advisory | `scp/requirements.lock.txt` (54 pins, diff container = rỗng); ⚠️ online advisory scan chưa chạy | ⚠️ một phần |
| **LLM04 Data/Model Poisoning** | Knowledge quarantine + contradiction authority | `scp/knowledge/` quarantine; ⚠️ **chưa có poisoning dataset test** (gap thật) | 🔴 GAP |
| **LLM05 Improper Output Handling** | Sandbox Evaluator + fail-closed verdicts | `scp/sandbox_evaluator/` (E2E 18P); stdout/stderr raw trả về, gate chốt | ✅ |
| **LLM06 Excessive Agency** | Capability PEP + tier3 approval + token scopes + FA-05 ordering | `test_flow_04` (58P, kernel mutation 0 khi deny); MCP `test_mcp_server.py` (FA-05 test) | ✅ |
| **LLM07 System Prompt Leakage** | Withheld answers khi verify FAIL | `ask_kernel_adapter.py` withheld (`bench_w2_seed42.json`: 13/13 FAIL = withheld) | ✅ |
| **LLM08 Vector/Embedding Weakness** | Evidence-grounded retrieval (RAG) | ⚠️ evidence recall 0.38 đo được (`bench_w2_seed42.json` D) — pipeline có, quality chưa chứng minh | ⚠️ một phần |
| **LLM09 Misinformation** | Hallucination guard + abstain | W2 R1: hallucination **0**/30; benchmark self-correction: **false corrections 13/13 (0% success)** — 🔴 GAP thật: không có LLM → không tự sửa được | 🔴 GAP |
| **LLM10 Unbounded Consumption** | Backpressure (200 in-flight cap), rate limit 60/min, lockfile | `ask_kernel_adapter.py` backpressure; slowapi; W2 R2 ladder đến ~1150 RPS không lỗi | ✅ |

## C.3 OpenAI "Practices for Governing Agentic AI" — nguyên tắc → SCP

| Nguyên tắc | SCP implementation | Bằng chứng |
|---|---|---|
| Traceability & audit trail | Journal hash-chain + evidence store + trace_id | `taskkernel.py` journal (W2: hash-chain 8/8 links); `bench_w2_seed42.json` run_id 29/30 unique |
| Human oversight / approval gates | Tier-3 approval + escalation UNKNOWN→ESCALATE | `judge.py` governance; benchmark: governance UPHOLD/ESCALATE measured |
| Bounded autonomy | Capability levels + egress mode + backpressure | capability_epoch + PEP; backpressure cap 200 |
| Incident response | Kill switch + breaker + recovery | W2 R3 chaos table (recovery 21s sau kill -9) |

## C.4 Cách đọc

- Bảng này là **map** — không phải chứng nhận. Mỗi dòng "✅" = có test/scan evidence trong repo tại SHA nêu trên.
- Số liệu benchmark (accuracy, self-correction) đo trên môi trường **không có LLM provider hoạt động** (zero-cost wall chặn — W2 bug #2) → accuracy 0% phản ánh pipeline không có generation, KHÔNG phản ánh chất lượng khi có provider.
- Lần benchmark kế tiếp cần: provider hoạt động (record $0 pricing proof như W2) → accuracy thực sự → điền số cạnh dòng tương ứng.
