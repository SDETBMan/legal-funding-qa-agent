from __future__ import annotations

from pydantic import BaseModel, ConfigDict

class PromptVersion(BaseModel):
    """INV-20: Versioned judge prompt with hash and eval score for regression control."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    hash: str
    content: str
    eval_score: float | None = None
    replaced_at: str | None = None

def hash_prompt(content: str) -> str:
    """INV-20: Compute stable hash for prompt versioning in reports."""
    raise NotImplementedError

WATERFALL_JUDGE_PROMPT_v3 = PromptVersion(
    hash="sha256:placeholder",
    content="",
    eval_score=None,
    replaced_at=None,
)
