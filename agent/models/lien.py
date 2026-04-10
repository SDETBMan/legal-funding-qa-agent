from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, ValidationInfo, field_validator, model_validator

from agent.models.money import validate_cents

class LienType(str, Enum):
    """Lien channel for waterfall ordering (INV-07)."""

    MEDICARE = "MEDICARE"
    MEDICAID = "MEDICAID"
    MEDICAL = "MEDICAL"
    ATTORNEY = "ATTORNEY"

class LienPriority(BaseModel):
    """Lien position and balance for a case (INV-08)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    lien_id: str
    case_id: str
    lien_type: LienType
    priority_rank: int
    balance_cents: int
    original_billed_cents: int
    lienholder_name: str

    @field_validator("balance_cents", "original_billed_cents", mode="before")
    @classmethod
    def _cents_fields(cls, v: Any, info: ValidationInfo) -> int:
        return validate_cents(v, info.field_name or "cents")

    @model_validator(mode="after")
    def balance_within_original_bill(self) -> LienPriority:
        if self.balance_cents > self.original_billed_cents:
            delta = self.balance_cents - self.original_billed_cents
            msg = (
                f"INV-08: balance_cents ({self.balance_cents}) cannot exceed "
                f"original_billed_cents ({self.original_billed_cents}); delta={delta}"
            )
            raise ValueError(msg)
        return self
