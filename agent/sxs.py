"""Side-by-Side (SxS) Pairwise Report Comparison Engine.

Compares two report.json files to detect logic drift between runs or versions.
Used via ``python -m agent.main --sxs <baseline_report.json>``.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict


class SxSRow(BaseModel):
    """Per-attack comparison between baseline and current run."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    attack_name: str
    rule: str
    baseline_status: str | None
    current_status: str | None
    comparison: Literal["MATCH", "REGRESSION", "IMPROVEMENT", "NEW", "REMOVED"]


class SxSReport(BaseModel):
    """Aggregate SxS comparison results."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    matches: int
    regressions: int
    improvements: int
    new_attacks: int
    removed_attacks: int
    details: list[SxSRow]


def _classify_change(baseline_status: str | None, current_status: str | None) -> str:
    """Classify how a status changed between baseline and current."""
    if baseline_status is None:
        return "NEW"
    if current_status is None:
        return "REMOVED"
    if baseline_status == current_status:
        return "MATCH"
    # HELD → BREACHED or HELD → INDETERMINATE = regression
    # BREACHED → HELD = improvement
    if baseline_status == "HELD" and current_status in ("BREACHED", "INDETERMINATE"):
        return "REGRESSION"
    if baseline_status == "BREACHED" and current_status == "HELD":
        return "IMPROVEMENT"
    if baseline_status == "INDETERMINATE" and current_status == "BREACHED":
        return "REGRESSION"
    if baseline_status == "INDETERMINATE" and current_status == "HELD":
        return "IMPROVEMENT"
    if baseline_status == "BREACHED" and current_status == "INDETERMINATE":
        return "IMPROVEMENT"
    # Fallback: any other change is a regression
    return "REGRESSION"


def _load_adversarial(path: Path) -> dict[str, dict[str, Any]]:
    """Load report.json and return adversarial attacks keyed by name."""
    data = json.loads(path.read_text(encoding="utf-8"))
    attacks = data.get("adversarial", [])
    return {a["name"]: a for a in attacks}


def compare_reports(baseline_path: Path, current_path: Path) -> SxSReport:
    """Compare two report.json files and print a diff table.

    Returns an SxSReport with per-attack comparison details.
    """
    baseline = _load_adversarial(baseline_path)
    current = _load_adversarial(current_path)
    all_names = sorted(set(baseline.keys()) | set(current.keys()))

    rows: list[SxSRow] = []
    for name in all_names:
        b = baseline.get(name)
        c = current.get(name)
        b_status = b["status"] if b else None
        c_status = c["status"] if c else None
        b_rule = b["rule"] if b else (c["rule"] if c else "")
        c_rule = c["rule"] if c else b_rule

        comparison = _classify_change(b_status, c_status)
        rows.append(SxSRow(
            attack_name=name,
            rule=c_rule or b_rule,
            baseline_status=b_status,
            current_status=c_status,
            comparison=comparison,
        ))

    matches = sum(1 for r in rows if r.comparison == "MATCH")
    regressions = sum(1 for r in rows if r.comparison == "REGRESSION")
    improvements = sum(1 for r in rows if r.comparison == "IMPROVEMENT")
    new_attacks = sum(1 for r in rows if r.comparison == "NEW")
    removed = sum(1 for r in rows if r.comparison == "REMOVED")

    report = SxSReport(
        matches=matches,
        regressions=regressions,
        improvements=improvements,
        new_attacks=new_attacks,
        removed_attacks=removed,
        details=rows,
    )

    # Print formatted table
    headers = ("attack", "rule", "baseline", "current", "comparison")
    table_rows = [
        (
            r.attack_name,
            r.rule,
            r.baseline_status or "—",
            r.current_status or "—",
            r.comparison,
        )
        for r in rows
    ]
    widths = [max(len(h), *(len(tr[i]) for tr in table_rows)) for i, h in enumerate(headers)]
    print()
    print("=" * 80)
    print("  SxS PAIRWISE COMPARISON")
    print("=" * 80)
    print(" | ".join(h.ljust(widths[i]) for i, h in enumerate(headers)))
    print("-+-".join("-" * widths[i] for i in range(len(headers))))
    for tr in table_rows:
        print(" | ".join(tr[i].ljust(widths[i]) for i in range(len(headers))))
    print()
    print(
        f"Matches: {matches}  Regressions: {regressions}  "
        f"Improvements: {improvements}  New: {new_attacks}  Removed: {removed}"
    )

    return report
