# R19 Remediation Plan — Phương án xử lý vấn đề còn lại
## Áp dụng SCP DNA Skill (26 nguyên tắc + 6-step loop)

> **🐔 Gà:** "vậy phương án sử lí như nào các vấn đề còn lại? SCP DNA?"
>
> **🤖 SCP:** "6 vấn đề còn lại. Mỗi vấn đề: 5-Whys → root cause → fix nhỏ + rollback + Reality test. Không big-bang."

---

## 1. Problem Statement (DNA #1)

6 vấn đề còn lại sau R16+R17+R18:

| # | Vấn đề | DNA vi phạm | Severity |
|---|---|---|---|
| **V1** | 1,804 silent except:pass (17 files) | #9 (No harm) | 🔴 Systemic |
| **V2** | 14 dead security functions (register_*, verify_all_baselines) | #19 (Tầng kiểm toán) | 🟠 HIGH |
| **V3** | 25 god methods (>200 LOC) | #17 (Hành động nhỏ) | 🟡 MEDIUM |
| **V4** | 11 large files (>1000 LOC) | #18 (HỎI THỬ NHỎ) | 🟡 MEDIUM |
| **V5** | Runtime chưa verify (OpenRouter 429 chặn benchmark) | #26 (Reality > Model) | 🟠 HIGH |
| **V6** | External reviewer thiếu (tự audit) | #15 (Gà Lab bị audit) | 🟡 MEDIUM |

---

## 2. Why Chain (DNA #1) — cho mỗi vấn đề

### V1: 1,804 silent except:pass

```
Tại sao có 1,804 silent except?
→ Developer dùng "except: pass" làm default (fail-open)
Tại sao fail-open thành default?
→ Không có CI rule chống lại pattern này
Tại sao không có CI rule?
→ Lint config không enable BLE001 + S110 + S112 as errors
Tại sao developer không log errors?
→ "best effort" được hiểu thành "silent effort"
Tại sao (ROOT)?
→ "fail-open" được implement thành "fail-SILENT" — fail-open nên LOG, không nên SILENT
```

### V2: 14 dead security functions

```
Tại sao 14 security functions không được gọi?
→ Implemented trong standalone modules, quên wire vào pipeline
Tại sao R4-R15 không phát hiện?
→ vulture thấy "method defined on class" = "used" → false negative
Tại sao R16-R18 mới phát hiện?
→ Manual code flow audit (khác lineage với vulture)
Tại sao (ROOT)?
→ "Implemented but not wired" pattern — R13's "callable ≠ called" bug (DNA #22 recursive)
```

### V5: Runtime chưa verify

```
Tại sao runtime chưa verify?
→ OpenRouter 429 chặn benchmark
Tại sao OpenRouter 429?
→ Free tier exhausted (0/1000 trên 3 keys)
Tại sao không có fallback LLM?
→ Chỉ dùng OpenRouter, không có Groq/Together/Ollama
Tại sao (ROOT)?
→ Single provider dependency — DNA #13 (Không đứng số một) violation
```

---

## 3. Evidence Map (DNA #5, #14, #20)

| Source | Evidence | Lineage | Độc lập? |
|---|---|---|---|
| vulture | 529 dead code findings (≥60% conf) | AST + confidence | ✅ |
| R18 manual audit | 14 dead security functions | Human code flow | ✅ (khác lineage vulture) |
| grep | 1,804 silent except across 17 files | ripgrep | ✅ |
| R17 benchmark attempt | 15.4% accuracy, /health 503 | Runtime Reality | ✅ (tuyệt đối) |
| OpenRouter API | 429 on all 3 keys | External Reality | ✅ |

**Cảnh báo ảo giác đồng thuận (DNA #5):** vulture + ruff + pyflakes cùng AST lineage → có thể missed semantic dead code. Manual audit (R18) độc lập → phát hiện bugs tools missed.

---

## 4. Missing Pieces (DNA #19, #25)

### Đã biết
- 1,804 silent except:pass — cần triage + fix từng cái hoặc CI gate
- 14 dead security functions — cần wire hoặc delete
- 25 god methods — cần refactor (deferred)
- Single provider dependency — cần fallback LLM

### Chưa biết (DNA #25)
- R19 sẽ tìm gì R18 không thấy?
- Dynamic dispatch có giấu dead code không?
- Runtime behavior có match code analysis không?

---

## 5. Proposed Action (DNA #12, #17 — nhỏ, đảo ngược được)

### Action 1: CI Gate cho silent except (V1) — ROOT FIX

**DNA #7 (Autofix safe) + #9 (No harm) + #17 (Hành động nhỏ)**

**What:** Thêm ruff rule BLE001 + S110 + S112 as ERRORS trong CI config.

**File:** `scp/ruff.toml` + `scp/pyproject.toml`

```toml
[tool.ruff.lint]
select = ["E", "W", "F", "I", "UP", "B", "BLE001", "S110", "S112"]
# BLE001 = blind except Exception
# S110 = except: pass
# S112 = except: continue
```

**Root cause fix (không cascade):**
- CASCADE: fix 1,804 locations thủ công (slow, error-prone)
- ROOT: CI gate chặn NEW silent except + gradual fix existing

**Rollback:** Remove 3 rules from config
**Reality test:** `ruff check --select BLE001,S110,S112` → count should decrease over time

**Phases:**
1. Phase 1: Add CI rule (chặn NEW) — 1 giờ
2. Phase 2: Fix top 17 files (high-impact) — 2-3 ngày
3. Phase 3: Fix remaining (low-impact) — gradual

---

### Action 2: Wire 14 dead security functions (V2) — ROOT FIX

**DNA #19 (Tầng kiểm toán) + #7 (Autofix safe)**

**What:** Wire các security functions vào pipeline.

**Priority order:**

| # | Function | File | Wire into | Action |
|---|---|---|---|---|
| 1 | `external_trust.register_file` | `meta/external_trust.py:145` | startup (register source files) | Wire vào lifespan |
| 2 | `external_trust.verify_all_baselines` | `meta/external_trust.py:169` | 24h cron | Wire vào deep_audit_loop |
| 3 | `domain_store.verify_all_baselines` | `knowledge/domain_store.py:369` | 24h cron | Wire vào deep_audit_loop |
| 4 | `cross_verify_trivia` | `core/cross_verify.py:244` | WHY engine | Wire hoặc delete |
| 5 | `verify_with_voting` | `ai_patterns.py:87` | Delete (superseded by RealityJudge) | Delete |
| 6-14 | (9 more vulture findings) | various | Triage: wire/delete | Per-function |

**Root cause fix (không cascade):**
- CASCADE: wire tất cả 14 cùng lúc (risky)
- ROOT: wire 3 CRITICAL first (external_trust + domain_store), triage rest

**Rollback:** Revert individual wire
**Reality test:** `grep -rn "verify_all_baselines" scp/` → should have ≥2 production callers

---

### Action 3: Refactor god methods (V3) — DEFERRED

**DNA #17 (Hành động nhỏ) + #18 (HỎI THỬ NHỎ)**

**What:** Split god methods >200 LOC thành smaller functions.

**Priority:**
1. `antibody_system.py:_run_antibody` (1153 LOC) — CRITICAL
2. `db_manager.py:_init_all_module_tables` (453 LOC) — HIGH
3. `fast_learning_engine.py:_store_kb` (312 LOC) — MEDIUM

**Approach:** Extract method pattern — 1 method at a time, each with Reality test.

**Why deferred:** God methods work (just hard to maintain). Fix khi touch file đó cho feature khác.

**Rollback:** Revert individual extract
**Reality test:** `ast.parse` + test suite pass

---

### Action 4: Split large files (V4) — DEFERRED

**DNA #18 (HỎI THỬ NHỎ)**

**What:** Split files >1000 LOC vào modules.

**Priority:**
1. `judgecore_mixin.py` (3449 LOC) — split by phase (28 phases → 28 files?)
2. `autofix/engine.py` (2486 LOC) — split by tier (Tier 1/2/3/4)
3. `antibody_system.py` (1766 LOC) — split by antibody type

**Why deferred:** File splitting = big refactor. DNA #17: "nhỏ + đảo ngược". Defer đến khi cần touch file.

**Rollback:** Revert split
**Reality test:** All imports still work + test suite pass

---

### Action 5: Fallback LLM provider (V5) — ROOT FIX

**DNA #13 (Không đứng số một) + #26 (Reality > Model)**

**What:** Thêm Groq/Together AI/Ollama sebagai fallback khi OpenRouter 429.

**File:** `mini-services/llm-bridge/index.ts`

```typescript
// [R19-FIX] Fallback LLM providers — nếu OpenRouter 429, thử Groq, rồi Ollama
const LLM_PROVIDERS = [
  { name: "openrouter", url: "https://openrouter.ai/api/v1", key: process.env.OPENROUTER_API_KEY },
  { name: "groq", url: "https://api.groq.com/openai/v1", key: process.env.GROQ_API_KEY },
  { name: "ollama", url: "http://127.0.0.1:11434", key: "" },  // local, no key
];

async function callLLMWithFallback(messages, model) {
  for (const provider of LLM_PROVIDERS) {
    if (!provider.key && provider.name !== "ollama") continue;
    try {
      return await callProvider(provider, messages, model);
    } catch (err) {
      if (isRateLimitError(err)) {
        console.warn(`[llm-bridge] ${provider.name} 429, trying next...`);
        continue;
      }
      throw err;
    }
  }
  throw new Error("All LLM providers exhausted");
}
```

**Root cause fix (không cascade):**
- CASCADE: retry OpenRouter với longer backoff (vẫn 1 provider)
- ROOT: multi-provider fallback (DNA #13: dùng hệ thống khác nếu tốt hơn)

**Rollback:** Remove fallback array
**Reality test:** Kill OpenRouter → SCP vẫn trả lời được (via Groq/Ollama)

---

### Action 6: External reviewer (V6) — DEFERRED

**DNA #15 (Gà Lab bị audit) + #21 (Không tin một tác nhân)**

**What:** Independent external reviewer chạy benchmark + audit.

**Options:**
1. Publish trên GitHub → community audit
2. Hire external auditor
3. Use another AI (different lineage) to audit

**Why deferred:** Cần public release first (publish GitHub + HuggingFace).

**Rollback:** N/A (additive)
**Reality test:** External reviewer reproduces benchmark results

---

## 6. Priority Matrix (DNA #17 — nhỏ trước, lớn sau)

| Priority | Action | Effort | Impact | Risk |
|---|---|---|---|---|
| **P0** | Action 1: CI Gate silent except | 1h | Chặn NEW silent except | THẤP |
| **P0** | Action 5: Fallback LLM provider | 2-3h | SCP work khi OpenRouter 429 | THẤP |
| **P1** | Action 2: Wire 14 dead security (3 CRITICAL) | 4-6h | Security functions enforce | MED |
| **P2** | Action 2: Wire remaining 11 dead security | 1-2 ngày | Complete coverage | MED |
| **P3** | Action 3: Refactor god methods | 1-2 tuần | Maintainability | MED |
| **P3** | Action 4: Split large files | 2-4 tuần | Maintainability | MED |
| **P4** | Action 6: External reviewer | 1-2 tháng | Independent validation | THẤP |

---

## 7. Timeline (DNA #18 — HỎI THỬ NHỎ)

```
Tuần 1:
  Day 1: Action 1 (CI gate) + Action 5 (fallback LLM)
  Day 2-3: Action 2 (wire 3 CRITICAL security functions)
  Day 4-5: Reality test — run benchmark với fallback LLM

Tuần 2:
  Day 1-3: Action 2 (wire remaining 11 security functions)
  Day 4-5: Fix top 17 silent except files (high-impact)

Tuần 3-4:
  Action 3 (refactor god methods — 1 at a time)

Tuần 5-8:
  Action 4 (split large files — 1 at a time)

Tháng 3+:
  Action 6 (external reviewer — publish + community audit)
```

---

## 8. Reality Test Plan (DNA #26)

### Sau mỗi action:

```bash
# Action 1 (CI gate):
ruff check scp/ --select BLE001,S110,S112 --statistics
# EXPECT: count tracked over time (should decrease)

# Action 2 (wire security):
grep -rn "verify_all_baselines\|register_file" scp/ --include="*.py" | grep -v "def \|#"
# EXPECT: ≥2 production callers

# Action 5 (fallback LLM):
# Kill OpenRouter (set invalid key) → SCP vẫn trả lời via Groq/Ollama
curl -X POST http://127.0.0.1:8000/ask -d '{"question":"2+2=?"}'
# EXPECT: 200 response (not 503)

# All actions:
python3 -c "import ast; ast.parse(open('scp/api_server.py').read())"
# EXPECT: ast.parse OK (no syntax errors)
```

---

## 9. Open Questions (DNA #23, #24, #25)

1. **CI gate có break existing CI không?** — Cần check if 1,804 silent except are in CI-critical paths
2. **Groq/Ollama có available trong user's environment không?** — Cần verify before wire
3. **14 dead security functions — wire hay delete?** — Per-function triage needed
4. **God method refactor có cause regression không?** — Cần test suite mạnh hơn (hiện 38% false-PASS)
5. **R19 sẽ tìm gì R18 không thấy?** — DNA #25: không thể biết trước

---

## 10. Conclusion (DNA #26: Reality > Model)

### 6 vấn đề → 6 actions

| Vấn đề | Action | Priority | Status |
|---|---|---|---|
| V1: 1,804 silent except | CI gate (ROOT) | P0 | Ready to apply |
| V2: 14 dead security | Wire 3 CRITICAL + triage 11 | P1 | Ready to apply |
| V3: 25 god methods | Refactor 1 at a time | P3 | Deferred |
| V4: 11 large files | Split 1 at a time | P3 | Deferred |
| V5: Runtime chưa verify | Fallback LLM provider | P0 | Ready to apply |
| V6: External reviewer | Publish GitHub | P4 | Deferred |

### DNA principles applied

| DNA | Application |
|---|---|
| **#1** (Hỏi Tại sao) | 5-Whys cho mỗi vấn đề |
| **#7** (Autofix safe) | Mỗi action có rollback |
| **#9** (No harm) | CI gate chặn silent except (ROOT fix) |
| **#13** (Không đứng số một) | Fallback LLM provider |
| **#17** (Hành động nhỏ) | Priority matrix — nhỏ trước, lớn sau |
| **#19** (Tầng kiểm toán) | Wire dead security functions |
| **#22** (PASS ≠ TRUE) | ast.parse OK ≠ runtime OK — cần Reality test |
| **#25** (Câu hỏi không nghĩ ra) | 5 open questions |
| **#26** (Reality > Model) | Reality test plan cho mỗi action |

### Verdict

> **6 vấn đề còn lại. 2 P0 (ready to apply ngay). 1 P1 (wire security). 3 P3-P4 (deferred).**
>
> **P0 actions (CI gate + fallback LLM) = ROOT fix cho 2 systemic issues.**
>
> **Không big-bang. Mỗi action nhỏ + đảo ngược + Reality test.**

> **KHÔNG HOÀN THIỆN. KHÔNG THẤT BẠI. KHÔNG HOÀN TẤT. ĐANG HOẠT ĐỘNG.** (DNA #23)
>
> **Reality vẫn giữ quyền trả lời cuối cùng.** (DNA #26 🌍)
