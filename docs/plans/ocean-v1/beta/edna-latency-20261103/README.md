# eDNA latency audit — local transport only

No application source, cloud resource, activation, classification or deployment
was changed by this audit. The private complete-cohort activation is3fee1bae:
39eDNA datasets/349638detections. eDNA remains held from the immediate phase1
activation until actual transport/latency gates pass. Results here use real
sealed bytes, explicit test-only local transport and a synthetic admin principal;
they are not actual Google-session/GCS/production acceptance.

## Measured cause

A real eDNA-only C14 overview takes14.492seconds locally. 39complete
`load_dataset` calls take12.400seconds; `validate_rows` takes9.301seconds,
Parquet-to-frame parsing3.077seconds, repeated primitive validation3.359seconds,
and353136JSON validation calls3.204seconds. These are nested inclusive timers:
do not sum them. 79fresh snapshot reads take1.830seconds locally. C14 creates
fresh adapters per operation and C13 retains complete source/namespace validation,
so another request repeats the full semantic work.

A separate cProfile of the largest dataset (20360detections) takes1.925seconds
under profiler overhead:1.631seconds in semantic `validate_rows`,0.529seconds
JSON validation,0.443seconds taxonomy assignment and0.403seconds primitive
validation. The profile is diagnostic, not an unprofiled performance figure.

## Private measurement prototype

A private in-process prototype caches only fully validated C12 DatasetInputs,
keyed by canonical child manifest and metadata identity. Every hit first verifies
all owned current payload sizes/SHA256; the original fresh snapshot/control/
activation reads, complete C13 namespace/collision checks and current dataset
policies still execute. The prototype returns detached metadata/objects and
copied DataFrame object arrays, whose validated string/number/bool/null cell
values are immutable. It does not cache user access, filtered outputs, scientific
eligibility, catalogue nodes or current visibility decisions.

Actual measured results, with source fingerprints unchanged throughout:

| Operation | Local wall time |
|---|---:|
| Cache fill / cold overview |14.802s|
| Warm overview |1.891s|
| Warm5-row raw detection query |1.582s|

The two overview response objects match exactly. All39datasets are retained;
39misses and79hits were observed. Conservative pandas deep-memory accounting is
707492049bytes (~675MiB), so a512MiB DataFrame cache cannot hold the full cohort.
The bounded1GiB/64-entry measurement prototype fits; measured whole-process peak
RSS is1234436096bytes (~1.15GiB). That budget is a prototype, not an accepted
production setting or a concurrency/eviction test. Object-array copies share
immutable primitive string values; summing deep-memory figures over copies
would overstate actual retained string memory. First failed budget and malformed
query-harness attempts are separately disclosed; no partial query is accepted.

There are only18497distinct taxonomy JSON strings summed within datasets across
349638detection rows. A bounded per-load memo of already validated taxonomy and
its shared deepest-assignment result can improve cold validation without storing
an access decision or skipping any row's foreign-key/count/concentration checks.
Precompiling the primitive-field validation plan also avoids reconstructing Arrow
type comparisons for every cell. Both require their own owning C12 tests.

## Recommended implementation

1. Add a bounded, byte-accounted, thread-safe semantic-input cache owned by the
   trusted FrozenCatalogueResolver/service instance, initially eDNA only. Keep
   the existing frozen *view* cache disabled and C26 view-memory behavior intact.
   A cache key must bind canonical manifest, exact metadata/object membership,
   schema/operation identity and verified bytes; where transport generations are
   available, bind those too. No cached hit may bypass the current reader's
   generation fencing, payload SHA256 verification or current authority checks.
2. Cache only successfully and completely validated immutable inputs. Validate
   incoming bytes/membership and current decoded budgets even on hits, and return
   isolated frames/metadata/objects so downstream mutations cannot poison cache.
   Preserve complete hidden-source namespace checks and fresh policy callbacks,
   including denied-source collisions and classification withdrawal/replacement.
   Failed/partial loads must never populate cache.
3. Enforce entry and retained-memory bounds, evict before retaining another
   entry, and coalesce concurrent misses. A bounded Arrow-backed immutable cache
   is an alternative if pandas retention/concurrency fails the workload budget.
   Explicitly test memory with multiple catalogue requests, not just one warm
   request, before selecting production limits.
4. Reduce cold semantic cost through bounded per-load taxonomy/assignment reuse
   and a precompiled primitive validator, preserving exact errors/row semantics.
   If cold operations still miss the existing15-second proxy gate, warm verified
   immutable inputs during the explicitly selected host startup *before* Ready.
   Warmup must use the activated store/registration and pure source validation;
   never manufacture an admin user, scientific approval or model call. Keep the
   existing startup CPU/health protocol and min0 billing boundary, and measure
   actual cold-start latency before claiming success.
5. Measure actual GCS-backed cold/warm discovery, directory/inspector and raw
   table paging. This local prototype still performs79snapshot reads; real SDK
   metadata/download round trips can dominate even after CPU reuse. Any verified
   byte reuse must check current generations and hash its cached bytes, without
   relaxing control/activation access. Do not raise the frontend deadline as
   evidence that the gate passed.

Required focused acceptance includes content/generation/metadata tampering after
warmup; removal/revocation/retirement/registration/activation changes; owner and
classification changes; hidden namespace collisions; returned-object/frame/attrs
mutation; decode and retained-byte bounds; eviction/reload; concurrent fills and
failed fills; raw/eligible/count/coverage/table output parity; unchanged C26 view
cache budget; and source-bound Linux/live GCS browser checks. No such production
cache implementation, security/concurrency suite or live gate is claimed here.

[Profile](local-profile.json), [prototype measurements](private-cache-prototype.json),
[private script hashes and attempt qualifications](provenance.json).
