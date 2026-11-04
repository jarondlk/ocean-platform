# Context reference verification follow-up — 2026-11-04 JST

The API change in `57dde148ecf94e2759e71018042f9a1c10c70662` checks all catalogue
attachments and pins against one complete verified node view per resolution
stage. Previously each stage loaded an overview and opened every referenced
object separately. Investigation `get` also redundantly loaded the overview
before its context resolution. Artifact resolution is unchanged.

The internal bounded membership operation uses the same current resolver,
scope, node validation, collision and ancestry checks as ordinary catalogue
opens without details. It adds no cache or public endpoint. All four existing
prepare/apply/commit/response resolution stages remain; SQL owner checks,
retention registration, lifecycle checks and source integrity verification are
preserved. Neither the 8-second frontend read bound nor the 15-second mutation
and proxy deadlines changed.

The two focused Python runs passed 216 and 224 tests (with overlapping
materialization checks), covering current ownership/policy withdrawal, corrupt
inputs, uncertain writes, historical context and host execution denial. A new
regression checks that a context with an attachment and a pin materializes one
view in each of the four mutation stages and one for a subsequent get, then
denies the withdrawn attachment on the next read. All 34 source-package boundary
checks passed. Local Python was 3.13; the isolated image proof used the pinned
production runtime.

Cloud Build `f97c5e8e-ff1c-4684-9aec-d70afcd9e8ee` succeeded in Tokyo with the
approved account, staging bucket and `CLOUD_LOGGING_ONLY`. Its source-only
14-file context contains the existing opaque activation binding, no scientific
rows or credentials. The API image is
`snapshot-api@sha256:f72ed2a8c95cf65496e9593cf790a6bef9143ab34f55710a17bd350d022c1e37`.
The nonroot, network-disabled proof verified all nine overlaid modules and the
existing activation `464b018099db5975c5ba74ded879e0af5080ad8c4f29541cbaa77397d1af5001`.

Revision `ocean-v1-beta-serving-00014-xzr` was staged Ready without traffic, then
promoted to 100%. Its service template differs only in API image and generated
client nonce. An extra prepromotion assertion comparing the resolved revision
with the service template failed because Cloud Run resolves the SQL-proxy
manifest index to its platform digest. The shell did not stop on that assertion
and continued promotion. Subsequent commands were changed to stop on errors;
readback of both old and new resolved revision specs confirmed that only the
API image changed. The SQL proxy, frontend, identity, secrets, ingress, startup,
context flags and min0/max1 settings are identical. Revision `00013-trn` is the
preceding traffic rollback target. Login returned 200 and unauthenticated
runtime returned 401. There were no new IAM, SQL, job, queue or legacy changes.

In the signed-in browser, the existing private CTD verification investigation
loaded with its single available attachment. Removing that attachment returned
200 in 8.286 seconds, and reattaching it returned 200 in 8.887 seconds. Both
changes showed the saved confirmation and their revalidated attachment counts
without a retry prompt. The prior revision's comparable reattachment returned
503 at 15.031 seconds after persistence. Eight sampled investigation gets on
the new revision returned 200 in 1.504–3.472 seconds. These are live request
samples, not percentile, concurrency or cold-start acceptance claims.
A full browser reload retained exactly one available CTD attachment in the
same investigation. Reopening its existing saved conversation showed the same
single attachment and no submitted activity; execution remained unavailable.

The three-hour schedule remains paused. CTD, metagenome and MUR SST remain
available, with their existing scientific qualifications. ANEMONE/eDNA stays
gated on its separate production latency/integrity/current-access acceptance;
this context optimization does not qualify its raw data path. Model/dispatch/
queue/worker execution remains disabled, and the ¥50,000/month notice threshold
is unchanged.
