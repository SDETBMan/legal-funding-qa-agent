"""
Tool selection middleware (Drift Triangle guardrail).

Goal: before each *main* model call, shrink the available tool registry to the most
relevant tools to reduce tool-call loops and reduce attack surface.

Design constraints:
- Always include the search tool (domain requirement).
- Prefer a fast/cheap model for selection (e.g. Claude Haiku).
- Fail open: if selection fails, return the original tool registry.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Protocol

import structlog

log = structlog.get_logger(__name__)


class ToolSelectorLLM(Protocol):
    """Minimal interface: supply text in, get text out."""

    async def complete(self, *, prompt: str, model: str) -> str: ...


@dataclass(frozen=True)
class ToolSpec:
    """A tool entry the selector can reason about."""

    name: str
    description: str
    is_search: bool = False


@dataclass
class ToolSelectorMiddleware:
    """
    Filters a tool registry down to the top-N tools for a given goal.

    This middleware does not execute tools; it only selects which tools the main model
    is allowed to see.
    """

    llm: ToolSelectorLLM | None = None
    fast_model: str = "claude-haiku"
    max_tools: int = 3
    always_include_tool_names: tuple[str, ...] = ("search",)

    async def select_tools(
        self,
        *,
        goal: str,
        tools: list[ToolSpec],
        trace_context: dict[str, Any] | None = None,
    ) -> list[ToolSpec]:
        """
        Return a filtered tool list.

        - Always includes any tool with ``is_search=True`` and any in ``always_include_tool_names``.
        - If an LLM is configured, uses it to choose the rest (fast model).
        - If no LLM or parsing fails, falls back to a keyword-scoring heuristic.
        """
        trace_context = trace_context or {}
        if not tools:
            return tools

        must_keep = self._must_keep(tools)
        remaining = [t for t in tools if t.name not in {k.name for k in must_keep}]

        budget = max(0, self.max_tools - len(must_keep))
        if budget <= 0:
            return must_keep[: self.max_tools]

        try:
            picked: list[ToolSpec]
            if self.llm is None:
                picked = self._heuristic_pick(goal=goal, tools=remaining, k=budget)
            else:
                picked_names = await self._llm_pick_names(goal=goal, tools=remaining, k=budget)
                picked = [t for t in remaining if t.name in set(picked_names)]
                # If LLM returns fewer than needed, fill deterministically.
                if len(picked) < budget:
                    fill = self._heuristic_pick(goal=goal, tools=[t for t in remaining if t not in picked], k=budget - len(picked))
                    picked.extend(fill)

            out = (must_keep + picked)[: self.max_tools]
            log.info(
                "tool_selector_filtered",
                goal=goal[:200],
                selected=[t.name for t in out],
                total=len(tools),
                trace=trace_context,
            )
            return out
        except Exception as exc:
            log.warning(
                "tool_selector_failed",
                error=str(exc),
                goal=goal[:200],
                total=len(tools),
                trace=trace_context,
            )
            return tools

    def _must_keep(self, tools: list[ToolSpec]) -> list[ToolSpec]:
        always = set(self.always_include_tool_names)
        keep_map: dict[str, ToolSpec] = {}
        for t in tools:
            if t.is_search or t.name in always:
                keep_map[t.name] = t

        # Prefer search first if present.
        keep: list[ToolSpec] = []
        for t in tools:
            if t.is_search and t.name in keep_map:
                keep.append(keep_map.pop(t.name))
        # Then preserve original registry order for the rest.
        for t in tools:
            if t.name in keep_map:
                keep.append(keep_map.pop(t.name))
        return keep

    async def _llm_pick_names(self, *, goal: str, tools: list[ToolSpec], k: int) -> list[str]:
        assert self.llm is not None
        prompt = self._build_prompt(goal=goal, tools=tools, k=k)
        raw = await self.llm.complete(prompt=prompt, model=self.fast_model)
        names = self._parse_llm_output(raw)
        if not names:
            return []
        # preserve order from LLM but drop unknowns
        allowed = {t.name for t in tools}
        return [n for n in names if n in allowed][:k]

    def _build_prompt(self, *, goal: str, tools: list[ToolSpec], k: int) -> str:
        tool_rows = [{"name": t.name, "description": t.description} for t in tools]
        return (
            "Select the most relevant tools for the goal.\n"
            f"Goal: {goal}\n\n"
            f"Return JSON ONLY, shape: {{\"tools\": [<tool_name>, ...]}} with at most {k} names.\n"
            "Do not include any names not in the list.\n\n"
            "Tools:\n"
            f"{json.dumps(tool_rows, ensure_ascii=False)}\n"
        )

    def _parse_llm_output(self, raw: str) -> list[str]:
        try:
            obj = json.loads(raw)
        except json.JSONDecodeError:
            # Some models wrap JSON with text; attempt best-effort extraction.
            start = raw.find("{")
            end = raw.rfind("}")
            if start == -1 or end == -1 or end <= start:
                return []
            try:
                obj = json.loads(raw[start : end + 1])
            except Exception:
                return []

        tools = obj.get("tools")
        if not isinstance(tools, list):
            return []
        out: list[str] = []
        for item in tools:
            if isinstance(item, str) and item.strip():
                out.append(item.strip())
        return out

    def _heuristic_pick(self, *, goal: str, tools: list[ToolSpec], k: int) -> list[ToolSpec]:
        goal_l = goal.lower()
        scored: list[tuple[int, ToolSpec]] = []
        for t in tools:
            text = (t.name + " " + t.description).lower()
            score = 0
            for token in set(goal_l.split()):
                if token and token in text:
                    score += 1
            scored.append((score, t))
        scored.sort(key=lambda x: (-x[0], x[1].name))
        return [t for _, t in scored[:k]]

