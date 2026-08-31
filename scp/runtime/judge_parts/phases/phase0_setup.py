from typing import Any
from scp.runtime.judge_parts.phases.context import JudgeContext
import time
from datetime import datetime
import os
import logging
logger = logging.getLogger(__name__)

class Phase0SetupMixin:
    def _phase0_setup(self, ctx: JudgeContext) -> Any:
            ctx.ts = datetime.now().isoformat()
            ctx._judge_start_perf = time.perf_counter()  # [V93.9] measure total judge() duration
            
            #  Per-phase timer — 11 timestamps
            from scp.runtime.timing_and_restart import PhaseTimer, QueryTimeoutError, check_timeout
            ctx._v100_timer = PhaseTimer()
            
            # [V104.39 #A] Define _enable_closed_loop ONCE at top of judge() — used by
            # WHY engine (line ~1227), PolicyApplier (line ~1360), VerdictPredictor (line ~1378),
            # and feedback record_outcome (line ~2108). All must use the SAME env var.
            ctx._enable_closed_loop = os.environ.get("SCP_ENABLE_CLOSED_LOOP", "1") == "1"
            
            #  TẠI SAO: Multiple V104.40-V104.45 "fixes" (bugs K/CB/BX/BA) reference
            # `verdict`, `verdict_type`, `reasoning` BEFORE they are assigned:
            #   - Step 0b (UnifiedDetector, ~line 1365): `verdict.evidence[...]` before verdict created (~2251)
            #   - Step 5.5 (Adversary, ~line 1794): `if verdict_type == "PASS"` before Step 6 sets it
            #   - ErrorStoreIndex (~line 1436): `verdict.evidence[...]` before verdict created
            # Each raised NameError, swallowed by `except Exception as e: pass` → the fixes were
            # cosmetically present but functionally DEAD. Reality: "ảo giác đồng thuận" —
            # code looks like 10 fixes agree, but all share one dead lineage.
            # Fix: initialize all three to None/"" up here. Pre-verdict evidence writes go
            # into `_pre_verdict_evidence` dict and are merged into verdict.evidence AFTER
            # verdict creation. Adversary conflict is recorded as a flag and applied post-Step-6.
            ctx.verdict = None
            ctx.verdict_type = None
            ctx.final_answer = ""
            ctx.confidence = 0.0
            ctx.verdict_evidence_spec = None
            ctx.reasoning = ""
            ctx._pre_verdict_evidence: dict[str, Any] = {}
            ctx._adversary_conflict = False
            ctx._adversary_conflict_reason = ""
            ctx._es_index_threshold_boost = 0.0  # ErrorStoreIndex similar-FAIL threshold raise
            
            # [V104.39 #F] TẠI SAO: V90 OPT skipped WHY engine → Evidence-First not operational.
            # Re-enabled via SCP_ENABLE_CLOSED_LOOP=1 (same guard as Policy).
            # [Task 45-B] WHY engine block extracted to _run_why_engine() to reduce judge() CC.
            ctx.why_plan, ctx.why_result = self._run_why_engine(ctx.question, ctx.ai_answer, ctx._enable_closed_loop)
            
            # ============================================================
            # [Task 40-B / OPT-1] KnowledgeArbiter — resolve cross-source conflicts.
            # TẠI SAO: KnowledgeArbiter instantiated in judge.__init__ (line ~642)
            # but NEVER called on the judge() hot path → dead code (DNA #6 violated).
            # Wire here, AFTER why_result has collected multi-source values but
            # BEFORE verdict construction. ADDITIVE: does not modify why_engine
            # logic; only consults arbiter and logs conflicts. Arbiter facts are
            # added per-judge-call (short-lived) — same pattern as why_result.
            # [OPT-42] Extracted to _check_knowledge_conflicts() to reduce judge() CC.
            # ============================================================
            self._check_knowledge_conflicts(ctx.why_result, ctx.why_plan, ctx.question, ctx._pre_verdict_evidence)
            
            # ============================================================
        
