"""
Conversation summarization middleware.

Triggers when the conversation history approaches the context window limit, summarizes
older messages, and keeps the last N messages verbatim.

Design constraints:
- Use a fast/cheap model for summarization (e.g. Claude Haiku).
- Fail open: if summarization fails, return messages unchanged.
- Keep the last 20 messages verbatim (operator debugging + recency).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Protocol

import structlog

log = structlog.get_logger(__name__)


class SummarizerLLM(Protocol):
    async def complete(self, *, prompt: str, model: str) -> str: ...


Message = dict[str, str]  # expected keys: role, content


@dataclass
class SummarizationMiddleware:
    llm: SummarizerLLM | None = None
    fast_model: str = "claude-haiku"
    context_window_tokens: int = 200_000
    trigger_ratio: float = 0.80
    keep_last_n: int = 20
    summary_role: str = "system"
    summary_prefix: str = "Conversation summary (auto, older messages):\n"

    def should_summarize(self, messages: list[Message]) -> bool:
        est = self.estimate_tokens(messages)
        return est >= int(self.context_window_tokens * self.trigger_ratio)

    def estimate_tokens(self, messages: list[Message]) -> int:
        """
        Very rough token estimate without external deps.

        Heuristic: 1 token ~= 4 chars (English-ish) plus small per-message overhead.
        """
        chars = 0
        for m in messages:
            chars += len(m.get("role", "")) + len(m.get("content", ""))
        overhead = 8 * len(messages)
        return (chars // 4) + overhead

    async def maybe_summarize(
        self,
        *,
        messages: list[Message],
        trace_context: dict[str, Any] | None = None,
    ) -> list[Message]:
        trace_context = trace_context or {}
        if not messages or self.keep_last_n <= 0:
            return messages

        if not self.should_summarize(messages):
            return messages

        if len(messages) <= self.keep_last_n:
            return messages

        older = messages[: -self.keep_last_n]
        recent = messages[-self.keep_last_n :]

        try:
            summary_text = await self._summarize_older(older)
            summary_msg: Message = {
                "role": self.summary_role,
                "content": f"{self.summary_prefix}{summary_text}".strip(),
            }
            out = [summary_msg, *recent]
            log.info(
                "history_summarized",
                before=len(messages),
                after=len(out),
                est_tokens_before=self.estimate_tokens(messages),
                est_tokens_after=self.estimate_tokens(out),
                trace=trace_context,
            )
            return out
        except Exception as exc:
            log.warning(
                "history_summarization_failed",
                error=str(exc),
                trace=trace_context,
            )
            return messages

    async def _summarize_older(self, older: list[Message]) -> str:
        prompt = self._build_prompt(older)
        if self.llm is None:
            return self._heuristic_summary(older)
        raw = await self.llm.complete(prompt=prompt, model=self.fast_model)
        text = raw.strip()
        if not text:
            return self._heuristic_summary(older)
        return text

    def _build_prompt(self, older: list[Message]) -> str:
        """
        Summarizer prompt: ask for a compact, structured summary suitable as a system message.
        """
        # Keep prompt deterministic; only include roles+content.
        payload = [{"role": m.get("role", ""), "content": m.get("content", "")} for m in older]
        return (
            "Summarize the older conversation messages for continuation.\n"
            "Requirements:\n"
            "- Preserve decisions, constraints, invariants, and unresolved tasks.\n"
            "- Do NOT include secrets or raw PII.\n"
            "- Be concise.\n"
            "- Output plain text (no JSON).\n\n"
            f"Older messages JSON:\n{json.dumps(payload, ensure_ascii=False)}\n"
        )

    def _heuristic_summary(self, older: list[Message]) -> str:
        """
        Fail-open fallback when no LLM is configured: keep only a compact outline.
        """
        lines: list[str] = []
        max_lines = 40
        for m in older[-max_lines:]:
            role = (m.get("role") or "").strip()[:12]
            content = (m.get("content") or "").strip().replace("\n", " ")
            if len(content) > 140:
                content = content[:137] + "..."
            if role and content:
                lines.append(f"- {role}: {content}")
        if not lines:
            return "(no content)"
        return "\n".join(lines)

