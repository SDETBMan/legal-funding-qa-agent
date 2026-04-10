from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, model_validator

from agent.models.money import Cents

class LienPriority(str, Enum):
    """INV-07: Medicare/Medicaid super-priority relative to medical liens."""

    SUPER_PRIORITY = "SUPER_PRIORITY"
    MEDICAL = "MEDICAL"
    OTHER = "OTHER"

class MedicalLien(BaseModel):
    """INV-07, INV-08: Ordering by priority_rank; balance must not exceed original bill."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    lien_id: str
    case_id: str
    priority_rank: int
    balance_cents: Cents = Field(ge=0)
    original_billed_amount_cents: Cents = Field(ge=0)
    priority_class: LienPriority

    @model_validator(mode="after")
    def balance_within_original_bill(self) -> MedicalLien:
        if self.balance_cents > self.original_billed_amount_cents:
            msg = (
                f"INV-08: balance_cents ({self.balance_cents}) cannot exceed "
                f"original_billed_amount_cents ({self.original_billed_amount_cents})"
            )
            raise ValueError(msg)
        return self

class LienRelease(BaseModel):
    """INV-07: Release amount within settlement waterfall."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    lien_id: str
    release_cents: Cents = Field(ge=0)
