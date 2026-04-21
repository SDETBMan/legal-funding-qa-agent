"""
Versioned judge prompt templates (INV-20 / Drift Triangle).

Each template carries a SHA-256 of UTF-8 content and an optional ``eval_score`` from the
held-out judge eval set. Production deploys should only advance hashes in
``config/judge_prompt_baseline.json`` after a passing eval run.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Final

# Stable registry keys (match report.json ``prompt_versions`` and baseline JSON).
WATERFALL_JUDGE_KEY: Final[str] = "waterfall_judge"
UI_RECONCILIATION_JUDGE_KEY: Final[str] = "ui_reconciliation_judge"

JUDGE_PROMPT_KEYS: Final[tuple[str, ...]] = (
    WATERFALL_JUDGE_KEY,
    UI_RECONCILIATION_JUDGE_KEY,
)


def sha256_text(text: str) -> str:
    """SHA-256 hex digest of ``text`` encoded as UTF-8 (no BOM)."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class PromptVersion:
    """One judge prompt: body, stored SHA-256, and held-out eval score (INV-20)."""

    key: str
    content: str
    eval_score: float | None
    description: str = ""
    content_sha256: str = field(init=False)

    def __post_init__(self) -> None:
        digest = hashlib.sha256(self.content.encode("utf-8")).hexdigest()
        object.__setattr__(self, "content_sha256", digest)

    @property
    def sha256(self) -> str:
        """Alias for :attr:`content_sha256` (report / baseline compatibility)."""
        return self.content_sha256


# --- Templates (edit content only with a follow-on eval + baseline bump) ---

_WATERFALL_JUDGE_CONTENT = """You are an invariant judge for legal funding and settlement waterfall outputs.

Given JSON evidence and an invariant rule ID (e.g. INV-04, INV-07), respond with exactly one verdict:
HELD, BREACHED, or INDETERMINATE.

Rules:
- Base the verdict only on the evidence; do not invent money fields.
- If any money field is a float or a string with more than two decimal places, treat that as INV-11 material and explain in reasoning.
- Prefer INDETERMINATE when the API shape is ambiguous rather than guessing.

Output JSON: {"verdict": "...", "reasoning": "..."}
"""


_UI_RECONCILIATION_JUDGE_CONTENT = """You are a UI vs API reconciliation judge for funding and payoff displays.

Compare API integer cents (ground truth) to what the UI shows. Flag any cent mismatch as a potential INV-13 breach.

Output JSON: {"verdict": "...", "reasoning": "..."}
"""


WATERFALL_JUDGE_V1 = PromptVersion(
    key=WATERFALL_JUDGE_KEY,
    content=_WATERFALL_JUDGE_CONTENT,
    eval_score=0.94,
    description="Waterfall / invariant verdict judge (DSPy-optimizable module).",
)

UI_RECONCILIATION_JUDGE_V1 = PromptVersion(
    key=UI_RECONCILIATION_JUDGE_KEY,
    content=_UI_RECONCILIATION_JUDGE_CONTENT,
    eval_score=0.91,
    description="UI reconciliation vs API payoff judge.",
)

_PROMPTS: Final[tuple[PromptVersion, ...]] = (
    WATERFALL_JUDGE_V1,
    UI_RECONCILIATION_JUDGE_V1,
)


def get_prompt_registry() -> dict[str, PromptVersion]:
    """Map prompt key -> :class:`PromptVersion` (single source of truth)."""
    return {p.key: p for p in _PROMPTS}


def get_prompt_fingerprints() -> dict[str, dict[str, object]]:
    """Serializable fingerprints for reports and baseline files."""
    out: dict[str, dict[str, object]] = {}
    for p in _PROMPTS:
        out[p.key] = {
            "sha256": p.sha256,
            "eval_score": p.eval_score,
            "description": p.description,
        }
    return out


def export_baseline_dict() -> dict[str, object]:
    """Shape written to ``config/judge_prompt_baseline.json`` after an eval-approved promotion."""
    return {
        "schema_version": 1,
        "prompts": {
            p.key: {"sha256": p.sha256, "eval_score": p.eval_score}
            for p in _PROMPTS
        },
    }


def write_baseline_file(path: Path | None = None) -> Path:
    """
    Write last-known-good hashes (from :func:`export_baseline_dict`) using only stdlib.

    Uses ``hashlib.sha256(prompt.encode('utf-8')).hexdigest()`` via :class:`PromptVersion`.
    """
    root = Path(__file__).resolve().parent.parent
    out = path or root / "config" / "judge_prompt_baseline.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(export_baseline_dict(), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return out


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(description="Judge prompt baseline (hashlib SHA-256).")
    ap.add_argument(
        "--write-baseline",
        action="store_true",
        help="Write config/judge_prompt_baseline.json from current templates.",
    )
    args = ap.parse_args()
    if args.write_baseline:
        p = write_baseline_file()
        print(f"wrote {p}")
    else:
        print(json.dumps(export_baseline_dict(), indent=2, ensure_ascii=False))
