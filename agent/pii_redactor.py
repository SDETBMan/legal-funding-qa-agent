"""PII redaction guard — strips sensitive data before it enters agent context."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import structlog
from presidio_analyzer import AnalyzerEngine
from presidio_anonymizer import AnonymizerEngine
from presidio_anonymizer.entities import OperatorConfig

log = structlog.get_logger(__name__)


@dataclass
class RedactionResult:
    """Sanitized text plus audit metadata (no raw spans or values)."""

    original_length: int
    sanitized_text: str
    entities_found: list[str]
    was_modified: bool


class PIIRedactor:
    """
    PII redactor for legal/financial payloads (SSN, contact, financial identifiers).

    Use before any string or nested dict is passed to an LLM or logged as free text.
    """

    ENTITY_TYPES = [
        "PERSON",
        "EMAIL_ADDRESS",
        "PHONE_NUMBER",
        "US_SSN",
        "CREDIT_CARD",
        "US_BANK_NUMBER",
        "MEDICAL_LICENSE",
        "DATE_TIME",
        "US_DRIVER_LICENSE",
        "IP_ADDRESS",
    ]

    def __init__(self) -> None:
        self.analyzer = AnalyzerEngine()
        self.anonymizer = AnonymizerEngine()
        self._operators = {
            "US_SSN": OperatorConfig(
                "mask", {"masking_char": "*", "chars_to_mask": 9, "from_end": False}
            ),
            "CREDIT_CARD": OperatorConfig(
                "mask", {"masking_char": "*", "chars_to_mask": 12, "from_end": False}
            ),
            "PERSON": OperatorConfig("replace", {"new_value": "[PLAINTIFF/ATTORNEY]"}),
            "EMAIL_ADDRESS": OperatorConfig("replace", {"new_value": "[REDACTED_EMAIL]"}),
            "PHONE_NUMBER": OperatorConfig("replace", {"new_value": "[REDACTED_PHONE]"}),
            "DEFAULT": OperatorConfig("replace", {"new_value": "[REDACTED]"}),
        }

    def redact(self, text: str, context: str = "test_payload") -> RedactionResult:
        """Analyze and redact PII from a single string."""
        if not text or not text.strip():
            return RedactionResult(
                original_length=len(text),
                sanitized_text=text,
                entities_found=[],
                was_modified=False,
            )

        try:
            results = self.analyzer.analyze(
                text=text,
                entities=self.ENTITY_TYPES,
                language="en",
            )

            if not results:
                return RedactionResult(
                    original_length=len(text),
                    sanitized_text=text,
                    entities_found=[],
                    was_modified=False,
                )

            entity_types = [r.entity_type for r in results]
            log.warning(
                "pii_detected",
                context=context,
                entity_types=entity_types,
                message="redacting before LLM context",
            )

            anonymized = self.anonymizer.anonymize(
                text=text,
                analyzer_results=results,
                operators=self._operators,
            )

            return RedactionResult(
                original_length=len(text),
                sanitized_text=anonymized.text,
                entities_found=entity_types,
                was_modified=True,
            )

        except Exception as exc:
            log.error(
                "pii_redaction_failed",
                context=context,
                error=str(exc),
                message="blocking input",
            )
            return RedactionResult(
                original_length=len(text),
                sanitized_text="[INPUT BLOCKED — PII REDACTION ERROR]",
                entities_found=["REDACTION_ERROR"],
                was_modified=True,
            )

    def redact_dict(self, data: dict[str, Any]) -> dict[str, Any]:
        """Recursively redact all string values in a dict (e.g. API payloads)."""
        sanitized: dict[str, Any] = {}
        for key, value in data.items():
            if isinstance(value, str):
                sanitized[key] = self.redact(value, context=key).sanitized_text
            elif isinstance(value, dict):
                sanitized[key] = self.redact_dict(value)
            elif isinstance(value, list):
                sanitized[key] = [self._redact_nested(item, key) for item in value]
            else:
                sanitized[key] = value
        return sanitized

    def _redact_nested(self, item: Any, context_key: str) -> Any:
        if isinstance(item, str):
            return self.redact(item, context=context_key).sanitized_text
        if isinstance(item, dict):
            return self.redact_dict(item)
        if isinstance(item, list):
            return [self._redact_nested(x, context_key) for x in item]
        return item


_default_redactor: PIIRedactor | None = None


def get_default_pii_redactor() -> PIIRedactor:
    """Lazy singleton — Presidio engines are heavy; avoid import-time init."""
    global _default_redactor
    if _default_redactor is None:
        _default_redactor = PIIRedactor()
    return _default_redactor
