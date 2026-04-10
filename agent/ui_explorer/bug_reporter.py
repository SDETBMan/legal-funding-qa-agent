from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict

class UIBugReport(BaseModel):
    """INV-13–INV-16: Structured agent-authored bug artifact for artifacts/ui_bugs/."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    bug_id: str
    invariant: str
    goal: str
    severity: str
    steps_to_reproduce: list[str]
    evidence: dict[str, Any]

def write_bug_report(report: UIBugReport, artifacts_dir: Path) -> Path:
    """INV-13–INV-16: Persist JSON bug report under artifacts/ui_bugs/."""
    raise NotImplementedError
