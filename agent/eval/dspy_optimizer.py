from __future__ import annotations

from typing import Any

import dspy
from pydantic import BaseModel, ConfigDict

class JudgeOutput(BaseModel):
    """INV-20: Structured output from an optimized Judge module for scoring."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    verdict: str
    reasoning: str

class JudgeModule(dspy.Module):
    """
    DSPy module for Judge reasoning (§8).

    INV-20: Optimized prompts must beat baseline on held-out eval before production swap.
    """

    def forward(self, evidence: dict, invariant_description: str) -> JudgeOutput:
        """INV-20: Map evidence + invariant text to verdict and reasoning."""
        raise NotImplementedError

class OptimizationResult(BaseModel):
    """INV-20: Scores and prompt hashes for audit trail."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    baseline_score: float
    optimized_score: float
    promoted: bool

class PromptOptimizationPipeline:
    """INV-20: BootstrapFewShot training with held-out gating per §8.2."""

    def run(self) -> OptimizationResult:
        """INV-20: Optimize Judge prompts only if held-out score >= baseline."""
        raise NotImplementedError
