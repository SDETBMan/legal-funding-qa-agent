from __future__ import annotations

from agent.adversary.attacks import AttackResult

class FinancialRedTeamAgent:
    """
    Adversarial agent for financial edge cases (§9).

    Stresses API-layer invariants INV-01 through INV-12 using synthetic and boundary inputs.
    """

    def run(self, invariant_id: str) -> AttackResult:
        """INV-01–INV-12: Plan inputs, execute via clients, return evidence for the Judge."""
        raise NotImplementedError
