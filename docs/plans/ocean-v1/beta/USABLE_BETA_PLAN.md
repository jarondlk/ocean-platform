# Plan — from current beta to a usable beta

Written 2026-11-27 JST. Current state: [STATUS.md](../STATUS.md). This plan
orders the work so that invited researchers can rely on the beta as early as
possible; the full release gates stay in
[BETA_COMPLETION_PLAN.md](BETA_COMPLETION_PLAN.md) and are not weakened here.

## What "usable" means

An invited researcher can, without operator help:

1. Sign in, browse the catalogue and understand what each dataset is.
2. Ask a question about CTD, SST or metagenome data and receive a readable,
   cited answer within a few minutes.
3. Reopen the answer and its evidence later, and download the evidence.
4. See plainly when something is delayed, unavailable or not scientifically
   reviewed — and report a problem.

Operators are alerted when delivery fails, and costs stay inside the existing
¥50,000/month beta target. Experiments are **not** part of "usable"; they stay
labelled as coming later until B3 passes.

## Who can do what

- **CLI identity (this Mac / Claude):** code, tests, image builds, updates to
  `ocean-v1-beta-serving`, read-only checks.
- **Operator (you):** research controller updates, Cloud Tasks queue and
  Scheduler, SQL, secrets, IAM, user enrollment, budget decisions.
- **Scientific reviewer:** eligibility of eDNA cohorts and any published
  analysis.

## Work, in order

### 1. Answers arrive automatically — blocking

Today questions can be submitted, but delivery is paused, so they wait for a
manual dispatch.

| Step | Owner | Done when |
|---|---|---|
| Show users when delivery is paused ("answers are delayed") instead of an endless "queued" state | CLI | **Partly done (gen 77):** items queued for 90 s show a saved-and-waiting notice. The runtime cannot see the queue, so a true "paused" message needs a server flag set by the operator |
| Run the live outbox-health check and the exhausted-task recovery trial (B4 open items) | Operator | Both receipts recorded; no stuck explorations or answers |
| Set queue rate limits and per-day model budget, then resume the queue and Scheduler | Operator | Queue `RUNNING`, Scheduler enabled, limits read back |
| Supervised soak: 10 real questions over 48 h | Operator + CLI | All answered unattended; alerts silent or acted on; cost measured |

### 2. Answers are readable — blocking

| Step | Owner | Done when |
|---|---|---|
| Build one API image: live B2 runtime `0994e9d` plus only `orchestration/research_synthesis.py` and its tests from `8686f6a` (applies cleanly), on its own branch with hosted CI and a qualification receipt, packaged as an overlay like `deploy/gcp/beta/b2/prepare_api_context.py` | CLI, after you approve the branch | Build and offline proof pass |
| Update the research controller to that image first | Operator | Controller ready on the new image; readback matches |
| Update the serving `api` container to the same image; record receipt and extend the dispatch guard | CLI | Generation 77 live; serving and controller images equal |
| Re-ask the saved MUR question and one CTD count | CLI (signed in) | Answers read as sentences ("MUR … v04.1 …", "N datasets — counted as …") |

### 3. The answers are right for real questions — blocking

| Step | Owner | Done when |
|---|---|---|
| Agree a starter set of ~10 questions (CTD, SST, metagenome) with expected answers | You + reviewer | Question list and reference results written down |
| Run them one at a time within the validation allowance; record each outcome | CLI + operator | Each answer matches its reference or the gap is filed |
| Fix clarification and partial-answer cases found | CLI | Re-run passes |
| Put the verified questions on the welcome screen as examples | CLI | Examples shown in EN/JA |
| Mark eDNA as "inventory only — not yet scientifically reviewed" in the catalogue and answers | CLI | Visible wherever eDNA appears |

### 4. It feels fast enough — important

| Step | Owner | Done when |
|---|---|---|
| Re-measure cold navigation and investigation/conversation opening on generation 76 | CLI | Numbers recorded (was 17.7 s full cold navigation) |
| Remove duplicate list/snapshot requests and slow first catalogue reads | CLI | Each screen loads in under 5 s on the beta, or the gap is explained |

### 5. Users can get in and get help — important

| Step | Owner | Done when |
|---|---|---|
| Decide the first group of beta users | You | Names/roles agreed |
| Enroll them with the existing enrollment tooling | Operator | Each can sign in with the intended role |
| Replace the "Feedback unavailable" page with a working contact (email or issue link) | CLI, needs the contact address from you | Visible from the app menu |
| Short About/help text: what the data is, what "descriptive" and "not reviewed" mean | CLI | Reviewed by you |
| Hide or relabel Experiments, Tools and Administration until they work | CLI | **Done (gen 77)** |

### 6. Keep the repository healthy — in parallel

| Step | Owner | Done when |
|---|---|---|
| Merge PR #142, rebase and merge #141, bring the Next.js bump to `overhaul` | You approve, CLI does | CI green on `main` and `overhaul` |
| Record the C26 source supersessions since Oct 29 | CLI | `run_system_acceptance.py` audit passes |
| Continue the UI wording pass (Workspace context panel, evidence page) and move copy into the EN/JA table | CLI | No internal terms in normal screens |

## After "usable": finishing the beta (unchanged gates)

- **B2:** live withdrawal on a disposable source.
- **B3:** signed-in experiment from proposal to download, worker network and
  restart checks.
- **B4:** isolated hosted restore with measured RPO/RTO; integrated worker
  recovery; sustained delivery.
- **B5:** C26 evaluation on the deployed candidate, C27 rollout/rollback
  rehearsal, security findings (#104) triaged, scientific and release sign-off.

## Decisions needed from you

1. Is "usable" without experiments acceptable for the first invited users?
2. Who are the first beta users, and which roles do they need?
3. Daily model-call budget and queue rate for unattended delivery.
4. Who reviews the starter questions and the eDNA labelling?
5. Whether to grant the CLI identity update access on the research controller,
   or keep controller updates as an operator step.
