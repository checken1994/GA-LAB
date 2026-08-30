import logging
import asyncio
import os
from typing import Any

logger = logging.getLogger("scp.cognitive_router")

def run_pre_judge_hooks(question: str, context_dict: dict):
    """
    [V5.9-WIRE] Progressive wiring for 77,000 LOC of orphaned cognitive & security stack.
    Runs ThreatDetector, FalsificationEngine, and WhyEngine safely.
    """
    # 1. Threat Detector (Security)
    try:
        from scp.security.threat_detector import ThreatDetector
        td = ThreatDetector()
        threat_score = td.analyze(question)
        context_dict["threat_score"] = threat_score
        if threat_score.get("risk_level") == "CRITICAL":
            logger.warning(f"[SECURITY] ThreatDetector flagged query: {threat_score}")
    except Exception as e:
        logger.debug(f"ThreatDetector hook failed: {e}")

    # 2. Why Engine (Meta)
    try:
        if "tại sao" in question.lower() or "why" in question.lower():
            from scp.meta.why_engine import WhyEngine
            why = WhyEngine()
            plan = why.create_verification_plan(question)
            if plan:
                context_dict["why_plan"] = plan.__dict__
    except Exception as e:
        logger.debug(f"WhyEngine hook failed: {e}")

    # 3. Falsification Engine (Meta)
    try:
        from scp.meta.falsification_engine import FalsificationEngine
        fe = FalsificationEngine()
        hypo = fe.generate_hypotheses(question)
        if hypo:
            context_dict["falsification_hypotheses"] = hypo
    except Exception as e:
        logger.debug(f"FalsificationEngine hook failed: {e}")

    return context_dict
