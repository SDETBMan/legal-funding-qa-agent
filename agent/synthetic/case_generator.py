from __future__ import annotations

from pydantic import BaseModel, ConfigDict

class CasePortfolio(BaseModel):
    """INV-01, INV-18: Linked cases, fundings, and documents for swarm and RAG stress."""

    model_config = ConfigDict(extra="allow", frozen=True)

    portfolio_id: str
    cases: list[dict]

class LegalCaseFactory:
    """
    Legal case + funding portfolio scenarios (§10.2).

    Profiles exercise INV-01 (multi-funder), INV-07 (Medicare priority), INV-18 (cross-case similarity), etc.
    """

    def generate(
        self,
        profile: str = "standard",
        count: int = 1,
        seed: int = 42,
    ) -> list[CasePortfolio]:
        """INV-01, INV-18: Deterministic portfolios keyed by seed; no brittle hardcoded payoffs."""
        raise NotImplementedError
