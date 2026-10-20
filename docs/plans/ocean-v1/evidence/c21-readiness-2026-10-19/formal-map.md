# C21 prerequisite source reconciliation

This preparation is bound to C20 source
`fc46da36aa27c203357a1b5874a02378ae089847` on `overhaul`.
It does not select or implement C21. C20 local acceptance is frozen, but its
exact-source hosted run 39207358123 and separate committed/pushed delivery record
must complete before root finalizes C21 readiness. `C20/delivery.json` is not yet
available when this preparation starts.

The formal dependency list is C05, C06, C07, C13, C19 and C20. The audit begins
with each dependency's original `verification.json` file map, validates its
aggregate, then follows every explicit later component source map through C20.
Each changed hash has a receipt-bound acceptance chain; an arbitrary current
checkout hash cannot explain a supersession. The final hash must match both the
working file and its exact bytes at the C20 source commit.

| Formal prerequisite | Original entries | Entries superseded later | Explanation |
|---|---:|---:|---|
| C05 | 19 | 4 | CI advances through C09/C12/C17/C19/C20; API main advances through C06/C07/C14–C17/C20; two retrieval/scope tests migrate under C06. |
| C06 | 16 | 1 | API main advances through C07/C14–C17/C20. The C06 provider completion contract remains accepted. |
| C07 | 16 | 1 | API main advances through C14–C17/C20. Safe serialization sources retain their accepted hashes. |
| C13 | 17 | 2 | The explicit method-alias amendment changes scientific catalogue inputs and its focused tests. Its final source map precedes C14; the original receipt remains immutable. |
| C19 | 13 | 3 | C20 intentionally supersedes config and the controller/budget modules for durable replay. The separately accepted C19 CI timeout amendment is also included in the global source sequence. |
| C20 | 46 | 0 | All local accepted feature/test/contract/harness files match the committed C20 source. Hosted delivery is still pending. |

These 127 original entries share paths; the receipt separately records the
deduplicated current map. Intermediate original and accepted source receipts are
both pinned. C13's `method-alias-amendment/accepted-source.json` and C19's
`ci-budget-amendment/accepted-source.json` are applied after their component's
original maps, rather than treating either original map as current forever.
Source selection is explicit and does not search for a receipt that happens to
match a changed file.

C05's delivered source is recorded in
`c06-readiness-2026-10-15/verification.json`; it has no separate `C05/delivery.json`.
C06 and C07 use their own delivery receipts. C13 uses its final alias-amended
source and C19 uses its final CI-budget-amended delivery source. The audit checks
successful source-bound hosted receipts, Git ancestry and the exact historic
source bytes for these five delivered prerequisites. C20 local acceptance and
all tested transitive paths are separately checked against the C20 source commit.
No previous create-only verifier is executed and no application tests are rerun.

Preservation checks use C20's existing start snapshot: 30 unrelated files,
7 real scientific artifacts, 2 serving files, 106 legacy frontend files and all
912 prior evidence files. The audit also derives a fresh baseline from every
evidence blob actually tracked at the C20 source commit, then compares its SHA256
with the working file. This protects newly delivered C20 evidence as well as the
older 912-file baseline; it does not silently adopt a modified working-tree
receipt as the preservation baseline. Unrelated local work remains untouched.

`audit_pending.py` is importable without side effects. Its default command creates
`pending-verification.json` exactly once, with state `pending-hosted-delivery`,
`ready_for_selection: false` and `component_selected: false`. Revalidation is
read-only:

```text
python3 docs/plans/ocean-v1/evidence/c21-readiness-2026-10-19/audit_pending.py --check pending-verification.json
```

After root verifies C20 hosted success and commits/pushes its delivery record,
root may import `collect_audit(require_delivery=True)` or run the script with
`--final` to create a separate `verification.json`. This requires C20's exact
source-bound successful hosted receipt, unchanged accepted/tested files and
protected evidence, a separate Git checkpoint containing `C20/delivery.json`,
and HEAD ancestry in the locally recorded `origin/overhaul`. The script performs
no network fetch; root's delivery/push evidence remains authoritative. Even a
final receipt does not select C21, and the pending receipt is never rewritten.

Synthetic local implementation requires no live provider or cloud target.
Paid/live generation, actual data transfer, real scientific review, independent
v1 infrastructure configuration and deployment retain their separately documented
authorization and evidence gates. `preparation.md` records C21's implementation
boundaries and remains unchanged by this audit.
