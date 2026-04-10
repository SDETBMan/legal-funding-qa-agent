# Legal Funding QA Agent

One-sentence description: "An autonomous QA agent that attacks financial and legal invariants in a pre-settlement funding API, produces an auditable JSON report, and feeds a go/no-go signal directly into the CI/CD release pipeline."

---

## Why this exists

Traditional test suites assert what you already expect; this agent attacks what you did not model. In legal-tech fintech, a miscalculated payoff is a regulatory finding, a wrong lien priority is legal liability, and a float in a money field is an audit event. The agent is built to surface those failure modes before production does, with evidence suitable for a release gate, not just a failing assertion.

---

## Architecture

```
Explorer → Adversarial Agent → Judge Agent → Report + Release Gate
                ↑
         Synthetic Data
```

| Component | Role |
|---|---|
| Explorer | Maps API and UI surfaces and seeds scenarios the attacks can reach. |
| Adversarial Agent | Drives edge-case requests and collects raw responses as evidence. |
| Judge Agent | Interprets evidence against invariants and explains verdicts in natural language. |
| Report + Release Gate | Emits `artifacts/report.json` and a BLOCK / WARN / PASS decision for CI/CD. |
| Synthetic Data | Generates valid case, lien, and funding graphs so attacks do not depend on hand-written fixtures alone. |

---

## Invariants under attack

| ID | Rule | Blast radius |
|---|---|---|
| INV-01 | No duplicate active funding on the same case | Regulatory / duplicate disbursement |
| INV-02 | Funding cannot be approved if case status is settled, dismissed, or closed | Unrecoverable non-recourse loss |
| INV-03 | Attorney acknowledgment must exist and be dated before funds disburse | Legal liability / clawback |
| INV-04 | Payoff = principal_cents + accrued_interest_cents + fees_cents; interest accrues from disbursement_date, not application_date | Direct $ — overcharge or undercharge |
| INV-05 | Approved funding <= case_max_exposure at time of approval | Credit / loss risk |
| INV-06 | Jurisdiction rate cap enforced — interest rate must not exceed applicable state usury limit | Regulatory / void contract |
| INV-07 | Settlement waterfall order: Medicare/Medicaid → medical liens by priority_rank → funding payoff → attorney fees → plaintiff remainder | Legal liability to lienholders |
| INV-08 | Medical lien balance cannot exceed original_billed_amount | Overbilling / provider dispute |
| INV-09 | Plaintiff remainder after waterfall must be >= 0; disbursement must not proceed if obligations exceed settlement | Negative remainder = company debt |
| INV-10 | Cancelled or expired applications release reserved case capacity immediately | Inventory leak / over-exposure |
| INV-11 | All money fields are integer cents — never floats, never strings with >2dp | Audit / regulatory finding |
| INV-12 | Interest uses exact calendar day count from disbursement_date to payoff_date | Off-by-days = material $ error at portfolio scale |

---

## Quick start

```bash
git clone <repository-url>
cd MoveDocs
cp .env.example .env
# add keys (e.g. MOVEDOCS_API_BASE=http://localhost:8000 for the mock API)
docker-compose up -d
python verify_bugs.py
python -m agent.main
```

Expected terminal output of step 5:

```
INV-01 | duplicate_funding            | HELD     | "Duplicate correctly rejected."
INV-11 | float_payoff                 | BREACHED | "total_cents returned as float: 523260.0"
INV-04 | interest_from_application_date| BREACHED | "Plaintiff overcharged by 9 days = 431 cents ($4.31)."
INV-07 | waterfall_priority           | BREACHED | "Medicare paid second despite super-priority."

Release gate: BLOCK
```

---

## Demo findings

| Invariant | Finding | Severity | $ Impact |
|---|---|---|---|
| INV-11 | payoff_amount returned as float (523260.0) | CRITICAL | Audit / regulatory |
| INV-04 | Interest accrues from application_date not disbursement_date | HIGH | $4.31 per contract |
| INV-07 | Medicare lien paid after MEDICAL lien despite super-priority | HIGH | Legal liability |

---

## Stack

| Core | Agents & ops |
|---|---|
| Python 3.11, httpx, pydantic v2, hypothesis | LangGraph, langchain-anthropic, structlog, AgentOps |

---

## Design decisions

- Why LangGraph instead of pytest? The agent needs to reason, not just assert — when a payoff is off, the question is why (day count, rate, fee), and a Judge LLM explains that where pytest would only show a failure.
- Why Playwright as browser-use instead of scripted selectors? The UI changes, scripted selectors break silently, and navigating by semantic intent degrades gracefully and surfaces flows no one scripted.
- Why DSPy instead of hand-tuned prompts? Prompts degrade silently when response shapes change, and DSPy turns the Judge into a module with a measurable eval score so regression is detectable in a regulated financial domain.
- Why integer cents throughout? Floating-point in payoff math is a compliance finding, not a rounding error, and integer arithmetic is exact — there is no acceptable alternative in legal funding.

---

## CLAUDE.md

Every AI agent working in this repo is bound by [CLAUDE.md](CLAUDE.md) — a contract that defines invariants, forbidden patterns, contributor standards, and escalation rules.
