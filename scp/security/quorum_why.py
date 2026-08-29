"""
Quorum WHY + Cross-Falsification — hội đồng AI cho ACTION NGUY HIỂM.

TẠI SAO tồn tại (Reality Check: "Nhà dân chủ mù"):
  Quorum voting thông thường (2/3 PASS) sập bẫy Ảo Giác Đồng Thuật — 3 model
  cùng bị một prompt tinh vi đánh lừa sẽ cùng vote PASS. Chống lại nó bằng
  chính phương pháp của SCP:

    1. Không vote KẾT QUẢ (WHAT) — mỗi model phải xuất trình LÝ DO (WHY):
       cây suy luận "Tại sao action này an toàn, theo điều khoản nào".
    2. Cross-Falsification: lấy WHY của model A ném cho model B với nhiệm vụ
       "BẺ GÃY lập luận này". Lập luận sống sót qua 3 vòng tấn công mới được
       duyệt. Một vết nứt duy nhất → HUMAN_REVIEW.
    3. Fail-closed tuyệt đối: model lỗi, mạng lỗi, trả lời rỗng, hoặc không
       đủ 3 WHY → HUMAN_REVIEW. Không bao giờ APPROVED khi thiếu dữ kiện.

  Đây chỉ là ĐIỀU KIỆN CẦN. Các chốt chặn cơ học (capability token, canary,
  lease/quota, postcondition verifier) là ĐIỀU KIỆN ĐỦ và nằm ngoài lớp này.
"""
from __future__ import annotations

import logging
import threading
from typing import Any, Callable

logger = logging.getLogger("scp.security.quorum_why")

WHY_SYSTEM = (
    "You are a security architect. Given a dangerous action, output a WHY argument: "
    "a short logic tree explaining why the action is safe and which safety clause covers it. "
    "Max 6 lines. If you cannot justify safety, output exactly: CANNOT_JUSTIFY."
)
ATTACK_SYSTEM = (
    "You are an adversarial reviewer. Given a safety argument for a dangerous action, "
    "try to BREAK it (missing preconditions, hidden side effects, privilege escape). "
    "If the argument survives, output exactly: NO_FALSIFICATION. "
    "Otherwise output FALSIFIED: <the hole you found>."
)

# 3 provider route khác nhau → 3 model khác nhau trong gateway warehouse.
PROVIDER_SEQUENCE = ("judge", "autofix", "why")


class QuorumReviewer:
    """WHY-quorum with cross-falsification. Injectable reviewer for tests."""

    def __init__(
        self,
        provider_sequence: tuple[str, ...] = PROVIDER_SEQUENCE,
        chat_fn: Callable[..., tuple[str | None, str]] | None = None,
    ):
        self.provider_sequence = provider_sequence
        self._chat_fn = chat_fn

    def _chat(self, prompt: str, system: str, task: str) -> str | None:
        if self._chat_fn is not None:
            content, _provider = self._chat_fn(prompt, system, task)
            return content
        from scp.llm_gateway import get_gateway

        content, _provider = get_gateway().chat_sync(prompt, system_prompt=system, task=task)
        return content

    def review(self, action_desc: str, risk_tier: str = "R2") -> dict[str, Any]:
        """Trả về decision APPROVED chỉ khi 3 WHY sống sót cross-falsification."""
        if not str(action_desc).strip():
            return self._human_review("empty_action")
        if risk_tier not in {"R2", "R3"}:
            # Quorum chỉ bắt buộc cho action rủi ro cao; R0/R1 đi cổng thường.
            return {"decision": "NOT_REQUIRED", "reason": f"risk_tier={risk_tier}"}

        arguments: list[dict[str, Any]] = []
        for task in self.provider_sequence:
            try:
                prompt = (
                    f"DANGEROUS ACTION (risk {risk_tier}): {str(action_desc)[:500]}\n"
                    "Produce the WHY argument (why is this safe?)."
                )
                content = self._chat(prompt, WHY_SYSTEM, task)
            except Exception as exc:
                return self._human_review(f"provider_error:{task}:{type(exc).__name__}")
            if not content or "CANNOT_JUSTIFY" in content.upper():
                return self._human_review(f"unjustified_by:{task}")
            arguments.append({"provider": task, "why": content.strip()[:600]})

        falsifications: list[dict[str, Any]] = []
        for idx, arg in enumerate(arguments):
            attacker = arguments[(idx + 1) % len(arguments)]["provider"]
            try:
                prompt = (
                    f"SAFETY ARGUMENT from {arg['provider']} for action "
                    f"'{str(action_desc)[:300]}':\n{arg['why']}\nBreak this argument."
                )
                verdict = self._chat(prompt, ATTACK_SYSTEM, attacker)
            except Exception as exc:
                return self._human_review(f"attack_error:{attacker}:{type(exc).__name__}")
            text = (verdict or "").upper()
            if "NO_FALSIFICATION" not in text:
                falsifications.append({"attacker": attacker, "against": arg["provider"], "finding": (verdict or "")[:300]})

        if falsifications:
            return {
                "decision": "HUMAN_REVIEW",
                "reason": "argument_broken",
                "arguments": arguments,
                "falsifications": falsifications,
            }
        return {"decision": "APPROVED", "arguments": arguments, "falsifications": []}

    @staticmethod
    def _human_review(reason: str) -> dict[str, Any]:
        return {"decision": "HUMAN_REVIEW", "reason": reason, "arguments": [], "falsifications": []}


_REVIEWER: QuorumReviewer | None = None
_REVIEWER_LOCK = threading.Lock()


def get_reviewer() -> QuorumReviewer:
    global _REVIEWER
    if _REVIEWER is None:
        with _REVIEWER_LOCK:
            if _REVIEWER is None:
                _REVIEWER = QuorumReviewer()
    return _REVIEWER
