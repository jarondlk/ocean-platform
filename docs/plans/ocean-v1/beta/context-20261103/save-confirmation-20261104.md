# Saved-context confirmation follow-up — 2026-11-04 JST

Revision `ocean-v1-beta-serving-00013-trn` serves 100% of beta traffic in
`ocean-v1-beta-20261101`, region `asia-northeast1`. Source
`c81a33b376b66ee6e5fdcaba4bd1b5139588b5b2` removes the redundant investigation
read from the mutation's 15-second confirmation window. A validated committed
reply clears the retry intent immediately. The existing selection effect then
revalidates context separately before exposing the next mutable context.
Uncertain responses retain the exact intent for an idempotent retry, and access
or selection transitions still prevent stale confirmations. No deadlines changed.

Cloud Build `54ff07f5-8475-4bd2-9192-9e0c7c2e4456` succeeded using the dedicated
Tokyo build identity, approved staging bucket and `CLOUD_LOGGING_ONLY`.
The immutable frontend image is
`context-frontend@sha256:a7f725cbce560e13fd555de8ef49392a4d0bfcc9e79b41721519a03839ca4868`.
The build's isolated nonroot, network-disabled image proof passed. All 141
focused frontend tests and both frontend typechecks passed with verified Node
22.23.4. Three regressions exercise committed confirmation, a stale reply after
an access transition, and retention of an uncertain request's original key.

The rollout first staged a Ready revision without traffic, compared its template
with the freshly read live service, and then promoted it. Only the frontend image
and generated client nonce changed. The API image remains
`snapshot-api@sha256:2d9a1ae220ccd7039702cef0dde7c934d609a0800ce5459d2ddf7501975e787d`;
the catalogue activation and context-mode settings remain in place. Identities,
secrets, SQL proxy, ingress, startup behavior and min0/max1 scaling are preserved.
This follow-up made no IAM, SQL, job, queue or legacy changes. Revision
`ocean-v1-beta-serving-00012-hxz` is the preceding traffic rollback target.
Public login returned 200; unauthenticated runtime returned 401.

In the signed-in browser, removing the existing CTD attachment from the private
verification investigation returned HTTP 200 in 9.980 seconds. The browser showed
“Saved to this private investigation,” then revalidated to zero attachments,
without asking for a retry. Reattaching the same CTD dataset reached the
15-second backend/proxy limit: HTTP 503 in 15.031 seconds. Subsequent reads and a
full browser reload showed exactly one available attachment. This verifies
persistence of the second change, not successful acknowledgement of that request.
The reload cleared the in-memory pending intent; do not reconstruct or blindly
replay it with a new key. The test investigation is left with its original single
attachment. No scientific source data was changed.

Backend latency remains an open acceptance issue. Investigation reads observed
on this revision included 7.012, 7.174 and 9.566 seconds, near or beyond the
frontend's existing 8-second read bound. Periodic context checks can therefore
still flicker or fail. Fix backend verification/read cost and measure cold and
warm behavior, concurrent refreshes, current-access denial and integrity checks
before claiming a reliable workflow or deploying ANEMONE/eDNA. Do not solve this
by increasing the existing deadlines or weakening catalogue verification.

The three-hour schedule remains paused. ANEMONE/eDNA remains gated, and model,
dispatch, queue and worker execution remain disabled. Existing beta cost/scale
limits and the notice threshold of ¥50,000/month remain in force.
