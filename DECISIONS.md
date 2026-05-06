# Architecture Decisions

## Why LangGraph over CrewAI
- Durable execution via checkpointing. HITL capability. Stateful graph.
- CrewAI doesn't checkpoint — mid-run failure loses all progress.

## Why Presidio over regex for PII
- Handles edge cases regex misses. SSNs with/without dashes, partial emails in prose, financial identifiers in context.

## Why separate generator and judge agents
- Neither can rationalize its own mistakes. Generator hallucinates, judge catches it.
- Same model evaluating its own output defeats the purpose.

## Why hashlib over certutil for SHA256
- certutil hangs in subprocess calls on Windows.
- hashlib is pure Python, instant, cross-platform, no dependencies.

## Why Playwright as browser-use instead of scripted selectors
- The UI changes; scripted selectors break silently and create flaky CI.
- Navigating by semantic intent degrades gracefully and surfaces flows no one scripted.
- Enables self-healing selector proposals that engineers can review.

## Why DSPy instead of hand-tuned prompts
- Prompts degrade silently when API response shapes change.
- DSPy turns the Judge into a measurable module with an eval score, so regressions are detectable before deploy.

## Why integer cents throughout
- Float contamination in any money field is a compliance/audit finding.
- Integer arithmetic is exact; no rounding ambiguity in payoff and waterfall math.

## Why idempotent attacks with cleanup
- Staging environments are shared; orphaned records corrupt subsequent runs.
- Cleanup is part of correctness, not hygiene.

## Why separate observer and judge roles
- Attacks collect raw evidence; the Judge reasons over evidence.
- Re-judging stored evidence is cheaper than re-hitting the API and keeps verdicts reproducible.

## Why a dedicated guardrails layer
- Realistic test payloads contain PII; raw inputs must not reach LLM context or logs.
- Rate limiting and scoped retry prevent runaway agents from burning budget and blocking CI.

## Claude Code CLI Shortcuts Reference
*Added 2026-04-28 — reference for daily framework development workflow*

Key commands for the legal funding agentic framework:

### Cost & Context
- /cost — token usage for session
- /compact [instructions] — compress conversation, control what's kept
- /clear — fresh context start

### Framework & Memory
- /init — initialize project with CLAUDE.md
- /memory — edit CLAUDE.md directly from Claude Code
- /skills — list all available skills
- /agents — manage sub-agent configurations
- /permissions — manage allow/ask/deny tool rules

### Debugging & Safety
- /diff — interactive diff viewer for uncommitted changes
- /security-review — analyze pending changes for vulnerabilities
- /rewind — roll back to earlier conversation point
- /branch [name] — explore alternative approach without losing main thread

