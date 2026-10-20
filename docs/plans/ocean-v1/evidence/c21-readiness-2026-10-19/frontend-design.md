# C21 frontend integration preparation

Read-only design against the current separate-v1 frontend and C21 specification.
C20 final source `a149239` is awaiting its final hosted gate at the time of this
preparation. This file does not select or implement C21, freeze a public schema,
claim browser acceptance or change any existing preparation/audit/receipt file.
No application tests, services, providers or cloud actions were run for this task.
Root must agree the exact DTOs after C20 delivery and C21 readiness/selection.

## Current seams and constraints

| Existing source | Reusable boundary | C21 integration |
|---|---|---|
| `src/research-workspace.tsx` | Current investigation/conversation/context, preserved draft, Chat/Workspace split and four tabs | Own answer-job selection, explicit answer creation/cancellation, citation selection and retained-receipt attachment. Keep C20 run mutation actions separate. |
| `src/research-activity.tsx` | Controlled run cards and fixed submitted-context details | Add a controlled answer-job/card component beside each eligible run; do not put new prose into `ResearchRun.result`. Replace production Results/Evidence placeholders with separate typed answer/evidence components. |
| `src/research-run-contract.ts` / `research-run-service.ts` | Accepted seven fixed C20 HTTP actions; literal production `result:null` | Leave version/envelopes and terminal run history unchanged. Existing `RunResult`/`RunEvidence` also serve the explicit older fixture and lack the production receipt/answer fields; do not reuse them as the C21 public authority. |
| `src/runtime.ts` / `runtime-app.tsx` | Verified optional service discovery; same-identity volatile session; access refresh hides private UI | Add separate optional answer/evidence capability blocks and clients. C20 `research_runs.synthesis` stays its current literal `unavailable`; absence of new blocks means unavailable. |
| `src/research-state.ts` | Canonical investigation/conversation/tab URLs, account+permission binding, exact pending intents | Add bounded answer/evidence selections and replay intents in volatile identity-bound memory. Any optional deep-link IDs are selections, never authority or mutation commands. |
| `src/research-history-scheduler.ts` / `research-history.ts` | Single-flight polling, fixed deadline, mutation pause, fresh authorization for recent explicit off-page run IDs | Reuse the scheduling policy for separate answer jobs, not C20 event cursors or DTOs. Prevent the same off-page-acknowledgement loss in answer-job pagination. |
| `src/catalogue-browser.tsx` `QueryView` / `ScientificContextLabels` | Literal table cells, units, known/unknown counts, source/query completion, qualifications | Extract presentation if useful; retained evidence must read its own immutable receipt/table service, never rerun a current catalogue query or `getPublished` to reconstruct an old citation. |
| `src/investigation-service.ts` | C17 typed `changeContext` and exact mutation replay | Reuse only the explicit artifact attachment operation after a receipt has a server-issued ready attachment reference. No automatic transcript/prose conversion or artifact pin. |
| `frontend/lib/csv.ts` and `src/exports.ts` | C07 `escapeCsvCell`/`rowsToCsv` and safe download mechanics | Reuse the shared escaping policy. Prototype `exportTable`, `receiptExport` and investigation exports intentionally inject P00 synthetic metadata; they are unsuitable for production evidence. |

The prototype `src/ui.tsx` DataTable always captions data as a sample and splits
strings containing ` / ` into a presumed translation. Production retained tables
must preserve literal scientific strings and object/array values; do not reuse
that renderer unchanged. Its plot helper also embeds synthetic fixed descriptions.
Keep those prototype behaviors separate rather than silently relabelling fixtures.

## Proposed small public action surface

Names and versions here are proposals for root/schema ownership. Prefer two
clients, fixed same-origin POST endpoints, strict exact envelopes and no endpoint
URLs supplied by a receipt, generated answer, browser preferences or query string.
All reads are side-effect free and freshly authorized; none enqueues generation.

| Client/action | Minimal client input | Public response purpose |
|---|---|---|
| `AnswerClient.submit` at `/research/answers/submit` | Run/investigation/conversation IDs, actual requested `locale`, UUID idempotency key; optional expected terminal input version only if supplied by a verified eligibility view | Create/recover one synthesis job bound server-side to the terminal run's exact evidence anchor and remaining combined budget. No client-supplied scope, question, receipts or model prose as authority. |
| `AnswerClient.list` | Investigation/conversation, optional run filter, bounded limit and opaque cursor | Discover persisted answer jobs and immutable answer IDs; default 25. Explicitly acknowledged jobs outside the loaded page require fresh status before retaining them. |
| `AnswerClient.status` | Job plus investigation/conversation/run IDs | Current job state, immutable anchor identity, public budget counters, event high water, published answer ID or controlled unavailable reason. |
| `AnswerClient.events` | Same address, committed after-cursor and bounded limit | Controlled public progress, consecutive cursors, next cursor and separate latest cursor/has-more. No prompts, private reasoning, full tables or raw model outputs. |
| `AnswerClient.cancel` | Same address plus original UUID idempotency key | Request cancellation of this synthesis job only. Exact replay is safe; C20 cancellation is not a substitute. |
| `AnswerClient.get` | Immutable answer ID plus investigation/conversation/run address | Load a freshly permitted immutable answer and its citation targets. It never regenerates or upgrades it to a different publication. |
| `EvidenceClient.list` at `/research/evidence/list` | Investigation/conversation/run address and bounded cursor/limit | Discover retained deterministic receipts even when generation is disabled, exhausted or unavailable. |
| `EvidenceClient.open` | Server-issued receipt ID and expected original snapshot, plus authorized host context | Permitted bounded metadata, original authority, qualifiers, preview and table descriptors; ready `attachment_reference` when the storage-protection protocol is committed. |
| `EvidenceClient.page` | Receipt/table IDs, expected immutable receipt/payload hashes, bounded limit and opaque cursor | Read retained rows with immutable binding and policy-scoped pagination. Changing policy or payload invalidates the cursor; no fresh query is run. |
| `EvidenceClient.export` | Receipt/table IDs, `csv` or `json`, explicit full-versus-page selection and bounded request | Fresh `data:export` authorization and C07-safe CSV or original structured JSON, with provenance and honest completeness/truncation. No arbitrary external URL or legacy download path. |

Suggested families are `research-answers-v1` and `research-evidence-v1`. Keep
job IDs distinct from immutable answer IDs, receipt IDs and C20 run IDs. Replaying
submit/cancel uses the original body/key; another locale/key/version cannot reset
the per-run shared allowance. A separate retry endpoint is unnecessary if exact
submit replay returns the existing job and recovery stays server-owned.

A root-confirmed optional bootstrap could expose `research_answers` with version,
`http-v1|unavailable`, submit/dispatch booleans and reason, and `research_evidence`
with version, transport, read/export/attachment booleans and reason. Submission
and evidence read/export are independently discoverable so disabling new work
preserves permitted historical reads. Flags supplement current backend permission
checks. Do not infer permissions from role/account labels; exports use actual
`data:export`, and attachment uses the C17 mutation authority.

## Public projection needed by the frontend

An answer-job snapshot needs its full address and run/input/context anchor,
status, actual locale, immutable output identity, controlled error/reason,
committed/latest event cursors, persisted active synthesis time and combined
budget view. It must make eligibility/unavailable reasons readable without
revealing a revoked receipt's names, values, counts or body. Any server operation
key used for lost-acknowledgement recovery stays private account-bound memory.

An immutable answer needs answer/job/run/input IDs, the five-field context binding,
controller/evidence-pack identity references, actual generated locale,
host-assessed completion, unresolved work and mandatory limitations, typed fact
references, labelled model narrative and stable citation targets. A citation is
an allowlisted receipt ID/hash actually supplied to the synthesis pack, optionally
with a host-validated table/fact target. Numbered markers are presentation only.
Do not resolve arbitrary generated strings as an evidence URL or permit a model
to supply an independent receipt list. Render text as text; no source HTML.

Receipt metadata needs receipt version/ID/hash, original run/input/binding,
original authority and evidence kind, operation/version, exact parameters/hash,
executed scope, complete-input manifest identity/count/hash, payload/result hashes,
source completeness, query completion, semantic total and denominator, returned
preview count, truncation, units/descriptors, scientific/publication compatibility
and mandatory qualifications. Preserve hash domains separately. Public metadata
must not expose storage paths, credentials or private replay/provider envelopes.

Table descriptors/pages need stable table ID, original receipt/payload identity,
unique ordered columns and units, typed literal JSON cells, page position,
returned count, complete-scope total (`known` versus `unknown`) and denominator,
next cursor and current access revision. A zero total is distinct from missing or
unknown; a 100-row preview is not a population of 100. Reject unsafe numeric
integers instead of rounding exact counts; if large exact integers are needed,
root must declare a lossless canonical representation rather than implicit
`Number(...)` conversion. Sorting/filtering must be explicitly supported and
receipt/policy-bound; do not sort one preview and imply a full-table result.

Prefer a bounded export response carrying filename, content type, exact byte/hash
identity and provenance plus CSV/JSON content, or an equally validated same-origin
binary response with those metadata fields. Root must choose one concrete shape
and byte limit. Server-generated CSV uses the existing Python C07 serializer;
client-rendered authorized rows use the TypeScript C07 helper exactly once. Do not
double-escape a server CSV. If a full export exceeds its bound, report unavailable
or explicitly partial; never label a current page as the complete retained table.
Preserve canonical raw values in structured JSON and retained payloads.

## UI composition and state behavior

Keep P00's Research-first split, quiet navigation, sky-blue accents, mobile
Chat/Workspace panes and existing Context/Results/Experiments/Evidence tabs.
Answer and retained-evidence views belong in this Workspace, not a new admin
pipeline or a replacement catalogue. Essential scope/authority/limitations stay
visible; technical hashes, exact parameters and storage-independent provenance
are available in details. Keep EN/JA controls and keyboard focus behavior.

For an eligible completed/partial exploration, show a plain explicit action such
as “Prepare answer” and a reason when it is unavailable. A new question still
uses the C20 composer. If root preserves a single-submit answer journey instead,
record that answer intent durably at the original authorized submission and let
the backend orchestrate the separate job. Do not have mounting history, opening
a receipt or polling a completed run silently invoke `AnswerClient.submit`. An answer card and job progress live adjacent to the
original run/question; Results lists freshly authorized immutable answers for
this conversation. Switching tabs or opening a citation preserves the draft,
selected run and shared context. The card shows the answer's actual output locale;
switching shell language changes controls, not ungenerated prose. Do not invent
a Japanese/English translation or reuse prototype slash-separated translations.

Opening a citation selects its immutable ID, opens/resizes the Evidence workspace
and focuses its heading. On mobile, switch to Workspace and provide a predictable
return to the claim; closing/restoring focus must not reset the question draft.
The inspector has loading, available, zero rows, unknown coverage, partial,
error, unavailable and withdrawn states, literal paged tables and separately
labelled download/attachment actions. Unsupported evidence is unavailable rather
than an empty table. Never open a legacy/current publication as a hidden fallback.

Use controlled C21 components and a workspace-owned coordinator: e.g.
`research-answer-contract/service`, `research-evidence-contract/service`,
`ResearchAnswers` and `RetainedEvidence`. `ResearchActivity` stays the exploration
view. Its completed `result:null` message can be coordinated with a separate
answer-job state by its host, without changing C20's DTO or fabricated body.
Avoid scattering fetches or authorization rules inside citation renderers.

## Separate status, budget and cancellation semantics

Exploration and synthesis have separate job identities, event cursors, progress
and cancellation. A synthesis job may be queued/running/cancelling/completed/
partial/cancelled/failed/unavailable if root defines those states. A frontend-only
“Cancellation requested” state is safer than claiming it stopped before the
worker fence confirms it. The server decides cancellation-versus-publication
races; a winning committed answer remains an answer, not a forged cancellation.
Abort/unmount/disconnect only aborts HTTP, not durable work.

C21 uses the remaining shared C20 run-segment budget, not another 180 seconds or
fresh repair/model allowance. Show actual persisted synthesis elapsed time and,
on demand, server-owned combined counters/remaining allowance and invalid-clock
reason. Do not add browser wall time, fabricate percent complete or reset elapsed
on retries. A new locale/key cannot restore spent time or repair allowance.
Terminal run history remains immutable. Explicit C20 continuation is the separate
run segment; there is no automatic “continue generation” budget reset.

Job generation completion and scientific completion are independent. A fully
received model response can still yield a partial answer because host work is
unresolved. Unknown source coverage remains a qualifier without the frontend
reinterpreting host completion. Preserve exact descriptive, published,
documentary and experimental authority at the claim/receipt level. A mixed answer
must not receive a blanket “published” badge or imply scientific approval.

## Explicit retained-receipt attachment

Citation opening, previewing and downloading are reads. Attaching is a separate
button, labelled “Attach retained evidence”, showing its original snapshot and
that it adds shared context. Use only `EvidenceClient.open`'s server-issued ready
reference, for example `{kind:'artifact',id:<receipt artifact ID>,snapshot_id:
<original receipt snapshot>}`. Root's trusted C17 artifact resolver checks its
owner/hash/current policy, while C21 independently protects referenced snapshots,
ancestor holds and attachment dependencies before exposing a ready reference.
No client can establish readiness merely by constructing this object.

Submit the existing `changeContext` intent with the current destination
investigation ID, freshly verified expected head revision, UUID idempotency key
and `{op:'attach',reference}`. Existing exact replay/conflict review applies.
The destination may be another permitted conversation/investigation only through
an explicit action and server authorization; do not fetch/copy its transcript.
Successful attach creates a new C17 revision for future submissions and leaves
existing runs/answers unchanged. It never copies generated answer prose into
scientific context, converts a receipt into an artifact pin, changes source counts
or automatically broadens an older receipt's scope to the current snapshot.
If the protection registration or acknowledgement is uncertain, retain/replay its
same operation and report pending/unavailable instead of claiming it is attached.

## Identity, policy, navigation and race safety

Keep all answer bodies, receipt pages, selections and pending mutations only in
account+permission-revision-bound memory. Bind/clear alongside RuntimeApp's
existing ResearchSession, including acknowledgement metadata. Runtime loading
hides private content. A changed identity/permission revision or authoritative
401/403 clears private caches and pending intents. An unchanged identity can
retain hidden memory through temporary revalidation, but nothing is displayed
again until its answer/evidence reads authorize current access.

Evidence/answer responses and cursors also need a current source-policy/access
revision. Runtime identity revision alone does not prove a catalogue has not
withdrawn a cited source. Revalidate on opening, paging, export and explicit
attachment, and on focus/visibility/appropriate idle refresh. A changed revision
invalidates dependent answer/receipt pages and restarts at the permitted first
page. A revoked/unavailable citation invalidates cached bodies that may contain
its facts too; hiding just the citation label can still leak withdrawn content.
The backend must return a controlled unavailable answer when required evidence
is revoked. Do not silently regenerate a replacement from current publications.

Key each request by account, permission/source revision, investigation,
conversation, run/input, answer/receipt hash, table and page. Clear selected views
on conversation/navigation changes, abort promptly, and reject late responses
using selection/identity/epoch and signal checks after every await. Run one
request at a time per view with a fixed deadline. Poll ticks coalesce; mutations
pause history and trigger a fresh read after their result. Receipt pages or
signed cursors from a prior revision cannot be appended to a new view.

If reload deep links are added, extend the pure ResearchLocation parser with
validated answer/receipt/table selection IDs, preserving `view=research` and the
current investigation/conversation. URLs must not carry scope, authority, private
body, token, pending intent or automatic attach/start/cancel commands. Reopening
always authorizes the ID. Page cursors can remain volatile and restart at the
first page. No private state enters localStorage, sessionStorage or service-worker
caches; existing presentation preferences remain the only persisted UI settings.

## Suggested ownership and verification after selection

Root/schema owner freezes exact capability, public action/DTO, byte/page/export
bounds and safe errors; evidence/store owner supplies owner/policy/hold-aware
receipt loading/protection; synthesis owner publishes immutable validated answers
with shared-budget fencing. Frontend then implements the two strict clients and
controlled views, with small changes to runtime discovery, workspace coordination
and identity-bound state. Keep backend scientific membership/authority rules out
of browser heuristics and preserve original source/receipt supersession chains.

Meaningful frontend cases should cover real saved Python-to-TS DTO parity; all
answer actions; unknown versus known zero; totals versus previews; literal strings
containing ` / `; negative numbers versus textual formulas/unsafe headers in CSV;
large-page bounds; citation-to-unseen receipt rejection; no arbitrary HTML/URL;
actual output locale; partial generation/host completion; disabled dispatch with
permitted historical reads; exact lost-acknowledgement replay; separate cancel
race; off-page job acknowledgement; slow single-flight refresh; changed binding/
source revision; revoked citation/body; late navigation/identity response; and
explicit artifact attachment/conflict without prose/pin side effects. Use strict
synthetic/mocked unit fixtures and preserved actual wire captures, correctly
labelled. C26 remains assembled browser/reload/reconnect acceptance; no synthetic
test or screenshot establishes independent scientific review or live factual
accuracy. No new user decision blocks this design preparation; root's concrete
contract choices and the formal selection gate still precede implementation.
