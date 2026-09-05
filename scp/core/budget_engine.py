"""
Budget preferences constrained by SCP's zero-cost authority.

Difficulty scoring is deterministic and has no network effects. It may inform
quality selection within eligible models, but never authorize a paid tier.
The gateway checks fresh pricing evidence for every selected candidate.
"""

from __future__ import annotations

import os
import re

_HARD_SIGNALS = tuple(
    re.compile(p, re.IGNORECASE)
    for p in (
        r"race condition|deadlock|concurr|thread|mutex",
        r"memory leak|stack overflow|segfault|crash",
        r"security|injection|bypass|exploit|privilege",
        r"architecture|refactor|design|protocol|state machine",
        r"async|await|event loop|callback",
        r"algorithm|complexity|optimize",
    )
)
_EASY_SIGNALS = tuple(
    re.compile(p, re.IGNORECASE)
    for p in (
        r"typo|spelling|syntax|import statement|rename",
        r"\blog(ging)?\b|comment|docstring",
        r"\bprint\b|variable name",
    )
)


def difficulty_score(text: str) -> float:
    """Điểm độ khó >= 0 (deterministic). Càng cao càng cần model mạnh."""
    if not text:
        return 0.0
    score = 0.0
    for pattern in _HARD_SIGNALS:
        if pattern.search(text):
            score += 10.0
    for pattern in _EASY_SIGNALS:
        if pattern.search(text):
            score -= 3.0
    # Input dài = context nặng = chi phí thật
    score += min(len(text) / 2000.0, 5.0)
    return round(max(score, 0.0), 2)


def route_tier(text: str, task: str = "default", hard_threshold: float = 10.0) -> str:
    """Budget preference cannot authorize a tier outside the zero-cost wall."""
    mode = os.environ.get("SCP_LLM_COST_MODE", "free_only").strip().lower()
    if mode != "free_only":
        raise ValueError("SCP budget routing requires free_only")
    return "free_first"


def order_tiers(text: str, task: str = "default", hard_threshold: float = 10.0) -> list[str]:
    """Only verified-free candidates may be ranked downstream by the gateway."""
    route_tier(text, task, hard_threshold)
    return ["free"]
