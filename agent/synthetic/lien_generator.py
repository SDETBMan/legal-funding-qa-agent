from __future__ import annotations

from typing import Any

class LienPortfolioGenerator:
    """
    Multi-party lien portfolios for waterfall attacks (§3).

    INV-07: Medicare/Medicaid super-priority ordering scenarios.
    INV-08: Medical lien balances bounded by original billed amounts.
    """

    def generate(self, case_id: str, seed: int) -> list[dict[str, Any]]:
        """INV-07, INV-08: Emit lien graph structures with valid priority_rank and billed caps."""
        raise NotImplementedError
