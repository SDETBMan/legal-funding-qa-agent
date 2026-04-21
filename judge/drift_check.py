"""
Pre-deploy judge prompt drift check (Drift Triangle).

Compares live :mod:`judge.prompts` fingerprints to ``config/judge_prompt_baseline.json``.
If a prompt body changed without updating the baseline (after eval), log a warning.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import structlog

from judge.prompts import JUDGE_PROMPT_KEYS, get_prompt_fingerprints, get_prompt_registry

log = structlog.get_logger(__name__)


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def baseline_path() -> Path:
    return _repo_root() / "config" / "judge_prompt_baseline.json"


def load_baseline() -> dict[str, Any] | None:
    path = baseline_path()
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        log.error("judge_baseline_unreadable", path=str(path), error=str(exc))
        return None


def check_judge_prompt_drift() -> list[str]:
    """
    Compare current prompt hashes to the last-known-good baseline.

    Returns human-readable warning strings (empty if no drift vs baseline, or baseline missing
    with policy left to caller).
    """
    registry = get_prompt_registry()
    current = get_prompt_fingerprints()
    baseline = load_baseline()

    warnings: list[str] = []

    if baseline is None:
        warnings.append(
            f"Judge prompt baseline missing: {baseline_path()}. "
            "Create it from eval-approved hashes (see judge.prompts.export_baseline_dict)."
        )
        return warnings

    prompts_baseline = baseline.get("prompts")
    if not isinstance(prompts_baseline, dict):
        warnings.append("Baseline file invalid: missing top-level 'prompts' object.")
        return warnings

    if not prompts_baseline:
        warnings.append(
            "Judge prompt baseline is empty. After a passing held-out eval (INV-20), run "
            "`python -m agent.main --write-judge-baseline` and commit `config/judge_prompt_baseline.json`."
        )
        return warnings

    for key in JUDGE_PROMPT_KEYS:
        if key not in registry:
            warnings.append(f"Internal error: prompt key {key!r} not in registry.")
            continue

        cur_sha = str(current[key]["sha256"])
        cur_eval = current[key].get("eval_score")

        row = prompts_baseline.get(key)
        if not isinstance(row, dict):
            warnings.append(
                f"Judge prompt {key!r} has no baseline row — add sha256/eval_score after eval (Drift Triangle)."
            )
            continue

        base_sha = row.get("sha256")
        base_eval = row.get("eval_score")

        if base_sha != cur_sha:
            warnings.append(
                f"Judge prompt drift: {key!r} current_sha256={cur_sha} baseline_sha256={base_sha!r}. "
                "Run held-out judge eval (INV-20) and update baseline if approved."
            )

        # Score regression signal: baseline eval_score should not drop without review
        if isinstance(base_eval, (int, float)) and isinstance(cur_eval, (int, float)):
            if float(cur_eval) + 1e-9 < float(base_eval):
                warnings.append(
                    f"Judge prompt {key!r} eval_score in code ({cur_eval}) is below baseline ({base_eval}). "
                    "Confirm DSPy / eval before deploy."
                )

    return warnings


def log_judge_prompt_drift_warnings() -> None:
    """Emit structlog warnings for each drift finding."""
    for msg in check_judge_prompt_drift():
        log.warning("judge_prompt_drift", message=msg)
