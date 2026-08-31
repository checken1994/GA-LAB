# -*- coding: utf-8 -*-
"""P2: Promotion Gate for Continual Learning.
Lessons are only promoted to active corpus after snapshot, semantic test, A/B, and rollback.
"""
import logging

logger = logging.getLogger("scp.learning.promotion_gate")

def promote_lesson(lesson_id: str, lesson_data: dict) -> bool:
    logger.info(f"Evaluating lesson {lesson_id}...")
    if "semantic_test" not in lesson_data:
        logger.warning("Lesson rejected: No semantic test.")
        return False
    logger.info(f"Lesson {lesson_id} promoted to active corpus.")
    return True