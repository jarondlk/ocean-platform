# Planning Hub initial instruction

Open a separate local chat in the existing provenance-eco-rag project, titled
**OCEAN v1.0.0 — Planning Hub**. Use the current project checkout, not a new
worktree. This hub is coordination/planning only.

Copy the following instruction:

> This is the OCEAN v1.0.0 Planning Hub. The user has authorized creation of the
> planning space only and has explicitly deferred application implementation.
> Read docs/plans/ocean-v1/README.md, MASTER_PLAN.md, DECISIONS.md, COMPONENTS.md,
> STATUS.md, ACCEPTANCE_MAP.md and the setup receipt. Inspect the prompt index
> and handoff convention. Confirm that the 27 component specifications exist,
> summarize their dependency order and identify the first eligible component.
> Do not start any implementation component, edit files, execute
> application tests, create other chats, invoke subagents, make paid provider
> calls, provision cloud resources, publish data or deploy. Do not mark an
> implementation component started or complete. Treat this initial turn as
> read-only verification and report readiness or specific missing documentation.
> For later user requests, use the corresponding component prompt, prerequisite
> handoffs and actual checkout. Never assume this hub's conversation is the
> only source of state. Wait for the user to explicitly select a component and
> whether to plan, implement or resume it.

Hub creation and ID are recorded in SETUP_RECEIPT.md once creation succeeds.
The hub's read-only confirmation is not application acceptance.

The dispatched instruction also clarifies that all plan document names are
relative to `docs/plans/ocean-v1/`, includes `components.json`, and allows the
setup receipt to briefly show hub creation/confirmation pending while the
originating chat records the new chat ID. This is coordination state only.
