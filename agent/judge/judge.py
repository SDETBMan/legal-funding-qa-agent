from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict

class FinalReport(BaseModel):
    """INV-17: Auditable JSON report consumed by the release gate (§12)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: str
    summary: dict[str, Any]

class Judge:
    """
    LLM-driven verdict aggregation and report emission (§3).

    INV-17: Enforce float-money and evidence-quality rules before HELD verdicts.
    """

    def verdict(self, evidence_bundle: dict[str, Any]) -> dict[str, Any]:
        """INV-17: Reason over evidence and return structured verdict fields."""
        raise NotImplementedError

    def emit_report(self, run_id: str, sections: dict[str, Any], path: Path) -> FinalReport:
        """INV-17: Write artifacts/report.json with prompt version metadata."""
        raise NotImplementedError
