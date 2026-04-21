# Architecture Decisions

## Why LangGraph over CrewAI
Durable execution via checkpointing. HITL capability. Stateful graph.
CrewAI doesn't checkpoint — mid-run failure loses all progress.

## Why Presidio over regex for PII
Handles edge cases regex misses. SSNs with/without dashes, partial
emails in prose, financial identifiers in context.

## Why separate generator and judge agents
Neither can rationalize its own mistakes. Generator hallucinates,
judge catches it. Same model evaluating its own output defeats the purpose.

## Why hashlib over certutil for SHA256
certutil hangs in subprocess calls on Windows. hashlib is pure Python,
instant, cross-platform, no dependencies.