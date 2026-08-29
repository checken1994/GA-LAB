"""Quorum WHY + cross-falsification — hermetic (fake gateway, không mạng)."""
from __future__ import annotations

from scp.security.quorum_why import QuorumReviewer


def _fake_chat_factory(safety="NO_FALSIFICATION", justify=True, fail_on=None):
    def chat(prompt, system, task):
        # Gateway contract: (content, provider_name)
        if fail_on and task == fail_on:
            raise ConnectionError("provider down")
        if system.startswith("You are an adversarial"):
            return safety, f"fake:{task}"
        content = (
            "1. action scoped\n2. capability token present\n3. clause FS_WRITE covers it"
            if justify else "CANNOT_JUSTIFY"
        )
        return content, f"fake:{task}"

    return chat


def test_unanimous_surviving_arguments_approve():
    reviewer = QuorumReviewer(chat_fn=_fake_chat_factory())
    result = reviewer.review("Delete temp build artifacts in sandbox", "R2")
    assert result["decision"] == "APPROVED"
    assert len(result["arguments"]) == 3
    assert result["falsifications"] == []


def test_single_broken_argument_sends_to_human():
    reviewer = QuorumReviewer(chat_fn=_fake_chat_factory(safety="FALSIFIED: no disk quota check"))
    result = reviewer.review("Delete temp build artifacts in sandbox", "R2")
    assert result["decision"] == "HUMAN_REVIEW"
    assert result["reason"] == "argument_broken"
    assert len(result["falsifications"]) == 3


def test_unjustifiable_action_never_approved():
    reviewer = QuorumReviewer(chat_fn=_fake_chat_factory(justify=False))
    result = reviewer.review("Grant CAP_SYS_ADMIN to session", "R3")
    assert result["decision"] == "HUMAN_REVIEW"
    assert result["reason"].startswith("unjustified_by")


def test_provider_failure_fails_closed():
    reviewer = QuorumReviewer(chat_fn=_fake_chat_factory(fail_on="autofix"))
    result = reviewer.review("Format production disk", "R3")
    assert result["decision"] == "HUMAN_REVIEW"
    assert result["reason"].startswith("provider_error")


def test_low_risk_actions_skip_quorum():
    reviewer = QuorumReviewer(chat_fn=_fake_chat_factory())
    assert reviewer.review("read config", "R0")["decision"] == "NOT_REQUIRED"


def test_empty_action_fails_closed():
    reviewer = QuorumReviewer(chat_fn=_fake_chat_factory())
    assert reviewer.review("   ", "R3")["decision"] == "HUMAN_REVIEW"
