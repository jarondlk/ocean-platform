# Local UI and human-centered UX brief

Updated: 2026-10-13 JST. P00 design brief; local implementation is in progress.
The goal is a working local experience that the user can inspect and reshape
before backend construction. The saved concept image is a reference, not a
fixed layout or a requirement to reproduce every panel.

## Selected P00 direction

The user selected implementation on 2026-10-13 JST: research first, following the
legacy OCEAN principles; human-centered UI/UX, less copy, sky/baby-blue accents.
Use the legacy `#56b4e9` accent, softer blue surfaces and concise task labels.
Keep scientific caveats visible; reveal technical detail on demand.

## Experience to aim for

A researcher should understand where to begin, what data is being used, what
is happening and what they can do next. Start with the task and reveal detail
when it helps. Use a calm layout, familiar terms, legible typography, visible
focus, useful whitespace and predictable navigation. Give each state a clear
primary action instead of exposing every possible control at once.

Friendly language must retain scientific precision. Use conversational progress
such as “Checking available datasets” or “Preparing the comparison.” Report real
application activity when integrated; prototype activity is explicitly simulated.
Do not fabricate progress percentages, results, model reasoning or human identity.

## Core journeys to prototype

| Journey | Interaction to review |
|---|---|
| Start or resume research | A welcoming home with recent investigations, a clear new-investigation action and optional example questions |
| Find useful data | Catalogue navigation, search, dataset preview and a readable explanation of coverage and limitations |
| Choose context | “Use this data” adds context; “Limit this investigation to…” adds an explicit restriction. Browsing alone changes neither. |
| Ask and understand an answer | Compose a question, see the selected scope, review a readable answer and open evidence next to the relevant claim |
| Handle uncertainty | A clarification explains what is unresolved, preserves the draft and offers meaningful choices; partial results explain the missing work |
| Control long work | Clear queued/running/cancelling/completed states, elapsed time, cancel and resume; useful recovery after a simulated interruption |
| Review an experiment | Read the question, cohort, method, limitations, code and resource limits; revise or approve a simulated proposal and inspect labelled sample results |
| Return later | Reopen the investigation, switch conversations, locate retained evidence and understand which data version it uses |

Prototype every journey with representative fixtures, including empty, loading,
zero-match, unknown-coverage, error, unavailable, revoked-access and partial states.
A small coherent set of believable examples is more useful than many disconnected
screens. Sample names, measurements and findings must be visibly synthetic.

## Interaction principles

- Keep Research, Context Catalog and Tools understandable. The prototype may
  explore labels and grouping while preserving the full catalogue requirement.
- Prefer progressive disclosure: main answer and relevant context first;
  provenance, method details, identifiers and exact data versions on demand.
  Keep essential scientific limitations visible with their claims.
- Make the scope easy to see and change. Distinguish adding context from limiting
  scope using wording, preview and placement, without relying on color alone.
- Preserve drafts and selections when users open evidence, navigate back or
  recover from an error. Offer undo for reversible local changes. Confirm only
  actions whose consequences merit a review, including experiment approval.
- Use plain-language errors that explain the effect and next useful action.
  Keep technical diagnostics in a details view. Avoid dead buttons and unexplained
  disabled controls; show why an unavailable action cannot proceed.
- Give dense scientific tables room while keeping navigation quiet. A workspace
  should open when useful, be resizable/collapsible, and remember presentation
  preferences without changing scientific scope.
- On narrow screens use tabs/drawers, retain essential actions and avoid forcing
  simultaneous tiny columns. Verify touch targets, long labels and overflow.
- Support keyboard navigation, visible focus, semantic labels, screen readers,
  reduced motion, readable contrast, light/dark themes and English/Japanese.
- Make experimental, published and descriptive-query results distinguishable
  with words as well as visual treatment. Approval to execute never implies
  scientific approval of the result.

## Local feedback loop

1. Build a small navigable shell and one end-to-end investigation journey.
2. Open it locally for user review. Capture concrete friction and desired changes
   in the P00 handoff: confusing terms, extra steps, missing context, density,
   panel behavior, discoverability or misleading states.
3. Revise the experience and expand the remaining journeys. Prefer small focused
   review rounds; no fixed iteration count or calendar deadline is imposed.
4. Record the accepted direction, unresolved questions, screenshots and observed
   task walkthroughs. Reuse this frontend for backend integration.

The user should be able to explain the difference between “use this data” and
“limit the investigation,” find evidence for an answer, recover a draft and tell
whether an experiment has actually run. Observe these tasks; visual polish or a
screenshot alone does not establish usability. Record which behaviors the user
reviewed and any that still need feedback. Do not invent user acceptance.

## Frontend-to-backend boundary

Use typed provisional models for investigations, catalogue listings, context,
runs, evidence and experiments. Keep fixtures behind a replaceable adapter so
components do not scatter fake API responses or domain logic through the UI.
Document action names and observable states, not a premature database schema.

Expose a local-only scenario selector/reset outside the normal research flow.
Store only synthetic demo state locally. Use an obvious “Local preview · sample
data” indicator; simulation labels must remain on generated-looking outputs and
approval screens. No real authentication, model response, durable job, scientific
result or production access is implied.

C08 later reconciles these models with validated catalogue/scientific contracts.
C15/C16/C18/C20/C21/C25 progressively replace fixture behavior with verified v1
services. Keep useful UI decisions; correct a prototype interaction if it cannot
honestly represent scientific or execution constraints. P00 completion satisfies
only the local UX gate, not production, scale or backend acceptance.

## P00 review refinement — 2026-10-13 JST

The user reviewed the initial local preview positively and requested wordmark-only
branding (small library icons remain), a visible account type/access role, an
admin dashboard covering or extending legacy workflows, a dedicated About page,
a better catalogue landing with a light relationship map, feedback and exports.
The user clarified that “contracts” meant contacts; explicit creator/affiliation
and contact placeholders are acceptable for now.

P00 now previews these interactions locally. Admin roles/invitations/jobs, browser
persistence and feedback triage are simulations. Candidate map links never claim
verified physical identity; analysis references retain their different authority.
The latest refinement still needs user review. Real access control, feedback
services, export policy and scientific/cloud integrations retain their later gates.

### Accepted P00 direction — 2026-10-14 JST

The user accepted the working direction and requested Pipeline & jobs be omitted
from administration for now. The accepted UI has seven admin areas and no queue
controls or pipeline entry points. Backend job execution remains in C20/C24.
This local UX acceptance does not satisfy real-service or release gates.
