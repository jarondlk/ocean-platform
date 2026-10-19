# Final C20 history pagination amendment

The original C20 acceptance and committed source fc46da3 remain historical.
An independent probe confirmed that a successful submit whose UUID is beyond
page1 disappears at the next list refresh, potentially removing the last active
run from the browser's polling predicate. This is a delivery blocker even if
fc46da3's original hosted suites pass.

The repair keeps at most25 recently acknowledged run IDs/bindings per conversation
in the current account/permission-bound memory store. History fetches their fresh
status when absent from loaded list pages and verifies the original binding before
merging events. Arbitrary off-page cache entries are not retained. Identity changes,
revocation, cancellation and navigation must still prevent late private data from
returning. Older acknowledged entries evicted from this bounded set remain available
through server history pagination. No private run data enters persistent storage.

The frontend delegate owns source, regressions and frontend-verification.json.
The independent reviewer owns the baseline probe and independent-review.json.
Root's create-only freeze_acceptance.py requires those results, verifies unchanged
backend/PG source and all protected files/prior1005 tracked evidence, and records
every intentional original46/167 source supersession. It writes a new source map
and local verification; original receipts are never rewritten.

Root then commits/pushes the amendment, preserves exact-source hosted logs here,
and invokes record_delivery.py with that explicit source commit. Final delivery
requires all four hosted jobs on the amended source. The original source run is
preserved separately at ../hosted-ci.json and cannot alone complete C20. C21's
separate final readiness helper follows this amendment only after final delivery
is committed/pushed. No application implementation of C21 starts during this repair.
