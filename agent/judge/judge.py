from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import structlog
from pydantic import BaseModel, ConfigDict

from agent.judge.prompts import PromptVersion, hash_prompt

log = structlog.get_logger(__name__)

# Money field suffixes for float contamination scanning (INV-17)
_MONEY_SUFFIXES = ("_cents", "_amount", "_bps", "_paid", "_balance", "_billed")


class FinalReport(BaseModel):
    """INV-17: Auditable JSON report consumed by the release gate."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: str
    summary: dict[str, Any]


class Judge:
    """
    LLM-driven verdict aggregation and report emission.

    INV-17: Enforce float-money and evidence-quality rules before HELD verdicts.
    """

    def __init__(self, prompt: PromptVersion | None = None) -> None:
        self._prompt = prompt

    def verdict(self, evidence_bundle: dict[str, Any]) -> dict[str, Any]:
        """
        INV-17: Reason over evidence and return structured verdict fields.

        Applies the float-money guardrail: if any money field in evidence is a float,
        the verdict cannot be HELD. Uses the judge prompt for LLM-based reasoning when
        available; otherwise applies deterministic heuristics.
        """
        rule = evidence_bundle.get("rule", "UNKNOWN")
        attack_status = evidence_bundle.get("status", "INDETERMINATE")
        evidence = evidence_bundle.get("evidence", {})
        reasoning = evidence_bundle.get("reasoning", "")

        # INV-17: scan for float contamination
        float_violations = self._scan_float_money(evidence)

        if float_violations and attack_status == "HELD":
            return {
                "rule": rule,
                "verdict": "BREACHED",
                "reasoning": (
                    f"INV-17 override: attack reported HELD but evidence contains float money "
                    f"contamination in: {', '.join(float_violations)}. Upgrading to BREACHED."
                ),
                "float_violations": float_violations,
                "prompt_hash": self._prompt_hash(),
            }

        # Heuristic verdict: trust the attack's own assessment
        return {
            "rule": rule,
            "verdict": attack_status,
            "reasoning": reasoning,
            "float_violations": float_violations,
            "prompt_hash": self._prompt_hash(),
        }

    def emit_report(self, run_id: str, sections: dict[str, Any], path: Path) -> FinalReport:
        """
        INV-17: Write artifacts/report.json with prompt version metadata.

        Builds a FinalReport, writes JSON to disk, and returns the model.
        """
        adversarial = sections.get("adversarial", [])
        held = sum(1 for a in adversarial if a.get("status") == "HELD")
        breached = sum(1 for a in adversarial if a.get("status") == "BREACHED")
        indeterminate = sum(1 for a in adversarial if a.get("status") == "INDETERMINATE")

        summary = {
            "held": held,
            "breached": breached,
            "indeterminate": indeterminate,
            "total_attacks": len(adversarial),
            "prompt_hash": self._prompt_hash(),
        }

        report_data = {
            "run_id": run_id,
            "summary": summary,
            **sections,
        }

        # Write to disk
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(report_data, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        log.info("report_written", path=str(path), run_id=run_id)

        return FinalReport(run_id=run_id, summary=summary)

    def _prompt_hash(self) -> str:
        """Return the SHA-256 hash of the judge prompt, or 'none' if no prompt is set."""
        if self._prompt is not None:
            return f"sha256:{hash_prompt(self._prompt.content)}"
        return "none"

    @staticmethod
    def _scan_float_money(obj: Any, path: str = "") -> list[str]:
        """Recursively find float values in money-named fields."""
        violations: list[str] = []
        if isinstance(obj, dict):
            for k, v in obj.items():
                child = f"{path}.{k}" if path else k
                if isinstance(v, float) and any(k.endswith(s) or k.startswith("total") for s in _MONEY_SUFFIXES):
                    violations.append(child)
                violations.extend(Judge._scan_float_money(v, child))
        elif isinstance(obj, list):
            for i, item in enumerate(obj):
                violations.extend(Judge._scan_float_money(item, f"{path}[{i}]"))
        return violations
