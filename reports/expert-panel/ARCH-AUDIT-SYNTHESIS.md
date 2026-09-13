# ARCH-AUDIT-SYNTHESIS — Tổng hợp + kiểm chứng chéo 4 báo cáo kiến trúc SCP

- **Verifier Agent:** V-ARCH (READ-ONLY đối với product code; chỉ ghi file synthesis này)
- **Ngày:** 2026-09-13
- **Snapshot:** HEAD `9ec8d6bcf7b6ec3fc6c516328223a526292e9b17` (đã `git rev-parse` xác nhận khớp đề bài; commit "first live-LLM baseline seed99 … GA B11 handoff")
- **Đầu vào:** 4 báo cáo `reports/expert-panel/ARCH-AUDIT-{A-kernel,B-knowledge,C-meta,D-security}.md` = 14 + 11 + 15 + 12 = **52 mảnh** (D tách D6a/D6b nên 12).
- **Phương pháp verifier:** đọc lại 2 SKILL.md + tính SHA256, hợp nhất bảng 4 báo cáo, sau đó **spot-check 6 claim trọng nhất trực tiếp trên code tại HEAD** (đọc file + `git show HEAD:` cho 3 file S20 in-flight + 1 probe Python chạy thật). Không chạy server/benchmark mới; không sửa product code.

## Skill binding (SHA256 — tự tính lại bởi V-ARCH, khớp 4/4 báo cáo)

| File | SHA256 |
|---|---|
| `.agents/skills/scp-dna/SKILL.md` | `4aada0be4873598dc50c3a7f38d90151429bb5263c511a838ed1cdcb4d594d10` |
| `.agents/skills/scp-reality-verifier/SKILL.md` | `a9d65ce53b18f8310ceeb302b18b341a0e1b8b19cddc7f46d4fa6ee99432269e` |

Đã áp dụng: reality-verifier (phân biệt Static-A / Integration-B / E2E-C / Recovery-D; static PASS không nâng cấp thành runtime proof) + scp-dna core loop (evidence-first, missing-piece, reality-test, kết thúc bằng open questions).

---

## 1. Bảng tổng hợp 52 mảnh

Quy ước: EXISTS/WIRED tóm lược từ báo cáo gốc; mọi claim được spot-check ở mục 3 giữ nguyên; các mảnh không spot-check giữ verdict của agent gốc (đã đối chiếu tính nhất quán giữa 4 báo cáo). DECISION chuẩn hóa: `GIỮ-NHƯ-LÀ` → GIỮ; "GIỮ code, NỐI sau" → GIỮ; C11 ghi REBUILD vì phần việc trội là xây vòng chấm điểm tự động (ledger thì NỐI); D11 là RED (không thể falsify).

### Nhóm A — KERNEL/RUNTIME (14 mảnh)

| Mảnh | EXISTS | WIRED_IN_RUNTIME | EVIDENCE (falsifiable?) | GAP | DECISION |
|---|---|---|---|---|---|
| A1 Task state machine (17 states) | `task_kernel.py:16-26`; `transition()` `taskkernel.py:381-518` | `/ask` adapter.begin + hands bridge (`api_server.py:496-523`, `task_kernel_bridge.py:393-401`) + retry worker | 31+69 test T04 do agent tự chạy @HEAD; assert `InvalidTransition` → đỏ nếu sửa map | Ghost state `WAITING_APPROVAL` ngoài `STATES` (`task_kernel.py:26` vs `:16`) — nối miệng dễ gãy khi refactor | **NỐI** |
| A2 Journal hash-chain | `_append_event` `taskkernel.py:344-360`; verify/rebuild fail-closed `:1638-1708` | mọi write-path; `recover_on_boot` `:1591-1594`; doubt-cron định kỳ | test tamper DB trực tiếp (`UPDATE events SET payload`) → `hash_chain_valid=False` (31 passed) | chưa test tamper cấp file (bit-rot ngoài SQLite API) | **NỐI** |
| A3 Lease + fencing token | `Lease` `task_kernel.py:95-102`; `_assert_lease` `taskkernel.py:609-627` (fencing==MAX) | `/ask` claim ttl60; hands claim/start/heartbeat/release; watchdog `background_jobs.py:247-261` required=True | fencing tests trong 31 passed; runtime proof hands `runtime_proof_20260826_hands_bridge.json` @`46187e7` | TTL `/ask` cố định 60s (→ mảnh A4) | **NỐI** |
| A4 Lease heartbeat / renew trong /ask | `heartbeat()` đầy đủ `taskkernel.py:659-701` | **hands: có; /ask: KHÔNG tại HEAD** (claim ttl60 rồi không renew — đã spot-check, mục 3.6) | benchmark seed99: **2/10 asks chết `lifecycle_authority_lost`** (runtime đỏ tái hiện) | gap thật tại HEAD; S20 in-flight đang sửa, chưa commit | **NỐI** (chờ S20 commit + bench 10/10) |
| A5 OCC (optimistic concurrency) | `OptimisticLockError` + version check mọi UPDATE path `taskkernel.py:410-502,676-696,…` | mọi UPDATE kernel; adapter bắt KernelError route stale-lifecycle | rebuild/OCC/p1 tests trong 69 passed; bỏ `AND version=?` → đỏ | thiếu stress multi-writer song song thật (window hẹp, chấp nhận) | **NỐI** |
| A6 Idempotency (fenced claim/complete) | facade fail-closed `task_kernel.py:175-249` (bắt buộc lease authority) | `/ask` claim ngay sau start; hands claim/complete sau verifier; reconcile → HUMAN_REVIEW | stale lease không claim được (trong 31 passed); falsifiable | — (S19 BUG-2 đã sửa đúng tại HEAD) | **NỐI** |
| A7 Kill switch | `_assert_not_killed` `taskkernel.py:520-524`; epoch fencing `:1412-1449` | claim/commit + mọi `_assert_lease` check epoch; kill = máy-trạng trong DB | kill ON → `KillSwitchActive` (p1/adversarial trong 69 passed) | không có route HTTP operator (control-plane mỏng) | **NỐI** |
| A8 Recovery + checkpoint + reconcile | `taskkernel.py:782-968, 1569-1618, 1710-1718`; secret-scan checkpoint | lifespan boot + watchdog orphan required + hands dùng UNKNOWN/reconcile đầy đủ | crash-consistency + p1-regressions; runtime proof cấp D cho hands (UNKNOWN→recovery observed) | `/ask` R0 không dùng `record_action_dispatched` (hợp lý, không side-effect) | **NỐI** |
| A9 Backpressure / admission control | `in_flight_count` `taskkernel.py:1620-1624`; cap `SCP_ASK_MAX_INFLIGHT` `adapter:194-201` | `/ask begin()` cap check → `_kernel_blocked_response` | deterministic khi đọc trực tiếp; **chưa có unit test riêng cho cap** | `claim_next` fair-share chưa có consumer production | **NỐI** (+1 unit test cap) |
| A10 Request ledger (2 tầng) | kernel `record_action_dispatched` `:819-866` + API `RequestRunLedger` JSONL | API wired dày (/ask, admin, chat); kernel-level qua hands | unit adversarial/T10 + bench seed99 ghi run_status | 2 tầng ledger chưa join bằng tool đối chiếu tự động | **NỐI** |
| A11 Storage SQLite | `KernelStorage` Protocol + WAL/BEGIN IMMEDIATE retry `kernel_storage.py:32-238` | inject mặc định mọi consumer | storage tests trong 31 passed | SPOF single-node đã khai báo trong docstring (không phải gap ẩn) | **GIỮ** |
| A12 PG storage parity (Track C1) | `PgKernelStorage` + translator fail-closed; opt-in env | opt-in; compose hiện không set → SQLite default (không silent flip) | **16 test skipped (declared infra-skip, thiếu DSN)**; 10 translator passed | parity cần PG thật tái xác nhận định kỳ (CI chưa bật DSN) | **NỐI** (job CI có DSN) |
| A13 Event bus PG NOTIFY (Track C2) | `PgEventBus` publish+notify cùng xact `:205`; replay + poison guard | opt-in; consumer sandbox-evaluator compose profile "sandbox"; không trong /ask | suite real-PG gồm test "(b) listener down → replay mất 0 event" — skipped declared | cùng điều kiện A12; không có subscriber trong path /ask | **NỐI** (cùng job CI DSN) |
| A14 TraceLedger (JSONL hash-chain) | `trace_ledger.py:25-46` (seq+prev_hash+redact) | adapter tạo `data/ask_task_kernel_trace.jsonl`, append begin/finalize/fail | verify unit trong T04/T08 (A-level; không chống xóa file) | append O(n) đọc-ghi toàn file; chưa rotation | **NỐI** (rotation khi file lớn) |

### Nhóm B — KNOWLEDGE/LEARNING (11 mảnh)

| Mảnh | EXISTS | WIRED_IN_RUNTIME | EVIDENCE (falsifiable?) | GAP | DECISION |
|---|---|---|---|---|---|
| B1 Knowledge domain store | `knowledge/domain_store.py` 507 LOC thật (SHA-256, TTL, tamper-detect) | **KHÔNG**: `judge.py:111` trả `None` (đã spot-check, mục 3.1) → phase1/phase9 rẽ nhánh chết; `/v100/knowledge/*` 503; 0 nơi khởi tạo | test import-only (`test_subsystem_knowledge.py:12`) — **không falsifiable** với bug logic | Judge trả None → toàn bộ KB nội bộ không đọc/ghi trong prod | **NỐI** (wire store vào judge+lifespan) |
| B2 Curation 5-nguồn | `knowledge_curation.py` thật (4-signal reliability, quarantine gate) | **3/5 nguồn không chạy**; `curate()` 0 caller; chỉ GitHub+Wiki qua `/v104/learn/top-systems` + autofix | static grep test — không falsifiable cho pipeline | pipeline 5-nguồn trên giấy; 2 nguồn còn lại manual, không scheduler | **NỐI** (wire scheduler hoặc hạ claim còn 2-nguồn) |
| B3 Epistemic ladder L0→L4 | `ontology.py` thật (chặn RAW→GOLD, GOLD bắt buộc evidence_refs) | **KHÔNG**: chỉ `promotion_contract.py` + tests; 0 producer runtime | T02 falsifiable tốt (RAW→GOLD raise, bảng transition đóng) | ladder là schema authority không ai nuôi | **NỐI** (vào ingestion + PromotionAuthority) |
| B4 Contradiction engine | persist thật; assess heuristic **sai bản chất** (so độ dài chuỗi timestamp, L92) | **KHÔNG** (chỉ CognitiveOrchestrator — tự dead) | test contract một phần, không kill bug L92 | temporal-check sai + chưa từng chạy runtime | **REBUILD** (assess + wire trigger) |
| B5 Quarantine / trust model | `trust_hierarchy.py` TrustTier 0-4 + registry thật | **một nhánh có**: semantic firewall trong `/ask` (`_ask_impl.py:358-367`); tier không tác động thực (KB đang chết) | firewall tests + bench `G_security.bypassed=0`; chưa E2E poison-KB | tier chờ B1 sống mới có tác động | **GIỮ** (firewall); nối tier khi B1 sống |
| B6 Lineage + sha256 provenance | `lineage.py` + `evidence_store.py` thật (DB-enforced UNKNOWN_INDEPENDENCE) | **EvidenceStore CÓ** (v106 routes, gateway catalog, retention); **LineageStore KHÔNG** (0 caller runtime) | T06 falsifiable (không thể tự phong INDEPENDENT) | LineageStore tách rời EvidenceStore → independent_lineages không có dữ liệu runtime | **NỐI** (LineageStore vào evidence/ingestion) |
| B7 Continual learning `continual.py` | **BỊ HỎNG**: gọi `record_insight` (L28) — method không tồn tại trong repo | 0 caller | không có | dead code + broken API; chức năng thật do FastLearningEngine (B11) đảm nhiệm | **BỎ** |
| B8 Knowledge Warehouse (FAISS) | **STUB**: "Placeholder" L26/L32, không FAISS | 0 caller | không có | placeholder thuần; `capabilities/vector_db.py` là bản thật hơn | **BỎ** |
| B9 RAG / knowledge ingestion | `CanonicalRetriever` TF-IDF thật nhưng **corpus 0**; `/v105/rag/query` import `HybridRetriever` **không tồn tại** → 500 (đã spot-check, mục 3.5) | KHÔNG (corpus nội bộ); live 4-API CÓ qua DomainSLM fallback | **CÓ**: `D_evidence_recall` seeded 0.3846 (seed42) / 0.0 (seed99); gate RAG-1000 `BLOCKED`; test grep-text PASS dù endpoint 500 | corpus 0 + endpoint gãy import + test không kill được product bug | **REBUILD** (slice B-S2) |
| B10 Question/hypothesis/doubt memory | thật (dataclass + sqlite store) | KHÔNG (consumer duy nhất EpistemicBoundary/DoubtAuthority đều dead) | unit contract falsifiable cục bộ | cả cụm meta-cognitive tests-only | **GIỮ** code, nối khi B3 sống |
| B11 FastLearningEngine (tham chiếu) | thật (wiki cross-check trước khi store) | **CÓ**: thread trong `helpers.py:367`, ghi `data/v13.db` | chạy thật trong prod judge init | v13.db **không ai đọc lại** (phase1 đọc domain_store=None) | **NỐI** (output → retrieval) |

### Nhóm C — META / SELF-MODEL / WORLD-STATE (15 mảnh)

| Mảnh | EXISTS | WIRED_IN_RUNTIME | EVIDENCE (falsifiable?) | GAP | DECISION |
|---|---|---|---|---|---|
| C1 WHY Engine | thật (12 patterns, atomic `UPDATE..RETURNING` `whyengine.py:361`) | `/ask` pre-judge hook (`cognitive_router.py:22-29`) + background 5min qua `judge.why_engine` | M12-closure executed=1 @`fa9da62` (C-level 1 cycle); HEAD local DB `total=0` | chưa tái hiện executed tại HEAD (cần benchmark S1) | **NỐI** |
| C2 WHY Gate v9.0 "primary control gate" | `why_gate.py` 650 LOC substantive | **DEAD 2 LỚP**: judge mới không inherit mixin; trong phase7 `ctx.verdict.ctx` = **AttributeError nuốt bởi logger.debug** (đã spot-check, mục 3.2) | probe P3+P4 falsifiable, tái hiện 100% | claim "PASS→UNKNOWN" chết + code hỏng | **REBUILD** (port sang judge 2-tier) hoặc xóa claim |
| C3 BehaviorMonitor | thật (heuristic deterministic, decay) | chỉ qua why_gate trong autofix paths (deep-audit live); KHÔNG trong /ask verdict path | import được thật (qua P2); **0 test** | không gate được verdict /ask | **NỐI** (giữ) + thêm test |
| C4 CuriosityAsker | mỏng (template questions; không đọc `pending_resolutions` như docstring hứa) | 0 call-site runtime | docstring trích test **không tồn tại** trong tests/ | dead module khôi phục cho 1 test đã mất | **GIỮ** (chờ slice S3) |
| C5 CuriosityEngine / MetaCognitionEngine | thật, ghi `meta_curiosity` | chỉ CLI; `pending_resolutions` không có reader | static grep | meta-curiosity loop không chạy 24/7 | **NỐI** (qua slice S3) |
| C6 Self-model + Blind-Spot Registry | chuẩn evidence-first (proofs immutable, stale-SHA rejection) | route `/v106/capabilities/{id}` recompute; **`tested_sha="HEAD"` HARDCODE** (`v106_routes.py:66`) | T06 tests | tested_sha phá contract provenance của chính module; `add_blindspot` 0 runtime writer | **NỐI** + sửa tested_sha = git SHA thật |
| C7 DoubtAuthority | thật (anti-self-resolve, tự đăng ký blindspot) | **test-only**, 0 call-site runtime | T02 falsifiable cho module | không ai viết doubt/blindspot lúc runtime → registry trống | **NỐI** (wire vào doubt_cron) |
| C8 Doubt Cron | 4 checks + `doubt_ledger.jsonl` | lifespan start (6h, chạy vòng đầu) / stop | **probe P2 chạy thật end-to-end** → DOUBT_DETECTED (falsifiable) | chỉ báo cáo ledger + log, không escalate | **NỐI** |
| C9 World-State authority | bitemporal + immutability + anti-self-promotion + OBSERVED yêu cầu evidence_refs | routes (profile full) + **/ask PASS hook raise MỖI lần PASS** (đã spot-check, mục 3.3) | T02 + T09 golden e2e + P1/P1b falsifiable | hook dead-on-arrival 1 dòng (thiếu evidence_refs) → 0 event từ runtime | **NỐI** + fix hook (slice C-S2) |
| C10 Prediction routes + PredictiveOrchestrator | thật (run-cycle/verify/stats) | engine gắn judge (`helpers.py:287-295`); routes chỉ profile ≥ full | route tự 503 khi engine None (falsifiable wiring) | native `.env` `SCP_API_PROFILE=core` → routes không đăng ký; lệch bề mặt API với compose full | **NỐI** + quyết định profile nhất quán |
| C11 Calibration | ledger mới thật (record/resolve/accuracy); legacy engine 607 LOC | **ledger CÓ** (hook `/ask` UNKNOWN/PARTIAL/FLAGGED + routes); legacy chỉ trong phase7 chết | T06 + T02 falsifiable | không có auto-resolve/chấm điểm định kỳ; Brier/ECE legacy chết theo phase7 | **REBUILD** vòng chấm điểm tự động (ledger NỐI) |
| C12 Forecast | append-only registry + resolve outcome codes thật | hook keyword-trigger (`_ask_impl.py:565-586`) + routes (profile full) | static; routes fail-closed không leak | resolve chỉ admin-manual; hook chỉ bắt keyword | **NỐI** |
| C13 Risk Intelligence routes | RiskClassifier PR0-PR5 + IncidentStateMachine thật | hook classify mỗi request + routes (profile full) | hook observable qua `evidence['risk_level']` | `_incidents` in-memory — restart mất | **NỐI** (persist qua world_state khi cần) |
| C14 Judge background scheduler | `JudgeBgMixin` 175 LOC thật (ThreatSim/IntelCrawl/ReVerify/Canary/…) | **DEAD**: lifespan gọi `schedule_background_jobs` — judge mới không có method (probe P3 hasattr=False) → error log mỗi boot, `background_scheduler_started=False` | P3 falsifiable 100% tại HEAD | 6 job nền không chạy; ReVerify chỉ còn path sync | **REBUILD** (port sang judge mới hoặc background job registry) |
| C15 Old judge pipeline (~2.800 LOC) | từng là live path V104; giờ broken (`ctx.verdict.ctx`) | 0 importer ngoài wiring kiểu `__init__`; `runtime/judge.py` thay thế từ 2026-08-29 | static + P4 (code còn hỏng) | dead + broken, tạo illusion "10-phase pipeline" | **BỎ** (port why_gate #2, scheduler #14 trước khi xóa) |

### Nhóm D — SECURITY / CAPABILITY / GATEWAY (12 mảnh)

| Mảnh | EXISTS | WIRED_IN_RUNTIME | EVIDENCE (falsifiable?) | GAP | DECISION |
|---|---|---|---|---|---|
| D1 Capability PEP + token + tier3 | HMAC sig, secret fail-closed, scope map, PEP, tier3 approval — thật | execute routes chèn token; dispatch validate + re-validate | integration tests mutation-contract (kernel-mutation-0 khi deny), HMAC, fail-closed | legacy `CapabilityManager` sibling chết, không ký/không scope → 2 vocabulary | **NỐI** (xóa/wall legacy) |
| D2 Hands / PC executor | allowlist + chặn chaining + `shell=False` + audit fail-closed + backup atomic | pc_controller_routes + hands_routes + bridge share executor | `test_flow_04` + M04 closure (CLOSED_WITH_KNOWN_GAP) | `rollback()` half-stub — luôn trả lỗi sau token check | **NỐI** (hoàn thiện rollback hoặc disclosed-lost) |
| D3 Egress choke + static scan | `enforce_egress_policy` fail-closed + AST scan 453 dòng | 3 fetcher chuẩn + census tool | **28 egress tests** + container runtime proof EE (falsified-then-closed) | per-file analysis có blind spot; dev default (mode unset) mở theo thiết kế | **NỐI** |
| D4 Zero-cost guard (S18) | 5 quyết định fail-closed + pricing proofs SQLite | 3 call-site trước driver; **chỉ bật khi `SCP_LLM_COST_MODE=free_only`** | T05 2 nhánh + S18 runtime proof (falsifiable) | opt-in = deployment policy, không phải đảm bảo compile-time (đúng V18 ACCEPT) | **GIỮ** |
| D5 Semantic firewall | `_QUARANTINE_PATTERNS` deterministic thật | `/ask` quarantine từng evidence trước judge | firewall tests + bench bypassed=0 | regex false-positive chặn cả văn bản chỉ nhắc tên module | **NỐI** (tách "nhắc tên" khỏi "thao túng") |
| D6a Red-team agent | 11 vector thật NHƯNG `_default_probe` luôn `safe=True` (placebo) | **KHÔNG wired**: 0 call-site, 0 test | không có evidence runtime | wire-naive sẽ tạo false confidence | **BỎ** |
| D6b H8 RedTeamBridge | pipeline 2 chiều 28 signature — code thật | **KHÔNG**: `judge.py:113` trả `None` vĩnh viễn; 0 khởi tạo; `/v100/h8/*` 503 (đã spot-check, mục 3.4) | static-only (A) | chiều 2 "tự học từ bypass" của V100 trơ hoàn toàn | **REBUILD** (instantiate + env-flag) |
| D7 Sandbox evaluator | 448 LOC, pytest trên bản sao workspace, verdict fail-closed không-PASS-khi-không-chạy | opt-in `SCP_SANDBOX_EVALUATOR` trong autofix worker + bus events | C3 closure + verdict contract tự falsify | mặc định TẮT; bwrap chỉ Linux, Windows yếu hơn | **NỐI** |
| D8 Request run ledger | M05 CLOSED_WITH_KNOWN_GAP + TraceLedger hash-chain | 11+ route files + kernel/adapter (S20) | M05 closure + `verify()` là postcondition falsifiable | 2 abstraction song song, chưa có run-id thống nhất | **NỐI** |
| D9 Kill switch (2 miền) | PC-file-based + kernel global_kill_epoch — thật | pc_routes kill/clear + hands_executor + adapter governance | gap13 tests falsifiable | 2 miền độc lập không liên động; không có nút "dừng tất cả" duy nhất | **NỐI** |
| D10 JWT / auth | jwt_guard fail-closed + `verify_admin` canonical (rate-limit, timing-safe) | verify_admin dependency khắp routes; JWT chỉ openai_compat | auth fail-closed + injection + boundary tests | single-admin; chưa có identity per-user | **NỐI** (trong scope hiện tại) |
| D11 Autofix evidence replay | `verify()` trả `{"ok": True, "status": "VERIFIED"}` **vô điều kiện — fake verifier** | import trong autofix pipeline (disclosed FA-04) | **KHÔNG thể falsify → RED** | mọi consumer tin verdict này đang ăn bằng chứng giả | **RED — REBUILD hoặc cô lập (cấm consumer tin verdict)** |

---

## 2. Đếm tổng theo DECISION (52 mảnh)

| DECISION | Số lượng | Mảnh |
|---|---|---|
| **NỐI** | **36** | A1-A10, A12-A14 (13); B1, B2, B3, B6, B11 (5); C1, C3, C5, C6, C7, C8, C9, C10, C12, C13 (10); D1-D3, D5, D7-D10 (8) |
| **REBUILD** | **6** | B4 (contradiction assess), B9 (RAG ingestion), C2 (WHY Gate), C11 (vòng chấm calibration), C14 (judge scheduler), D6b (H8 bridge) |
| **BỎ** | **4** | B7 (continual.py hỏng), B8 (warehouse stub), C15 (old judge ~2.800 LOC dead+broken), D6a (red-team placebo) |
| **GIỮ** | **5** | A11 (SQLite storage), B5 (firewall/trust), B10 (question/hypothesis memory), C4 (CuriosityAsker), D4 (zero-cost guard) |
| **RED** | **1** | D11 (`evidence_replay.verify()` trả VERIFIED vô điều kiện — cần cô lập/ngăn consumer ngay) |

Đọc nhanh: **69% (36/52) chỉ cần nối, không cần viết lại** — kho code SCP phần lớn là thật. Đỏ tập trung ở đúng 1 kiểu lỗi lặp lại: **module thật nhưng không có producer/consumer runtime** (B1/B3/B4/B6/B10/C7 + D6a/D6b), và 1 kiểu thứ hai: **wiring trỏ vào code chết** (C2/C14/C15 + hook C9).

---

## 3. Spot-check 6 claim trọng nhất — kết quả: **6/6 VERIFIED, 0 REFUTED**

Mọi bằng chứng dưới đây do V-ARCH tự thu thập tại HEAD `9ec8d6b` trong phiên này (đọc file + `git show HEAD:` + 1 probe Python). Không có claim nào bị REFUTED; một vài số dòng của báo cáo gốc lệch ±1-3 dòng so với thực tế, không đổi verdict.

| # | Claim | Verdict | Bằng chứng |
|---|---|---|---|
| 3.1 | **B1**: `judge.py:111` trả None làm chết KB | **VERIFIED** | `scp/runtime/judge.py:111` = `def domain_knowledge_store(self): return None`; grep toàn repo: `DomainKnowledgeStore(` chỉ xuất hiện trong comment TODO (`domain_store.py:373`), 0 khởi tạo thật; `phase1_kb_retrieval.py:16` `if self.domain_knowledge_store:` rẽ nhánh chết; `admin_v100.py` (`/v100/knowledge/stats`, `/search`) raise 503 khi store falsy |
| 3.2 | **C**: phase7 AttributeError nuốt bởi logger.debug | **VERIFIED** | `judge_parts/phases/phase7_build_verdict.py:45` `ctx.verdict.ctx.verdict`; `JudgeVerdict` (`judge_parts/types.py:14`) không có field `ctx`; probe tự chạy: `JudgeVerdict(verdict='PASS').ctx` → `AttributeError: 'JudgeVerdict' object has no attribute 'ctx'`; `except` :62 → `logger.debug` :63 (nuốt ở mức debug) |
| 3.3 | **C**: world-state hook raise mỗi PASS | **VERIFIED** | `_ask_impl.py` ~530-543: PASS → `record_event(..., evidence_refs=[], actor_id="scp-judge")` → `temporal_authority.py:87` default `epistemic_status="OBSERVED"` → `:91-92` `raise WorldStateError("OBSERVED assertion requires evidence_refs...")`; bọc try/except → `logger.warning` → fail-open, 0 event được ghi mỗi lần PASS |
| 3.4 | **D**: H8 bridge dead + `/v100/h8` 503 | **VERIFIED** | `scp/runtime/judge.py:113` = `def h8_redteam(self): return None`; `H8RedTeamBridge(` = 0 site khởi tạo trong `scp/` + `tools/`; `admin_v100.py` cả 3 route `/v100/h8/{stats,bypasses,analyses}` raise `HTTPException(503)` khi `judge.h8_redteam` falsy |
| 3.5 | **B**: `v105_routes.py:719` import `HybridRetriever` không tồn tại | **VERIFIED** | `v105_routes.py:719` `from scp.rag.canonical_retriever import HybridRetriever`, `:725` `HybridRetriever()`; `canonical_retriever.py` chỉ định nghĩa `CanonicalRetriever` (:31) và `get_canonical_retriever` (:73) → import lỗi tại request time → 500; `test_flow_14:57` chỉ kiểm tra chuỗi "HybridRetriever" có mặt trong file route nên PASS dù endpoint gãy |
| 3.6 | **A**: heartbeat không renew trong `run_rag` | **VERIFIED (tại HEAD)** | `git show HEAD:scp/ask_kernel_adapter.py`: `claim(task_id, "ask-route-worker", ttl_seconds=60)` :206, `run_rag` :688, 0 match `heartbeat|renew` toàn file; kernel tại HEAD có `heartbeat` (:659) nhưng không có `renew_lease`. Lưu ý: **working tree S20 in-flight** đã thêm `renew_lease` (`taskkernel.py:710`) và gọi trong `run_rag` (adapter :756, def :773) — đúng như report A tự ghi nhận, không đổi verdict |

Hệ quả của 6/6 VERIFIED: các DECISION liên quan (B1 NỐI-wire, B9 REBUILD, C2 REBUILD, C9 NỐI+fix-hook, D6b REBUILD, A4 NỐI-chờ-S20) đều đứng vững; không cần sửa bảng.

---

## 4. Top-3 dọc-slice toàn cục (chọn từ 8 ứng viên)

8 ứng viên: A-S1 (S20 heartbeat e2e), A-S2 (PG parity CI), B-S1 (sống lại KB), B-S2 (RAG thật), C-S1 (WHY loop benchmark), C-S2 (world-state hook fix), D-S1 (deny-path zero-mutation), D-S2 (wire H8). Tiêu chí: (a) nhỏ nhất + benchmark đo được ngay, (b) mở khóa nhiều ô đỏ nhất phía sau, (c) giá trị cho vòng nhận thức khép kín (tự-hỏi→tự-đáp→tự-học→tự-chấm).

### Slice #1 — A-S1: Commit S20 lease-heartbeat + benchmark 10/10 asks (unblock toàn vòng /ask)
- **Ô phải nối:** `TaskKernel.renew_lease` (working-tree `taskkernel.py:710`, expiry-only + fencing) → heartbeat asyncio trong `AskKernelAdapter.run_rag` (adapter :739-756) → env kill-switch `SCP_ASK_HEARTBEAT_*` → watchdog `expire_leases` (`background_jobs.py:247-261`) không được phá lease sống.
- **Size:** ~0.5-1 ngày — S20 đã code 2/3; còn: chạy đủ suite T04, commit, 1 benchmark tái hiện seed99.
- **Benchmark:** harness `reports/benchmark-2026-09-12/` — chỉ số: asks kết thúc COMPLETED vs HUMAN_REVIEW(`lifecycle_authority_lost`); baseline 8/10 → target **10/10** tại cùng provider latency 30-260s; anti-placebo: tắt heartbeat phải tái hiện lỗi cũ.
- **Rủi ro chính:** renew phải giữ expiry-only (không nới TTL vô hạn → lease zombie); nếu latency provider vượt tổng cửa sổ renew thì phải cap số vòng renew và rơi vào HUMAN_REVIEW đúng nghĩa.
- **Vì sao #1:** đây là ô đỏ duy nhất đang làm **sai kết quả đo của mọi slice khác** (2/10 asks chết = mọi benchmark qua /ask bị nhiễu); GA B11 đang treo đúng ở đây.

### Slice #2 — B-S1: Sống lại KB nội bộ (wire DomainKnowledgeStore vào judge) — mở khóa nhiều ô nhất
- **Ô phải nối:** lifespan khởi tạo `DomainKnowledgeStore(data/knowledge)` (TODO `domain_store.py:370-382`) → `RealityJudge.domain_knowledge_store` (`judge.py:111` bỏ `return None`) → phase1 KB retrieval (`phase1_kb_retrieval.py:16`) + phase9 store (`phase9_claim_extraction.py:154-156`) → `/v100/knowledge/*` (`admin_v100.py`) hết 503.
- **Size:** ~40-80 dòng (1 property + 1 lifespan block + integrity job), không đụng pipeline chính.
- **Benchmark:** `/v100/knowledge/stats` 503→200; thêm metric `kb_hits`/`kb_short_circuit` vào harness seed42/99 hiện có; kill-test integration: `judge.domain_knowledge_store.search("câu vừa store")` trả record — phải FAIL trước patch, PASS sau.
- **Rủi ro chính:** test hiện tại import-only không kill bug logic → phải thêm test thật; khi nối output `v13.db` (FastLearningEngine) phải qua quarantine gate (B5) để tránh poison KB.
- **Vì sao #2:** mở khóa đồng thời B1 (chết), tác động thực của tier/TTL B5, output B11 (học xong không ai đọc), và tiền đề producer cho B3 — 4 ô đỏ phía sau; trực tiếp phục vụ cạnh **tự-học→tự-dùng** của vòng nhận thức.

### Slice #3 — C-S2: World-State PASS event thật (product fix nhỏ nhất, khởi động vòng tự-quan-sát)
- **Ô phải nối:** `_ask_impl.py:530-543` truyền `evidence_refs=[run_id]` (từ `RequestRunLedger`/`stage_request`) hoặc ghi qua đường INFERRED → hook ngừng raise (`temporal_authority.py:91-92`) → mỗi PASS ghi 1 assertion append-only.
- **Size:** nhỏ nhất trong 8 (~1-10 dòng + mở rộng test T09 golden e2e).
- **Benchmark:** 5 câu /ask trả PASS → `GET /v105/world/projection?subject=entity:ask_session` → count PASS events == 5; chạy lại → tăng đúng 5 (append-only); hiện tại count = 0 (hook raise mỗi lần).
- **Rủi ro chính:** `evidence_refs` phải là id có provenance thật (không nhét chuỗi rỗng giả danh evidence — sẽ phá chính contract OBSERVED); native profile `SCP_API_PROFILE=core` không đăng ký world routes → phải đo trên compose full.
- **Vì sao #3:** nhỏ nhất mà mở ô C9 + đặt nền cho S3 (curiosity→blindspot→promotion) và cho cạnh **tự-quan-sát/tự-chấm** (mọi calibration/world E2E cần event này tồn tại).

*(Không chọn: B-S2 vì phần lớn công việc là dữ liệu corpus + provenance chưa rõ; C-S1 là benchmark thuần không fix product; D-S1/D-S2 đáng làm kế tiếp sau top-3 — D-S2 nối H8 khi judge đã ổn định.)*

---

## 5. Giới hạn bằng chứng (bắt buộc ghi theo scp-reality-verifier)

1. **Blueprint không có trên đĩa:** `COMPLETE_SCP_SYSTEM_BLUEPRINT_2026-09-02.md` không tồn tại (4/4 agent đã find không thấy) → toàn bộ audit là **thuần repo**, không có đối chiếu blueprint gốc; định nghĩa "mảnh" lấy từ đề bài + nội dung repo. Đây là limitation, không phải bằng chứng thiếu.
2. **S20 in-flight:** `scp/task_kernel_parts/taskkernel.py`, `scp/ask_kernel_adapter.py`, `compose.yml` đang modified trong working tree (lease heartbeat) + vài file untracked. Mọi trích dẫn 3 file này trong mục 3 được đọc qua `git show HEAD:`; số dòng working-tree (renew_lease :710, adapter :756) có thể lệch sau khi S20 commit.
3. **Số benchmark là historical artifact:** `bench_final_seed99.json` (2/10 asks chết, D_evidence_recall 0.0), `bench_after_fix_seed42.json` (0.3846), attack-resistance 16-blocked/0-bypass/18-attempts, crosscheck "21/22", Mimosa "HIGH 190→0" — tất cả là **artifact chạy trước đó, không phải runtime proof hôm nay**; không agent nào (kể cả V-ARCH) chạy lại server/benchmark trong phiên audit. Mức bằng chứng của synthesis này: chủ yếu **Static-A / Integration-B**; các proof C/D chỉ tồn tại pinned ở SHA/artifact cũ (ví dụ M12-closure @`fa9da62`, hands runtime proof @`46187e7`).
4. **Verdict của bảng là hợp nhất tĩnh:** 46/52 mảnh giữ verdict của agent gốc mà V-ARCH không tái kiểm tra từng dòng (chỉ 6 claim trọng nhất + vài kiểm tra phụ như 0 instantiation của DomainKnowledgeStore/H8RedTeamBridge); khả năng còn sai số cục bộ ở các mảnh không spot-check.
5. **Scope test:** A là báo cáo duy nhất có tự chạy pytest trong phiên (100 test passed + 16 declared skips); B/C/D thuần static + đọc artifact; phần PG parity (A12/A13) vẫn chưa được xác nhận runtime trong bất kỳ session nào gần đây vì thiếu DSN.

---

## 6. Verdict tổng của V-ARCH

**SCP không thiếu module — SCP thiếu wiring.** 36/52 mảnh đủ tốt để nối tiếp; lõi kernel (A) và security/capability (D1-D5, D7-D10) là phần khỏe nhất với test falsifiable thật. Ba lỗ thật đã được xác minh bằng code + probe tại HEAD:

1. **Vòng nhận thức khép kín đứt ở đúng các điểm nối, không phải thiếu code:** `judge.py:111/113` trả None (KB + H8 chết), phase7 AttributeError (WHY gate chết), `/ask` world-state hook thiếu evidence_refs (observation chết), judge scheduler gọi method không tồn tại (meta-background chết), `v13.db` học xong không ai đọc lại. Sửa từng điểm là việc nhỏ; không sửa thì cả tầng meta/knowledge chỉ là illusion.
2. **Độ tin cậy vòng /ask:** lease hết hạn trước provider latency 30-260s → 2/10 asks mất answer thật (GA B11 đỏ) — S20 đang sửa đúng hướng, cần commit + benchmark 10/10.
3. **Vệ sinh kiến trúc:** ~2.800 LOC old-judge dead+broken tạo illusion "10-phase pipeline"; 4 module dead/stub (B7, B8, C15, D6a); và 1 RED thật cần xử lý ngay: `evidence_replay.verify()` trả VERIFIED vô điều kiện — bất kỳ consumer nào tin nó đang ăn bằng chứng giả (vi phạm FA-04, phải cô lập hoặc rebuild trước khi autofix tin verdict).

Không thể claim production-ready: mọi con số hiệu năng/an toàn trong hồ sơ là artifact lịch sử, chưa có runtime run mới tại HEAD trong phiên này; PASS_WITHIN_SCOPE của từng gate không được mở rộng thành "hệ thống hoạt động" (DNA #22).

**Open questions:** (1) corpus canonical-v2/v3 gốc nằm đâu trước khi rebuild B-S2; (2) profile `core` vs `full` — bề mặt API nào là deliberate; (3) old judge pipeline xóa hay port (ảnh hưởng test parity); (4) `tested_sha="HEAD"` là deliberate hay quên sửa; (5) legacy `CapabilityManager` có reachable qua dynamic import không.
