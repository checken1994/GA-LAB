# Auto-extracted from domain_registry.py
import logging
from typing import Any, Optional

def search_domains_by_keyword(query: str) -> list[str]:
    """
    Tìm domains có keyword match trong query.
    Trả về list domain ids sorted by match score.

    [V53 FIX] Use word-boundary matching for short keywords (<=4 chars)
    Trước V53: "AI" matched "r**AI**ndom" → false positive routing
    V53: short keywords require word boundary, long keywords use substring
    """
    if not query:
        return []
    import re
    q_lower = query.lower()
    scores: dict[str, int] = {}
    for domain_id, meta in DOMAINS.items():
        score = 0
        for kw in meta.get('keywords', []):
            kw_lower = kw.lower()
            if len(kw_lower) <= 4:
                pattern = '\\b' + re.escape(kw_lower) + '\\b'
                if re.search(pattern, q_lower):
                    score += len(kw_lower)
            elif kw_lower in q_lower:
                score += len(kw_lower)
        if score > 0:
            scores[domain_id] = score
    return sorted(scores.keys(), key=lambda d: -scores[d])
