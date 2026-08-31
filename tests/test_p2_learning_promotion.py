from __future__ import annotations

import unittest
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scp.learning.promotion_gate import promote_lesson

class TestP2LearningPromotion(unittest.TestCase):
    def test_promotion_gate_rejects_untested(self):
        """
        P2: Learning Semantic Truth.
        A lesson without a semantic test must be rejected.
        """
        lesson_data = {
            "title": "Use path module",
            "content": "Do not hardcode paths."
        }
        result = promote_lesson("lesson_1", lesson_data)
        self.assertFalse(result, "Lesson without semantic test MUST be rejected.")

    def test_promotion_gate_accepts_tested(self):
        """
        P2: Learning Semantic Truth.
        A lesson WITH a semantic test and A/B proof can be promoted.
        """
        lesson_data = {
            "title": "Use path module",
            "content": "Do not hardcode paths.",
            "semantic_test": {"status": "PASS", "coverage": 100},
            "ab_test": {"improvement": True}
        }
        result = promote_lesson("lesson_2", lesson_data)
        self.assertTrue(result, "Lesson with semantic test should be promoted.")

if __name__ == "__main__":
    unittest.main()