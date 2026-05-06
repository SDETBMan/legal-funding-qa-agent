# Contributing

Offshore and onshore contributor guide.

This file is the canonical home for contributor step-by-step workflows and the reviewer checklist. (These were previously embedded in `CLAUDE.md`.)

---

## Before you write any code

Ask yourself:

- Which invariant does this attack target? Find it in `README.md` (invariants table) and `PLAN.md` (prose).
- If no existing invariant fits, update `PLAN.md` first with a one-line blast radius statement before adding code.
- Are you using a seed/staging dataset that won’t pollute other engineers’ runs? Attacks must clean up after themselves.

---

## Step-by-step: adding an API attack

1. Open `agent/adversary/attacks.py`
2. Copy the `attack_template` function from the bottom of the file
3. Rename it to `attack_<invariant_description>` (snake_case, no abbreviations)
4. Add the `INV-XX` cite in the docstring **as the first line** (mandatory)
5. Write the attack body following the “idempotent + deterministic + evidence only” pattern
6. Add cleanup in a `finally` block — cancel/void all created records
7. Register the new attack in the `ATTACKS` registry
8. Run against staging: `python -m agent.main --attack <your_function_name>`
9. Verify the `AttackResult` evidence in `artifacts/attacks.json` looks correct
10. Open a PR and include the staging output in the PR description

---

## Step-by-step: adding a UI invariant check

1. Add the invariant to the UI invariant list before writing code (new invariant PR first)
2. Open `agent/ui_explorer/browser_agent.py`
3. Add a new goal string to `BROWSER_GOALS` (one sentence, imperative mood)
4. The agent handles navigation — do not hardcode URLs or selectors
5. If the check requires specific state, set it up via API clients (not UI clicks) so setup is deterministic
6. Register in `agent/swarm/reconciliation.py` so it runs in the release gate

---

## Code review checklist

Reviewers must verify:

- [ ] Docstring cites an `INV-XX` on the first line
- [ ] No float types anywhere near a money value (integer cents only)
- [ ] Cleanup exists in `finally` (all created IDs cancelled/voided)
- [ ] Returns `AttackResult` (never raises, prints, or exits)
- [ ] No hardcoded base URL
- [ ] No hardcoded money amounts (derive from API responses / scenario setup)
- [ ] Deterministic given the same seed (or explicitly documented as non-deterministic with reason)
- [ ] Staging run output included in the PR description
- [ ] New attack registered in the `ATTACKS` registry
- [ ] All inputs pass through `create_guarded_agent_state()` before entering any LLM context
