' JudgeVerdict, _AllowedByWatchlist\nSCP V90 — Reality Judge Module\nCross-check SLMs, verify with reality, produce final verdicts.\nExtracted from engine.py for modularity.\n\n[G4-FIX P0-12] REALITY-CHECK ON THE "10-PHASE PIPELINE" CLAIM:\nThe project doc (SCP_FULL_CONTEXT_FOR_AI.md §2.2) claims judge.judge() is a\n"10-phase pipeline" (Phase 1 DoS → 2 Multimodal → 3 Chatbot → 4 SmartClassifier\n→ 5 SLM → 6 KB → 7 Reality → 8 Consistency → 9 Governance → 10 Antibody →\n11 API boundary). That claim is FICTION. The ACTUAL judge() method (this file,\nL74-2305, 2232 LOC, CC≈300) is a single god method with ~27 distinct phases\nwhose inline numbering is contradictory (PHASE 1 / STEP 0 / Step 1 / Step 2 /\nStep 5.5 / Step 6 / Step 7 / Step 9 / STEP 9-again / PHASE 6 / PHASE 6.5 /\nPHASE 10 / PHASE 11 — see judge() docstring for the full table).\n\n`scp/runtime/judge_parts/judge_phases.py` defines only 6 phases and is NOT\nwired into THIS method. It runs in SHADOW MODE from judge.py:927 (the async\nwrapper `judge_async`) for comparison logging only — never sets the production\nverdict. See that file\'s docstring for its honest status.\n\nFull split of judge() into 10 phase modules = 21-day refactor, DEFERRED\n(worklog Task G4-C). This file documents reality instead of pretending.\n'

import asyncio

import logging

import os

import time

from dataclasses import dataclass

from datetime import datetime

from typing import TYPE_CHECKING, Any

from scp.core.db_manager import db_exec

from scp.core.evidence_filter import filter_slm_responses

from scp.meta.severity import Severity

from scp.runtime.judge_parts.types import JudgeVerdict, _AllowedByWatchlist

if TYPE_CHECKING:
    pass

from scp.meta.scp_meta import SCPMeta as _SCPMeta

logger = logging.getLogger('scp.judge')

_MULTI_LLM_CHECKER_SINGLETON = None

_MULTI_LLM_CHECKER_LOCK = __import__('threading').Lock()

def _get_multi_llm_checker():
    """Lazy singleton for MultiLLMChecker. Returns None if env var OFF."""
    global _MULTI_LLM_CHECKER_SINGLETON
    if os.environ.get('SCP_MULTI_LLM_CHECK', '0') != '1':
        return None
    if _MULTI_LLM_CHECKER_SINGLETON is None:
        with _MULTI_LLM_CHECKER_LOCK:
            if _MULTI_LLM_CHECKER_SINGLETON is None:
                try:
                    from scp.meta.multi_llm_check import MultiLLMChecker
                    _MULTI_LLM_CHECKER_SINGLETON = MultiLLMChecker()
                    logger.info('[V5.3-WIRE] MultiLLMChecker initialized — adversary answers will be cross-checked')
                except Exception as e:
                    logger.warning(f'[V5.3-WIRE] MultiLLMChecker init failed: {e} — multi-LLM check disabled')
                    _MULTI_LLM_CHECKER_SINGLETON = False
    return _MULTI_LLM_CHECKER_SINGLETON if _MULTI_LLM_CHECKER_SINGLETON is not False else None

def _build_governance_antibody_results(slm_responses: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    """Translate SLM response records into Governance's canonical format.

    Provider records use ``error`` as a transport/status field, whereas
    Governance consumes policy severities. The adapter must therefore emit a
    canonical ``Severity`` value and keep failures as ``passed=False``.
    """
    results: list[dict[str, Any]] = []
    for response in slm_responses or []:
        has_error = 'error' in response
        confidence = response.get('confidence', 0.0)
        results.append({'passed': has_error is False and confidence >= 0.5, 'severity': Severity.MEDIUM.value if has_error else Severity.WARNING.value if confidence < 0.5 else Severity.INFO.value, 'antibody': response.get('antibody_name', response.get('slm_name', 'unknown')), 'details': response.get('details', response.get('error', response.get('reasoning', '')))})
    return results

from .judgecore_mixin_parts.judgecoremixin import JudgeCoreMixin
