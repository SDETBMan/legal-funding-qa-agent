from __future__ import annotations

import hashlib

from pydantic import BaseModel, ConfigDict


class PromptVersion(BaseModel):
    """INV-20: Versioned judge prompt with hash and eval score for regression control."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    hash: str
    content: str
    eval_score: float | None = None
    replaced_at: str | None = None


def hash_prompt(content: str) -> str:
    """INV-20: Compute stable SHA-256 hash for prompt versioning in reports."""
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


WATERFALL_JUDGE_PROMPT_v3 = PromptVersion(
    hash=hash_prompt(
        "You are an invariant judge for legal funding and settlement waterfall outputs.\n"
        "Given JSON evidence and an invariant rule ID, respond with exactly one verdict: "
        "HELD, BREACHED, or INDETERMINATE.\n"
        "Rules:\n"
        "- Base the verdict only on the evidence; do not invent money fields.\n"
        "- If any money field is a float or a string with >2dp, treat as INV-11 material.\n"
        "- Prefer INDETERMINATE when the API shape is ambiguous.\n"
        'Output JSON: {"verdict": "...", "reasoning": "..."}'
    ),
    content=(
        "You are an invariant judge for legal funding and settlement waterfall outputs.\n"
        "Given JSON evidence and an invariant rule ID, respond with exactly one verdict: "
        "HELD, BREACHED, or INDETERMINATE.\n"
        "Rules:\n"
        "- Base the verdict only on the evidence; do not invent money fields.\n"
        "- If any money field is a float or a string with >2dp, treat as INV-11 material.\n"
        "- Prefer INDETERMINATE when the API shape is ambiguous.\n"
        'Output JSON: {"verdict": "...", "reasoning": "..."}'
    ),
    eval_score=0.94,
)
