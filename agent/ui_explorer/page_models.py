from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict

class SoftPageModel(BaseModel):
    """
    Soft page object fields maintained by the LLM (§3).

    INV-13–INV-16: Semantic locators and labels for payoff, status, waterfall, and ack UI.
    """

    model_config = ConfigDict(extra="allow", frozen=False)

    page_name: str
    selectors: dict[str, str]

    def merge_from_llm(self, patch: dict[str, Any]) -> None:
        """INV-14: Apply LLM-proposed selector or label updates without silent auto-merge policy."""
        raise NotImplementedError
