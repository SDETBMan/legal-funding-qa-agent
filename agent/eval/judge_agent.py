from __future__ import annotations

import json
import os
from typing import Any, Literal

import structlog
from pydantic import BaseModel, ConfigDict

from agent.adversary.attacks import AttackResult

log = structlog.get_logger(__name__)

# Money field name patterns that should always be integer cents
_MONEY_FIELD_SUFFIXES = ("_cents", "_amount", "_bps", "_paid", "_balance", "_billed")


class JudgeVerdict(BaseModel):
    """INV-17: Verdict over attack evidence; must not ignore float money contamination."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    rule: str
    verdict: Literal["HELD", "BREACHED", "INDETERMINATE"]
    reasoning: str


def _check_float_contamination(evidence: dict[str, Any]) -> list[str]:
    """INV-17: Recursively scan evidence for float values in money fields."""
    violations: list[str] = []

    def _scan(obj: Any, path: str = "") -> None:
        if isinstance(obj, dict):
            for k, v in obj.items():
                child_path = f"{path}.{k}" if path else k
                if isinstance(v, float):
                    # Flag any float in a money-named field, or any float that looks like cents
                    is_money_field = any(k.endswith(s) or k.startswith("total") for s in _MONEY_FIELD_SUFFIXES)
                    if is_money_field:
                        violations.append(f"{child_path}={v!r} (float in money field)")
                _scan(v, child_path)
        elif isinstance(obj, list):
            for i, item in enumerate(obj):
                _scan(item, f"{path}[{i}]")

    _scan(evidence)
    return violations


class JudgeModule:
    """
    DSPy-compatible judge module for grading attack evidence.

    Uses dspy.Predict when a DSPy language model is configured;
    falls back to heuristic grading otherwise.
    """

    def __init__(self) -> None:
        self._dspy_available = False
        if os.environ.get("FUNDING_MOCK_LLM"):
            return
        try:
            import dspy
            if dspy.settings.lm is not None:
                self._dspy_available = True
        except Exception:
            pass

    def forward(self, rule: str, status: str, evidence: dict, reasoning: str) -> dict[str, str]:
        """
        Produce a verdict + reasoning from attack evidence.

        When DSPy is configured, uses dspy.Predict with the waterfall judge prompt.
        Otherwise, returns heuristic verdict based on the attack's own status.
        """
        if self._dspy_available:
            return self._dspy_forward(rule, status, evidence, reasoning)
        return self._heuristic_forward(rule, status, evidence, reasoning)

    def _dspy_forward(self, rule: str, status: str, evidence: dict, reasoning: str) -> dict[str, str]:
        """LLM-backed verdict via DSPy."""
        try:
            import dspy

            class JudgeSignature(dspy.Signature):
                """Judge an adversarial attack result against a financial invariant."""
                rule_id: str = dspy.InputField(desc="Invariant rule ID (e.g. INV-04)")
                attack_status: str = dspy.InputField(desc="Attack's own verdict: HELD, BREACHED, or INDETERMINATE")
                evidence_json: str = dspy.InputField(desc="JSON evidence from the attack")
                attack_reasoning: str = dspy.InputField(desc="Attack's reasoning")
                verdict: str = dspy.OutputField(desc="One of: HELD, BREACHED, INDETERMINATE")
                judge_reasoning: str = dspy.OutputField(desc="Explanation of the verdict")

            predictor = dspy.Predict(JudgeSignature)
            result = predictor(
                rule_id=rule,
                attack_status=status,
                evidence_json=json.dumps(evidence, default=str),
                attack_reasoning=reasoning,
            )
            verdict = result.verdict.strip().upper()
            if verdict not in ("HELD", "BREACHED", "INDETERMINATE"):
                verdict = "INDETERMINATE"
            return {"verdict": verdict, "reasoning": result.judge_reasoning}
        except Exception as exc:
            log.warning("dspy_judge_fallback", error=repr(exc))
            return self._heuristic_forward(rule, status, evidence, reasoning)

    def _heuristic_forward(self, rule: str, status: str, evidence: dict, reasoning: str) -> dict[str, str]:
        """Deterministic heuristic: trust the attack status unless float contamination is found."""
        float_violations = _check_float_contamination(evidence)
        if float_violations and status == "HELD":
            return {
                "verdict": "BREACHED",
                "reasoning": (
                    f"INV-17 override: attack reported HELD but evidence contains float money "
                    f"contamination: {'; '.join(float_violations)}. Upgrading to BREACHED."
                ),
            }
        return {"verdict": status, "reasoning": f"Heuristic: trusting attack verdict. {reasoning}"}


class JudgeAgent:
    """
    Grades other agents' outputs and attack evidence.

    INV-17: Reject HELD if evidence contains float in any money field.
    INV-18: Detect cross-case PII leakage in RAG-style evidence bundles.
    """

    def __init__(self) -> None:
        self._module = JudgeModule()

    def grade_attack(self, result: AttackResult) -> JudgeVerdict:
        """INV-17: Produce verdict from AttackResult evidence with float-money guardrails."""
        # Step 1: Check for float contamination (INV-17 hard rule)
        float_violations = _check_float_contamination(result.evidence)

        if float_violations and result.status == "HELD":
            return JudgeVerdict(
                rule=result.rule,
                verdict="BREACHED",
                reasoning=(
                    f"INV-17: Attack reported HELD but evidence contains float money "
                    f"contamination: {'; '.join(float_violations)}. "
                    "Cannot mark as HELD when money fields are floats."
                ),
            )

        # Step 2: Delegate to LLM or heuristic module
        module_result = self._module.forward(
            rule=result.rule,
            status=result.status,
            evidence=result.evidence,
            reasoning=result.reasoning,
        )

        verdict = module_result.get("verdict", "INDETERMINATE")
        if verdict not in ("HELD", "BREACHED", "INDETERMINATE"):
            verdict = "INDETERMINATE"

        return JudgeVerdict(
            rule=result.rule,
            verdict=verdict,
            reasoning=module_result.get("reasoning", ""),
        )

    def grade_rag_response(self, case_id: str, retrieved_chunks: list[dict[str, Any]]) -> JudgeVerdict:
        """INV-18: Ensure retrieved content does not include PII from other cases."""
        foreign_chunks: list[dict[str, Any]] = []
        for chunk in retrieved_chunks:
            chunk_case = chunk.get("case_id")
            if chunk_case and str(chunk_case) != str(case_id):
                foreign_chunks.append(chunk)

        if foreign_chunks:
            return JudgeVerdict(
                rule="INV-18",
                verdict="BREACHED",
                reasoning=(
                    f"RAG response for case {case_id} contains {len(foreign_chunks)} chunk(s) "
                    f"from other cases: {[c.get('case_id') for c in foreign_chunks]}. "
                    "Cross-case PII leakage detected."
                ),
            )
        return JudgeVerdict(
            rule="INV-18",
            verdict="HELD",
            reasoning=f"All {len(retrieved_chunks)} retrieved chunks belong to case {case_id}.",
        )
