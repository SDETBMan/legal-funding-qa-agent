from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, ValidationInfo, field_validator, model_validator

from agent.models.lien import LienType
from agent.models.money import validate_cents

class WaterfallLine(BaseModel):
    """One lien slice in an ordered settlement waterfall."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    lien_id: str
    lienholder_name: str
    priority_rank: int
    amount_paid_cents: int
    lien_type: LienType

    @field_validator("amount_paid_cents", mode="before")
    @classmethod
    def _amount_paid_cents(cls, v: Any, info: ValidationInfo) -> int:
        return validate_cents(v, info.field_name or "amount_paid_cents")

class SettlementDisbursement(BaseModel):
    """
    INV-07, INV-09: Full settlement waterfall lines plus plaintiff remainder.

    ``waterfall`` must be sorted by ``priority_rank`` ascending.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    case_id: str
    settlement_cents: int
    waterfall: list[WaterfallLine]
    plaintiff_remainder_cents: int

    @field_validator("settlement_cents", "plaintiff_remainder_cents", mode="before")
    @classmethod
    def _top_level_cents(cls, v: Any, info: ValidationInfo) -> int:
        return validate_cents(v, info.field_name or "cents")

    @model_validator(mode="after")
    def plaintiff_remainder_non_negative(self) -> SettlementDisbursement:
        if self.plaintiff_remainder_cents < 0:
            msg = (
                f"INV-09: plaintiff_remainder_cents ({self.plaintiff_remainder_cents}) "
                "must be >= 0"
            )
            raise ValueError(msg)
        return self

    @model_validator(mode="after")
    def waterfall_sorted_by_priority(self) -> SettlementDisbursement:
        ranks = [line.priority_rank for line in self.waterfall]
        if ranks != sorted(ranks):
            msg = "waterfall must be sorted by priority_rank ascending"
            raise ValueError(msg)
        return self

    @model_validator(mode="after")
    def settlement_reconciles(self) -> SettlementDisbursement:
        paid = sum(line.amount_paid_cents for line in self.waterfall)
        total = paid + self.plaintiff_remainder_cents
        if total != self.settlement_cents:
            msg = (
                f"settlement_cents ({self.settlement_cents}) must equal "
                f"sum(waterfall amount_paid_cents) + plaintiff_remainder_cents "
                f"({paid} + {self.plaintiff_remainder_cents} = {total})"
            )
            raise ValueError(msg)
        return self
