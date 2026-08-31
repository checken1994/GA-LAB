from typing import Any
from scp.runtime.judge_parts.phases.context import JudgeContext
import time
from datetime import datetime
import os
import logging
logger = logging.getLogger(__name__)

class Phase8CounterResponseMixin:
    def _phase8_counter_response(self, ctx: JudgeContext) -> Any:
            #  STEP 9: COUNTER RESPONSE — chạy SAU Governance
            # ============================================================
            
            # 9a. AttackPolicyEngine — decide counter phase
            ctx.v98_policy = None
            ctx.v98_counter_result = None
            if self.attack_policy:
                try:
                    ctx.classification_dict = ctx.v98_classification.to_dict() if ctx.v98_classification else {
                        "actor": "human",
                        "attack_type": "none",
                        "severity": "none",
                        "confidence": ctx.verdict.ctx.confidence,
                    }
                    # If attack_match from AttackPatternMemory → boost severity
                    if ctx.v98_attack_match and ctx.v98_attack_match.get("matched"):
                        ctx.classification_dict["attack_type"] = "injection"
                        ctx.classification_dict["severity"] = "high"
            
                    ctx.target_verification = None
                    if ctx.v98_threat_signal and ctx.v98_threat_signal.asn_intel:
                        ctx.target_verification = {
                            "safe_to_counter": not ctx.v98_threat_signal.asn_intel.get("is_residential", False)
                                              and not ctx.v98_threat_signal.asn_intel.get("is_tor", False),
                            "is_residential": ctx.v98_threat_signal.asn_intel.get("is_residential", False),
                            "is_tor": ctx.v98_threat_signal.asn_intel.get("is_tor", False),
                        }
            
                    ctx.governance_dict = {
                        "decision": ctx.verdict.evidence.get("governance_decision", "UPHOLD"),
                    }
            
                    ctx.v98_policy = self.attack_policy.decide(
                        classification=ctx.classification_dict,
                        target_verification=ctx.target_verification,
                        governance_decision=ctx.governance_dict,
                    )
                    ctx.verdict.evidence["v98_attack_policy"] = ctx.v98_policy.to_dict()
                except Exception as e:
                    logger.debug(f" AttackPolicyEngine error: {e}")
            
            # 9b. CounterResponseEngine — execute counter if phase > 0
            if ctx.v98_policy and ctx.v98_policy.phase > 0 and self.counter_response:
                try:
                    ctx.attacker_ip = (ctx.v98_context or {}).get("ip", "internal")
                    ctx.attack_type = (ctx.v98_classification.ctx.attack_type if ctx.v98_classification
                                  else ctx.v98_attack_match.get("attack_type", "injection") if ctx.v98_attack_match
                                  else "injection")
                    # [V104.33 #16 FIX] CounterResponse Phase 3 was dead code:
                    #   OLD: _cr_pool.submit(_a.run, execute(...)) — coroutine called sync,
                    #        Future discarded, v98_counter_result stayed None,
                    #        except-block checked None.modified_response → AttributeError → swallowed
                    #   NEW: call _a.run(execute(...)) directly, capture result,
                    #        update verdict.final_answer on SUCCESS path (not in except)
                    import asyncio as _a
                    try:
                        ctx.v98_counter_result = _a.run(
                            self.counter_response.execute(
                                policy=ctx.v98_policy, attacker_ip=ctx.attacker_ip,
                                original_response=ctx.verdict.ctx.final_answer, attack_type=ctx.attack_type,
                            )
                        )
                        # [V104.33 #16] SUCCESS path — wire poison_response into final_answer
                        if ctx.v98_counter_result and ctx.v98_counter_result.modified_response:
                            if "poison_response" in ctx.v98_counter_result.actions:
                                ctx.verdict.ctx.final_answer = ctx.v98_counter_result.modified_response
                                ctx.verdict.evidence["v98_counter_response"] = {
                                    "actions": ctx.v98_counter_result.actions,
                                    "phase": ctx.v98_policy.phase,
                                    "canary_token": ctx.v98_counter_result.canary_token,
                                }
                    except RuntimeError as re:
                        # [V104.33 #16] If event loop already running, fall back to thread pool
                        logger.debug(f" CounterResponse asyncio.run fallback: {re}")
                        import concurrent.futures as _cf
                        try:
                            ctx._cr_pool = _cf.ThreadPoolExecutor(max_workers=1)
                            ctx._future = ctx._cr_pool.submit(
                                _a.run,
                                self.counter_response.execute(
                                    policy=ctx.v98_policy, attacker_ip=ctx.attacker_ip,
                                    original_response=ctx.verdict.ctx.final_answer, attack_type=ctx.attack_type,
                                )
                            )
                            ctx.v98_counter_result = ctx._future.ctx.result(timeout=10)
                            ctx._cr_pool.shutdown(wait=False)
                            if ctx.v98_counter_result and ctx.v98_counter_result.modified_response:
                                if "poison_response" in ctx.v98_counter_result.actions:
                                    ctx.verdict.ctx.final_answer = ctx.v98_counter_result.modified_response
                                    ctx.verdict.evidence["v98_counter_response"] = {
                                        "actions": ctx.v98_counter_result.actions,
                                        "phase": ctx.v98_policy.phase,
                                        "canary_token": ctx.v98_counter_result.canary_token,
                                    }
                        except Exception as e2:
                            logger.debug(f" CounterResponse thread fallback error: {e2}")
                except Exception as e:
                    logger.debug(f" CounterResponseEngine error: {e}")
            
            # 9c. CanaryTokenMonitor — generate canary if Phase 2+
            if ctx.v98_policy and ctx.v98_policy.phase >= 2 and self.canary_monitor:
                try:
                    ctx.attacker_ip = (ctx.v98_context or {}).get("ip", "internal")
                    ctx.canary = self.canary_monitor.generate(ctx.attacker_ip)
                    ctx.verdict.evidence["v98_canary_token"] = ctx.canary.token
                except Exception as e:
                    logger.debug(f" CanaryTokenMonitor error: {e}")
            
            # 9d. AttackPatternMemory — record bypass if verdict=PASS but attack detected
            if self.attack_memory and ctx.verdict.ctx.verdict == "PASS":
                # [FIX #11] actor="unknown" alone is NOT attack
                ctx._attacker_actors = {"bot_legacy", "scanner", "attacker", "exploit_tool"}
                ctx.is_attack = (
                    (ctx.v98_attack_match and ctx.v98_attack_match.get("matched")) or
                    (ctx.v98_guard_verdict and ctx.v98_guard_verdict.is_poisoned) or
                    (ctx.v98_classification
                     and ctx.v98_classification.actor in ctx._attacker_actors
                     and getattr(ctx.v98_classification, "severity", "low") in ("medium", "high", "critical"))
                )
                if ctx.is_attack:
                    try:
                        ctx.attack_type = (ctx.v98_classification.ctx.attack_type if ctx.v98_classification
                                      else ctx.v98_attack_match.get("attack_type", "injection") if ctx.v98_attack_match
                                      else "injection")
                        ctx.signatures = ctx.v98_classification.strong_signals if ctx.v98_classification else []
                        self.attack_memory.record_bypass(
                            question=ctx.question[:500],
                            answer=ctx.verdict.ctx.final_answer[:500],
                            attack_type=ctx.attack_type,
                            signatures=ctx.signatures,
                        )
                        ctx.verdict.evidence["v98_bypass_recorded"] = True
                        # [V104.42 #BA] TẠI SAO: bypass was logged but answer kept → client
                        # received full PASS answer despite jailbreak detection.
                        # Constitution: "abstain rather than fabricate".
                        # Fix: downgrade PASS → FAIL + clear answer when bypass detected.
                        if ctx.verdict.ctx.verdict == "PASS":
                            ctx.verdict.ctx.verdict = "FAIL"
                            ctx.verdict.ctx.final_answer = "[SCP: Answer withheld — bypass detected]"
                            ctx.verdict.ctx.reasoning += " | [V104.42 #BA] Bypass detected → FAIL + abstain"
                            ctx.verdict.evidence["bypass_retract"] = True
                        logger.warning("[V104.42 #BA] Bypass retract: verdict downgraded PASS → FAIL")
                        # [V104.44 #CV] Notify on bypass detection
                        if self.notifications:
                            try:
                                self.notifications.notify(
                                    event_type="bypass_detected",
                                    title="Bypass Detected",
                                    message=f"Question: {ctx.question[:100]}\nAttack: {ctx.attack_type}",
                                    severity="critical",
                                )
                            except Exception as e:
                                # [ROOT-FIX 5] Was `except Exception as e: pass` — swallowed
                                # notification dispatch errors silently → operators miss
                                # critical bypass alerts.
                                logger.warning(f"[judge] bypass_detected notify failed: {e}")
                    except Exception as e:
                        logger.debug(f" AttackPatternMemory record error: {e}")
            
            # 9e. Store V98 input detection results in evidence
            if ctx.v98_guard_verdict:
                ctx.verdict.evidence["v98_guard_verdict"] = ctx.v98_guard_verdict.to_dict()
            if ctx.v98_threat_signal:
                ctx.verdict.evidence["v98_threat_signal"] = ctx.v98_threat_signal.to_dict()
            if ctx.v98_classification:
                ctx.verdict.evidence["v98_classification"] = ctx.v98_classification.to_dict()
            if ctx.v98_attack_match:
                ctx.verdict.evidence["v98_attack_match"] = ctx.v98_attack_match
            
            # ============================================================
        
