# C14 implementation review — 2026-10-16 JST

Three delegates implemented/reviewed disjoint core, API/tool and independent
scale acceptance work. Primary integration uses the actual frozen C09/C10–C13
stores/adapters and the same authenticated routes/tools. No live model/provider,
configured database or production service is used.

Resolved findings:

- Interleaved identity/title/language path text could not match ordinary joined
  paths. Separate canonical, English and Japanese ancestry paths now match full
  multisegment requests; dedicated core cases cover them.
- A global cache lock covered blocking view reads. Materialization now happens
  outside that lock; a blocked backend cannot serialize another identity's read.
- Node-only open hid Definition values and qualified relationship/source content.
  Explicit strict include_details mode delegates verified C13 inspection; actual
  frozen tests compare metadata, relationships, workflows and publication records.
- Query mapped all ValueError instances to client 422, including frozen byte
  corruption. C14-only integrity subclasses now qualify C10–C13 load failures as
  unavailable 503, while public parameter failures retain 422. Ten actual index/
  child corruption cases exercise five service entries after prior success.
- Malformed disabled requests differed at the API/tool boundary. Public validation
  now precedes the feature gate in both paths; six flag/service combinations and
  an unknown tool name regression establish matching sanitized outcomes.
- C13 child retention dependency ownership was still deferred. Explicit trusted
  registration now pins the index and exact children; tests exercise idempotence,
  partial interruption, concurrent retirement, missing pins and current withdrawal.

The frozen resolver always creates fresh policy-bound adapters, checks explicit
registrations/current lifecycle and disables caching. Only an explicitly supplied
immutable fixture backend opts into scoped view caching; the resolver still runs
on all 200 pages. No runtime fixture import/fallback exists. Prior accepted C08–C13
source and scientific/P00 evidence remain protected by the preservation baseline.
The three additive integration edits are config.py, api/main.py and api/auth.py.

Final acceptance and hosted delivery remain separate from these review notes;
read verification.json/delivery.json and the handoff for their actual state.

A final detailed-inspection review reproduced a privacy blocker in existing C13
metadata reference inspection: nested source metadata.related_ids retained denied
identities even though top-level node links were pruned. The new C14 serialization
boundary recursively filters those structured lists against the current permitted
view, including inside models/lists. A new core case and three actual sealed Data,
Metadata and Statistics cases preserve permitted links and exclude denied IDs.
No prior C13 source/receipt is modified.

The first combined required run was sandboxed and could not bind temporary
loopback fixture HTTP servers (nine failures/14 setup errors, all PermissionError;
2,332 tests passed). The original log/result remain as initial-sandbox evidence.
Final acceptance uses the same isolated test settings with local fixture server
permission and reruns after the privacy fix. No provider or production access is
required by these fixture servers.

Final error-order review also reproduced malformed-body precedence differences
for missing/viewer/suspended identities. Shared invocation now resolves/authorizes
its trusted identity exactly once before public validation, then checks feature
and service availability. Eight combined identity/flag cases prove status/body
parity with actual middleware. Final focused API/tool suite passes 121 cases;
core unit 64, scale/hardening 33 and actual frozen integration 56 pass.
