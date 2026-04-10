from __future__ import annotations

from typing import Any

class SwarmCoordinator:
    """
    Orchestrates UI and API agents in parallel (§11, §3).

    Coordinates API adversary coverage (INV-01–INV-12) with browser work (INV-13–INV-16).
    """

    async def run_parallel(self, run_id: str) -> dict[str, Any]:
        """INV-01–INV-16: Launch API attacks, browser agent, and reconciliation; merge results."""
        raise NotImplementedError
