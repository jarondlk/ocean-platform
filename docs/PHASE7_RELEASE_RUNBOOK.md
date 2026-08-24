# Phase 7 prototype release runbook

Phase 7 validates the authenticated Vertex-backed prototype with a deliberately
small cohort before any broader research-team invitation. It does not increase
Cloud Run scale, database size, model quotas, or any component budget.

## Approved cohort

| Account | Intended role | Purpose |
| --- | --- | --- |
| `dilokkalayakul.jaronchai.p8@dc.tohoku.ac.jp` | Admin | Operations, feedback review, recovery, and release evidence |
| `akane.kitamura.e7@tohoku.ac.jp` | Researcher | Real-provider research workflow and role-boundary validation |

One researcher plus the existing administrator is sufficient for this
prototype phase. Viewer-only behavior remains covered by automated authorization
tests and is not a live-user release gate. Do not suspend either real account
without coordinating the test window with that person.

## Hard execution limits

- Cloud Run remains at minimum zero and maximum one instance.
- Test concurrency never exceeds five requests.
- The reusable probe cannot run longer than five minutes.
- A single mixed-load run cannot exceed 300 reads or 18 chat generations.
- The entire Phase 7 exercise stops after 32 chat generations, including
  browser smoke tests, load calls, rollback checks, and retries.
- Do not run the pipeline, embedding refresh, or full evaluation suite.
- Cloud Run Jobs remain manual, one task, and zero retry.
- Do not increase a quota, timeout, instance limit, pool size, or budget during
  the release exercise.

Stop immediately on an unexplained 5xx response, database pool timeout, secret
or token in logs, unexpected cloud resource, model retry storm, invalid answer
citation, or a component reaching 75% of its monthly envelope.

## 1. Freeze and record the baseline

Record, without mutation:

1. active Cloud Run revision, immutable frontend/API images, traffic split,
   service account, concurrency, and min/max scale;
2. Cloud SQL tier, storage size/limit, backup/PITR configuration, and connection
   baseline;
3. Cloud Run Job identities, task counts, retries, timeouts, and stored safe
   defaults;
4. billing link plus project/component budget state;
5. application counts for users, invitations, chats, feedback, audit events,
   evaluation runs, retrieval documents, and embedding provenance; and
6. the current git commit and clean worktree.

Create a full logical backup labelled `phase7-pre-release` and run the isolated
restore test. Keep the archive, JSON manifest, SHA-256, table counts, and restore
duration in the release record. The disposable restore database must be removed
after verification.

## 2. Run local and build gates

Before spending Cloud Build time:

```bash
python -m ruff check .
python -m pytest -q
cd frontend && npm run typecheck && npm run build
```

Run the Phase 7 probe in dry-run mode to inspect its fixed limits:

```bash
python scripts/phase7_release_probe.py \
  --base-url=https://onagawa-source-chat-469489188516.asia-northeast1.run.app \
  --mode=load \
  --duration-seconds=300 \
  --concurrency=5 \
  --read-requests=120 \
  --chat-calls=18
```

The probe is dry-run by default. Production traffic additionally requires
`--execute`, an exact `--confirm-host`, and a private `0600` cookie-header file
outside the repository. Never paste a session cookie into a command, commit it,
or include it in an artifact. Delete the temporary file immediately after the
test. The sanitized JSON output contains endpoint, status, latency, model, and
citation counts only; it never stores cookies, prompts, or answers.

## 3. Authenticated journey

### Administrator

1. Sign in through Google OIDC and confirm the admin/internal identity.
2. Verify Overview reports 323 retrieval documents and healthy API, database,
   and model runtime.
3. Verify the researcher account is active with role `researcher` and account
   type `research`.
4. Run one fixed chat question and require a completed response, Vertex model,
   at least one citation, zero invalid citations, and a strong trust report.
5. Save thumbs-up feedback with a short synthetic release-test comment.
6. Confirm the feedback appears in the admin review page and CSV export.
7. Confirm the corresponding chat/feedback audit records exist.

### Researcher

The researcher performs the login and query from their own browser session.
Do not impersonate them or share session state.

1. Sign in through Google OIDC.
2. Open Overview, Explore, Data, Provenance, Evaluation, and Chat.
3. Confirm Users, Feedback administration, Pipeline, Database, System, and
   Debug are unavailable.
4. Run one fixed research question and inspect the cited evidence.
5. Save feedback and confirm it remains visible after sign-out/sign-in.

Viewer and suspended-user boundaries remain required automated tests but are
not exercised against a live person in this reduced cohort.

## 4. Persistence across a release-candidate revision

Capture database and artifact counts, deploy one immutable release-candidate
image, and leave maximum instances at one. After 100% traffic reaches the new
revision, verify:

- the two users and their roles are unchanged;
- pre-existing chat, feedback, and audit rows remain available;
- evaluation history remains available;
- all 323 retrieval documents retain Vertex provider/model/dimension metadata;
- the new authenticated smoke record is present; and
- unauthenticated traffic still redirects to login while the API sidecar has no
  public endpoint.

Do not run or downgrade a database migration solely to create a new revision.

## 5. Controlled mixed-load test

The approved production run is five minutes, five-way maximum concurrency,
120 authenticated reads, and at most 18 evenly paced chats. The chat schedule
is capped below the application's ten-per-minute user limit.

Acceptance criteria:

- zero unexpected 4xx or 5xx responses;
- read p95 below two seconds after warm-up;
- chat p95 below 30 seconds and none above 120 seconds;
- no Cloud SQL pool timeout or connection exhaustion;
- no sustained Cloud Run CPU or memory above 80%;
- one serving instance throughout the test;
- no Vertex unavailable, quota, truncation, or retry-storm errors; and
- every returned answer audit has zero invalid citations.

The result file is operational evidence, not a benchmark. It must not contain
session state, prompts, answers, database URLs, or secret values.

## 6. Rollback and restore exercise

1. Confirm the previous known-good revision still exists.
2. Route 100% traffic to it without changing the database.
3. Verify login, Overview, one chat, and stored feedback.
4. Record application rollback time; target less than ten minutes.
5. Route traffic forward to the release candidate and repeat the health check.
6. Restore the pre-release archive into a disposable database, apply current
   migrations there, and compare all application and corpus table counts.
7. Record restore time; target less than 30 minutes.
8. Remove only the disposable database. Never restore over production and never
   automatically downgrade the production schema.

## 7. Security and operations gate

Before inviting anyone beyond the approved cohort:

- triage every open dependency alert; unresolved high-severity findings block
  release unless a written non-applicability decision is reviewed;
- verify required CI checks and CodeQL for Python and JavaScript/TypeScript;
- choose and document chat/feedback retention (90 days is proposed but not yet
  enforced);
- record incident and billing contacts;
- inspect Cloud Logging for tokens, secrets, restricted prompts, request bodies,
  authorization failures, model failures, and database pool errors; and
- verify `environment=prototype` and `cost_component` attribution in posted
  billing data.

## 8. Cost and go/no-go review

Review posted billing after 24 hours and again after seven days. Billing data
can lag, so do not treat an empty current-day report as zero spend. Compare
Cloud SQL, Cloud Run serving/jobs, Vertex AI, Storage, Build, Registry, Secret
Manager, and Logging against the envelopes in `deploy/gcp/MIGRATION_PLAN.md`.

The broader research-team decision is **go** only when:

- every immediate technical and recovery gate passed;
- there is no unexplained or unlabeled spend;
- actual spend is below every stop condition;
- the projected monthly amount is within the component and project envelopes;
- dependency, retention, logging, and incident-contact gates are closed; and
- seven consecutive days show no availability, authorization, integrity, or
  citation regression.

Do not increase Cloud Run maximum instances from one to two as part of Phase 7.
That is a separate post-release decision based on measured connections and
remaining monthly budget.

## Execution record — 2026-08-21

Current decision: **keep the bounded two-person prototype live; do not widen the
cohort until the time-delayed cost reviews pass**. The immediate serving,
persistence, recovery, model, resource, CI, dependency, researcher-login,
retention-decision, and operations-contact gates passed. Automated retention
enforcement remains separate implementation work.

### Release and recovery evidence

- The frozen Phase 6 revision was `onagawa-source-chat-00006-ms2`. The first
  Phase 7 release candidate was `onagawa-source-chat-00007-xpm` from build
  `25b94a3d-7a01-45e2-99ea-b07b22909778`.
- The pre-release logical backup is
  `20260821T065606Z-phase7-pre-release-onagawa_rag.dump`, SHA-256
  `1b0607d4b489d645c2b2a153565a7bc128d74a265cb23b7184047fb4137a6783`.
  It contains 16 tables and 110 TOC entries. Its isolated restore test passed,
  all recorded table counts matched, and the disposable database was removed.
- Traffic was routed from the Phase 7 candidate to the known-good Phase 6
  revision and forward again in under 15 seconds without changing the database.
- Cloud Build initially omitted `frontend/app/data/page.tsx` because the
  unanchored `.gcloudignore` entry `data/` also matched the nested Next.js route.
  The exclusion is now anchored to `/data/`, and Cloud Build fails if either the
  source page or standalone server artifact is missing. One explicitly approved
  corrective build, `8341812f-ca9d-458e-bdbb-17ea7c150e18`, produced live
  revision `onagawa-source-chat-00008-926`; `/data` now returns the complete
  authenticated catalog UI.

### Authenticated and load evidence

- The administrator journey completed through Google OIDC. The fixed smoke
  answer used Vertex `gemini-3.6-flash`, completed in 11.033 seconds, and had 13
  valid citations, zero invalid citations, zero warnings, and a Strong/100%
  trust result. Positive feedback persisted across the revision.
- The approved researcher remains active as `researcher` / `research`. The
  operator confirmed that Akane can sign in successfully through Google from
  her own session; no administrator impersonation was used. Automated
  authorization tests remain the evidence for the detailed role boundaries in
  this reduced prototype cohort.
- Sixty five-way core-route navigations completed successfully. They generated
  166 authenticated backend reads—below the 300-read hard cap—and all returned
  HTTP 200. The health/stats subset matching the release probe had 0.485-second
  p95 latency. The full backend-read p95 was 8.031 seconds because 12 concurrent
  provenance-manifest diagnostics scanned the GCS-mounted lineage data; this is
  recorded as a performance follow-up and the normal cohort must not repeatedly
  refresh that diagnostic under concurrency.
- Two additional Vertex chat calls on the corrected revision completed in
  8.493 and 6.692 seconds. Their trust reports contained 16 and 18 valid
  citations respectively, with zero invalid citations and zero warnings.
- The window used one Cloud Run instance. Peak one-minute CPU utilization was
  33.5% and memory utilization was 11.8%. There were zero 5xx responses, severe
  logs, database-pool errors, and model-failure patterns. The only observed 4xx
  responses were three expected missing-`favicon.ico` requests.

### Security and operations evidence

- `npm audit --omit=dev` reports zero production findings after overriding the
  vulnerable PostCSS/Nano ID chain to `8.5.23` / `3.3.18`. A disposable
  `pip-audit` scan of `requirements/dev.txt` reports no known Python
  vulnerabilities. Approved build `48ffbcd3-3839-4d9b-977f-de1b4df7ab19`
  deployed revision `onagawa-source-chat-00009-x8f` at 100% traffic. Direct
  inspection of the published standalone image confirmed PostCSS `8.5.23` and
  Nano ID `3.3.18` in the live runtime.
- CI now runs on `gcp-dev` and audits production npm dependencies. Its first
  remote run passed the backend, frontend, PostgreSQL, backup/restore, and npm
  audit jobs. GitHub confirmed that repository-level CodeQL default setup is
  already enabled; the temporary duplicate advanced workflow was removed after
  GitHub correctly rejected it. Default-branch Dependabot alerts remain open
  until the security lockfile change is merged.
- A counts-only scan of 2,142 Phase 7 log entries found zero credential, prompt
  or answer, authorization-failure, database-pool, and model-failure patterns.
- The administrator feedback export endpoint returned HTTP 200 in 0.084
  seconds. The browser harness did not surface its Blob download as a download
  event, so a human save/open check remains useful but the authenticated server
  export path is proven.
- Chat/evidence/audit snapshots and associated feedback have an approved
  90-day retention period. No data was deleted; dry-run, legal-hold-aware,
  audited enforcement remains separate implementation work.
- The project owner/application administrator is the primary incident contact.
  Takeshi Obayashi is the primary billing contact through the existing IAM and
  billing assignments. Contact addresses remain in the private account/IAM
  systems rather than being added to this public repository.

### Remaining no-go items

1. The security update reaches the default branch so its
   Dependabot alerts close; CodeQL remains enabled through GitHub default setup.
2. Retention enforcement is implemented and reviewed before the cohort expands;
   the approved policy by itself does not authorize immediate deletion.
3. Posted billing is reviewed after 24 hours and again after seven days. Per the
   operator's decision, these reviews remain pending until their data is due.

The former Provenance performance no-go item closed on 2026-08-24. Snapshot
`provenance-20260824T064300Z` is live on revision
`onagawa-source-chat-00011-4pd`; integrity, authenticated UI/trace behavior,
and the bounded concurrency gate passed as recorded in
`docs/PROVENANCE_SNAPSHOT_RUNBOOK.md`.
