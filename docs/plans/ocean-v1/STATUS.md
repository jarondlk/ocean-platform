# OCEAN v1 beta — current status

As of **2026-11-27 JST**. This page is kept short and replaced, not appended.
The dated log is in [STATUS_HISTORY.md](STATUS_HISTORY.md); the remaining
work is in [beta/USABLE_BETA_PLAN.md](beta/USABLE_BETA_PLAN.md).

## What is live

| Part | State |
|---|---|
| Site | `https://beta.oceaninfobio.com`, Google sign-in, invite-only |
| Serving | `ocean-v1-beta-serving` generation 77, revision `ocean-v1-beta-serving-readable-062fa7a` (frontend `062fa7a`, API image unchanged since B2) |
| Research controller | `ocean-v1-beta-research-controller` generation 10, same API image as serving |
| Research delivery | Cloud Tasks queue and Scheduler job last recorded **paused** (Nov 24); manual operator dispatch only |
| Data in the catalogue | CTD, metagenome, MUR regional SST (2020–2023) and raw ANEMONE eDNA inventory (39 datasets) |
| Monitoring | Alert policies for queue backlog, Research delivery failures and SQL backups are active |
| Experiments | Not available to users (B3 open) |

## What a signed-in user can do today

- Browse the catalogue by collection, folder, search and filters.
- Create investigations and conversations, choose data, and reopen saved work.
- Read saved answers with citations, open evidence, and download CSV/JSON.

## What does not work yet

- **New questions are not answered automatically.** The question box accepts
  submissions, but delivery is paused, so a new question waits until an
  operator dispatches it. After 90 s the page now tells the user the question
  is saved and still waiting.
- **Answer wording is still technical** ("Retained object: …"). A verified API
  image with the readable templates is built
  ([candidate record](beta/answers-20261127/answers-api-candidate.json)); it
  goes live once the operator updates the research controller, after which the
  serving API is updated to the same image.
- **eDNA questions** cannot give scientific results: the live eDNA data is raw
  inventory with unknown or control classifications and no resolved sample
  identities.
- Experiments, Tools, Administration and Feedback are not integrated; they are
  hidden from the interface until they are.

## Milestones

| Milestone | State |
|---|---|
| B0 resume/preflight | Done (Nov 14) |
| B1 usable Research path | Accepted (Nov 16): real cited CTD answer, reload, recovery checks |
| B2 data and catalogue | Mostly done; live withdrawal check on a disposable source open |
| B3 production experiments | Private worker lifecycle passed; signed-in experiment journey open |
| B4 durable operations | Alerts live; unattended delivery, hosted restore and worker recovery open |
| B5 acceptance and release | Not started |

## Known issues

- CI: the legacy `frontend/` dependency audit fails until the Next.js security
  bump (PR #141, blocked on PR #142) reaches `main` and `overhaul`.
- The C26 acceptance check reports source changes since Oct 29 that were never
  recorded as authorized supersessions; this must be resolved before B5.
- Full cold navigation measured 17.7 s on Nov 16 (accepted as a known
  limitation); the focus-reload fix removes repeated reloads but has not been
  re-measured. On Nov 27 a cold open of a saved answer took about 6.5 s for
  answer events and 5.5 s for the evidence list.
