# TODO

## Immediate — Next Session
- Wire ToolSelectorMiddleware into main agent call
- Wire SummarizationMiddleware into main agent call
- Add prompt injection defense layer
- Add scope reminder injection at every LangGraph node (not just startup)

## Near-Term — Framework Hardening
- Add jurisdiction rate cap validation to invariant library
- Build page objects for core legal funding application flow
- Set up Azure Pipelines CI config
- Upgrade to LangGraph 1.2 when stable — DeltaChannel, per-node
  timeouts, error handlers, graceful shutdown
- Implement HITL persistence — LangSmith Deployment persists
  interrupt() state across process restarts and indefinite gaps

## Production Scale — When Deploying Client-Facing
- Evaluate LangSmith Deployment as runtime layer beneath the harness
- Implement time travel debugging for complex chain traversal failures
- Wire online evals for production trace monitoring
- Implement cron-based legal corpus maintenance agent
  (monitors jurisdiction rule changes, routes to human reviewer)
- Evaluate sandbox auth proxy — credentials injected at infra layer,
  never held in agent context
- Data isolation: Agent Server custom auth middleware scopes every
  request to authenticated user's threads
- Agent Auth: OAuth flow for credential delegation to third-party
  integrations
- RBAC: role-based access for team — deploy, view traces, change
  auth policies
- Reference: https://docs.langchain.com/oss/python/deepagents/
  going-to-production#multi-tenancy

## Ongoing — Invariant Library Governance (quarterly)
- Review every invariant for accuracy and relevance
- Each invariant must have: narrow description, explicit scope
  boundaries, clear pass/fail criteria, named owner
- New invariants require: stable workflow, high business value,
  non-overlapping scope with existing invariants
- Retired invariants get archived not deleted — audit trail matters

## Ongoing — CLAUDE.md Maintenance (monthly)
- Review every rule — does it still reflect how the codebase works?
- Delete stale rules immediately
- Merge overlapping rules
- Add rules that emerged from corrections this month
- Run /security-review in Cursor after any significant changes

## Ongoing — Claude Code Hooks
- pre-commit: run --demo-guardrails smoke test
- post-edit: security review on modified guardrail files
- pre-push: verify judge baseline is committed