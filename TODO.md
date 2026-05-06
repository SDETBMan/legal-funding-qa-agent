# TODO

## Next session (post-hire at Libra)
- Wire ToolSelectorMiddleware into main agent call
- Wire SummarizationMiddleware into main agent call
- Add jurisdiction rate cap validation to invariant library
- Build page objects for Libra funding application flow
- Set up Azure Pipelines CI config
- Add prompt injection defense
- Add scope reminder injection at every node rather than just startup

## Post-hire — LangSmith Deployment consideration
When Libra's agentic workflow moves toward production scale:
- Evaluate LangSmith Deployment as the runtime layer underneath the harness
- Implement time travel debugging for complex chain traversal failures
- Wire online evals for production trace monitoring
- Implement cron-based legal corpus maintenance agent
- Evaluate sandbox auth proxy pattern for any agent with API credentials

## Invariant library governance (ongoing)
- Quarterly review of all invariants for accuracy and relevance
- Each invariant must have: narrow description, explicit scope boundaries, 
  clear pass/fail criteria, and a named owner
- New invariants require: stable workflow, high business value, 
  non-overlapping scope with existing invariants
- Retired invariants get archived not deleted — audit trail matters

## Post-hire — Multi-tenancy architecture (when agent goes client-facing)
- Data isolation: Agent Server custom auth middleware scopes 
  every request to authenticated user's threads and memories
- Agent Auth: OAuth flow for attorney/provider credential delegation
  (Filevine, CASEpeer, vCase integrations)
- RBAC: Role-based access for team — who can deploy, view traces, 
  change auth policies
- Reference: https://docs.langchain.com/oss/python/deepagents/
  going-to-production#multi-tenancy

## HITL persistence for production
Current HITL gates work locally but don't survive process restarts.
LangSmith Deployment persists interrupt() state across indefinite gaps.
Required before any HITL gate goes client-facing or runs in production CI.

## Upgrade to LangGraph 1.2 post-hire
- Migrate message channels to DeltaChannel for long-running 
  chain traversal tests — cuts checkpoint overhead significantly
- Use snapshot_frequency=5 as starting point

## CLAUDE.md maintenance (monthly)
- Review every rule in CLAUDE.md — does it still reflect how the 
  codebase actually works?
- Delete rules that no longer apply
- Merge rules that overlap
- Add rules that emerged from the last month's corrections
- Run /security-review in Cursor after any significant changes

## Claude Code hooks (post-hire)
- pre-commit hook: run --demo-guardrails smoke test
- post-edit hook: security review on modified guardrail files
- pre-push hook: verify judge baseline is committed