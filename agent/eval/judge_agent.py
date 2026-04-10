from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

from agent.adversary.attacks import AttackResult

class JudgeVerdict(BaseModel):
    """INV-17: Verdict over attack evidence; must not ignore float money contamination."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    rule: str
    verdict: Literal["HELD", "BREACHED", "INDETERMINATE"]
    reasoning: str

class JudgeAgent:
    """
    Grades other agents' outputs and attack evidence (§3).

    INV-17: Reject HELD if evidence contains float in any money field.
    INV-18: Detect cross-case PII leakage in RAG-style evidence bundles.
    """

    def grade_attack(self, result: AttackResult) -> JudgeVerdict:
        """INV-17: Produce verdict from AttackResult evidence with float-money guardrails."""
        raise NotImplementedError

    def grade_rag_response(self, case_id: str, retrieved_chunks: list[dict[str, Any]]) -> JudgeVerdict:
        """INV-18: Ensure retrieved content does not include PII from other cases."""
        raise NotImplementedError
