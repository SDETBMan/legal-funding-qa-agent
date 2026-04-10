from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, model_validator

from agent.models.money import Cents

class SettlementDisbursement(BaseModel):
    """
    INV-07, INV-09, INV-11: Full settlement allocation; buckets plus remainder must equal settlement.

    Bucket totals follow the canonical waterfall ordering in aggregate form.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    settlement_id: str
    settlement_amount_cents: Cents = Field(ge=0)
    medicare_medicaid_cents: Cents = Field(default=0, ge=0)
    medical_liens_cents: Cents = Field(default=0, ge=0)
    funding_payoff_cents: Cents = Field(default=0, ge=0)
    attorney_fees_cents: Cents = Field(default=0, ge=0)
    plaintiff_remainder_cents: Cents

    def recompute_allocated_total(self) -> int:
        """Sum of all waterfall buckets including plaintiff remainder."""
        return (
            self.medicare_medicaid_cents
            + self.medical_liens_cents
            + self.funding_payoff_cents
            + self.attorney_fees_cents
            + self.plaintiff_remainder_cents
        )

    @model_validator(mode="after")
    def allocations_match_settlement(self) -> SettlementDisbursement:
        allocated = self.recompute_allocated_total()
        if allocated != self.settlement_amount_cents:
            msg = (
                f"settlement_amount_cents ({self.settlement_amount_cents}) must equal "
                f"sum of allocations ({allocated})"
            )
            raise ValueError(msg)
        if self.plaintiff_remainder_cents < 0:
            msg = (
                f"INV-09: plaintiff_remainder_cents ({self.plaintiff_remainder_cents}) "
                "must be >= 0"
            )
            raise ValueError(msg)
        return self

class WaterfallLineItem(BaseModel):
    """Single slice of a settlement waterfall (ordered disbursement line)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    category: str
    amount_cents: Cents = Field(ge=0)
    order_index: int = 0

class WaterfallResult(BaseModel):
    """INV-07: Line items plus plaintiff remainder must reconcile to settlement total."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    settlement_id: str
    settlement_amount_cents: Cents = Field(ge=0)
    line_items: list[WaterfallLineItem]
    plaintiff_remainder_cents: Cents

    def recompute_line_items_sum(self) -> int:
        return sum(item.amount_cents for item in self.line_items)

    @model_validator(mode="after")
    def totals_reconcile(self) -> WaterfallResult:
        lines = self.recompute_line_items_sum()
        total = lines + self.plaintiff_remainder_cents
        if total != self.settlement_amount_cents:
            msg = (
                f"Waterfall mismatch: settlement_amount_cents={self.settlement_amount_cents}, "
                f"line_items_sum={lines}, plaintiff_remainder_cents="
                f"{self.plaintiff_remainder_cents}, combined={total}"
            )
            raise ValueError(msg)
        if self.plaintiff_remainder_cents < 0:
            msg = (
                f"INV-09: plaintiff_remainder_cents ({self.plaintiff_remainder_cents}) "
                "must be >= 0"
            )
            raise ValueError(msg)
        return self
