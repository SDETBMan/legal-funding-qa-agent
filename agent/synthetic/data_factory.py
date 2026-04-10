from __future__ import annotations

from typing import Any

class RelationalDataFactory:
    """
    Base relational synthetic data entry point (§10, §3).

    INV-19: Generators must not embed hardcoded money literals — derive amounts from parameters or API-shaped fixtures.
    """

    def __init__(self, random_seed: int) -> None:
        self._random_seed = random_seed

    def build_portfolio_graph(self, spec: dict[str, Any]) -> dict[str, Any]:
        """INV-19: Create linked entities without hardcoded cent literals in generator code."""
        raise NotImplementedError
