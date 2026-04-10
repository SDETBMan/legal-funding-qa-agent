from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Annotated, TypeAlias

from pydantic import BeforeValidator

def validate_cents(value: object) -> int:
    """
    INV-11: Normalize values to integer cents; reject floats and fractional-cent Decimals.

    Accepts ``int``, strings that are whole cent amounts or decimal dollar/currency strings
    with at most two fractional digits (parsed via ``Decimal``, never ``float``), and
    ``Decimal`` values that are already exact whole cents.
    """
    if value is None:
        msg = "money value must not be None"
        raise TypeError(msg)
    if isinstance(value, bool):
        msg = "bool is not valid for money fields"
        raise TypeError(msg)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        msg = "float money is forbidden per INV-11"
        raise TypeError(msg)
    if isinstance(value, Decimal):
        return _decimal_must_be_whole_cents(value)
    if isinstance(value, str):
        return _parse_string_to_cents(value.strip())
    msg = f"unsupported money type: {type(value).__name__}"
    raise TypeError(msg)

def _decimal_must_be_whole_cents(d: Decimal) -> int:
    if not d.is_finite():
        msg = "money must be finite"
        raise ValueError(msg)
    integral = d.to_integral_value(rounding=ROUND_HALF_UP)
    if integral != d:
        msg = "Decimal must represent whole cents with no fractional cent remainder"
        raise ValueError(msg)
    return int(integral)

def _parse_string_to_cents(s: str) -> int:
    if not s:
        msg = "empty string is not valid money"
        raise ValueError(msg)

    neg = False
    if s[0] == "-":
        neg = True
        s = s[1:].strip()
        if not s:
            msg = "invalid money string"
            raise ValueError(msg)

    # Whole cent amount, no decimal point (e.g. API string "12345")
    if re.fullmatch(r"\d+", s):
        v = int(s)
        return -v if neg else v

    # Optional decimal fraction, 1–2 digits (treated as dollars/cents fraction)
    if re.fullmatch(r"\d+\.\d{1,2}", s):
        try:
            d = Decimal(s)
        except InvalidOperation as e:
            msg = "invalid decimal money string"
            raise ValueError(msg) from e
        cents = int((d * 100).to_integral_value(rounding=ROUND_HALF_UP))
        return -cents if neg else cents

    msg = f"unrecognized money string format: {s!r}"
    raise ValueError(msg)

def parse_ui_currency_to_cents(text: str) -> int:
    """
    INV-13: Parse common US-style currency text to integer cents without using ``float``.

    Accepts optional leading ``$``, thousands separators ``,``, optional surrounding
    parentheses for negative values, and a single ``-`` prefix.
    """
    cleaned = text.strip()
    if not cleaned:
        msg = "empty currency text"
        raise ValueError(msg)

    neg = False
    if cleaned.startswith("(") and cleaned.endswith(")"):
        neg = True
        cleaned = cleaned[1:-1].strip()
    cleaned = cleaned.replace(",", "")
    if cleaned.startswith("$"):
        cleaned = cleaned[1:].strip()
    if cleaned.startswith("-"):
        neg = not neg
        cleaned = cleaned[1:].strip()

    if not cleaned:
        msg = "no numeric currency content"
        raise ValueError(msg)

    if not re.fullmatch(r"\d+(\.\d{1,2})?", cleaned):
        msg = f"unsupported currency format: {text!r}"
        raise ValueError(msg)

    try:
        d = Decimal(cleaned)
    except InvalidOperation as e:
        msg = "invalid currency amount"
        raise ValueError(msg) from e

    cents = int((d * 100).to_integral_value(rounding=ROUND_HALF_UP))
    return -cents if neg else cents

def _coerce_cents(value: object) -> int:
    return validate_cents(value)

Cents: TypeAlias = Annotated[int, BeforeValidator(_coerce_cents)]
"""INV-11: Type alias for validated integer-cent money fields (rejects ``float`` inputs)."""
