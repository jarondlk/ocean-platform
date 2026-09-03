# ANEMONE local canary — 2026-09-03

Status: acquisition, canonical storage, evidence/provenance, signed API access
and local recovery verified. Scientific acceptance and cloud rollout are not
complete. No production import, model call, cloud build, GCP mutation, merge or
release was performed during this canary.

## Authority and cost boundary

The user delegated the choice of one relevant sample, supplied a fresh download
credential and confirmed **JPY 20,000 per month for the entire project**, not
an additional pilot allowance. Keep the canary at 20 inventoried files and
64 MiB selected transfer; no run-wide expansion was performed.

GCP CLI authentication was reverified for `data-infra-infobio`. The live service
still reports `ocean-platform-v030-1bb38b8`. The data bucket has uniform access,
public-access prevention and versioning enabled. No ANEMONE job or secret
resource was found in the preflight inventory. The credential was entered via
a hidden prompt and retained only in the acquisition processes; it was not
written to the repository or Secret Manager.

The CLI cannot list billing-account budgets. The project billing console
required a separate passkey challenge, so current-month spend and live budget
settings are **not verified**. Earlier documentation records a JPY 10,000
project alert and smaller component controls; those are historical settings,
not evidence of the newly confirmed ceiling being configured. Do not raise
existing resource limits or execute paid work until posted spend/headroom and
component controls are checked. An ordinary budget alert is not a hard cap.
[Google budget documentation](https://docs.cloud.google.com/billing/docs/how-to/budgets)

## Scope and reproducible identities

The canary uses the sample in the user's original download example:
[2019KibanSRUN01 / 20171218T0103-KUM-Otomi-Surface](https://db.anemone.bio/dist/MiFish/ANEMONE/2019KibanS/2019KibanSRUN01/2019KibanSRUN01__20171218T0103-KUM-Otomi-Surface__MiFish/).
It is a workflow canary, not an Onagawa/CTD/SST overlap validation.

The public [ANEMONE DB home page](https://db.anemone.bio/) marks its data CC0
1.0. Keep source attribution, hashes and acquisition dates for research
reproducibility. The public notice is not verification of all account-specific
automated-access conditions; no unrestricted archive mirror is authorized.

| Record | ID |
| --- | --- |
| Application commit | `bfc8c0ac05a3f615301265c8acea8f3861753bcc` |
| Raw snapshot | `c57c669f0e87953cbbac70a0053f895bc8f6d391bc89ef9f14aa4b34c5ea5432` |
| Raw transport artifact | `fd6bdc41312b20dc343771136bfae6d96468da14b2fd20ac31b87a7ceabb11f0` |
| Normalization | `5efd1ae7b2a8dd66c37a012efaf24dd5bd88a6cbe467b3a61b1c5e1a22528f50` |
| Normalized transport artifact | `05fdd38cd44ce2b92049eac161b2da30f29e8cba15d692d6842115a42ad30fa6` |
| Sample | `fb62c79e7ddc4720bf17fec298c83315cdbf72e6604175142d296c377221bf0a` |
| Retrieval generation | `45087d89cca6241d20d3693ce33e3cad1c51d6759767c3403df1d2cbba849740` |
| Analysis | `c5345afa8b7bc672a71589efd188f5639bc7aa9813c17ca620bcbf3a9bf63d88` |
| Local provenance snapshot | `anemone-9421403477f84b9689aaa02749f95a53` |

## Checks performed

- Inventory: 13 files, no validation issues, 5 interpreted TSVs selected.
  Source transfer: 6,412 compressed bytes. FASTQ and images were not downloaded.
- Canonical import: 1 sample, 1 assay, 70 detections, 4 internal standards,
  13 source-file metadata records and 1 source snapshot. The exact dry-run
  rolled back to zero data rows. Replay inserted/updated/inactivated no rows.
- Fresh database setup needs `bootstrap_database.py`, not only Alembic. An
  initial rolled-back import identified missing legacy `anchor_event`; complete
  bootstrap resolved it and confirmed all 23 tables. No code workaround or
  production schema change was made.
- Independent standard-library CSV/XZ reconciliation checked every detection's
  sequence, read count, genus/species/family/order/class/phylum and reported
  copies/mL against PostgreSQL. Both methods have 35 rows and 9,635 reads.
- Materialization produced 2 documents; replay retained both unchanged with no
  embedding invalidation. PostgreSQL full-text matching returned both. Vector
  retrieval/embeddings were not exercised or fabricated.
- Both document citations and both emitted analysis-context citations resolve
  through a verified local provenance snapshot. Missing embeddings are explicit.
- Signed local mock-provider API checks: anonymous access rejected (401);
  viewers denied Data/Provenance/export (403); researcher/admin read, exact-result
  provenance and bundle export passed (200). Export preserved all 70 exclusions
  and the empty diversity table. These are API checks, not live OIDC/browser tests.
- The local backup restore test passed all 23 table counts, including 3
  synthetic role-check users, 70 detections and 2 retrieval documents. Its
  temporary restore database was removed. No user data outside the pilot was
  changed.
- The post-canary backend gate passed 586 tests (8 PostgreSQL-gated skips),
  76.75% coverage, Ruff and diff checks. The NLTK reachability assessment and
  three regression cases are recorded in `docs/SECURITY.md`.

## Scientific finding and release blocker

The provider metadata lacks the explicit classification keys supported by the
adapter (`sample_type`, `sample_category`, `control_type`). It remains
`sample_kind=unknown`, `is_control=null`; collection method/name/location are
not silently treated as proof that a sample is not a control.

The genus recipe uses both assignment methods and `environmental_only`. It
correctly produces **zero composition/diversity rows and 70 exclusions**.
Method comparison remains descriptive: 35 shared sequences, 25 exact
assignments and 10 conflicting assignments. This is not independent accuracy
validation, contamination clearance, organism abundance or biological absence.
No environmental observation profile was enabled.

Before completing the scientific pilot, obtain researcher-reviewed
sample/control classification backed by provider evidence. The current code
has no operator classification-override input: an accepted review requires a
small provenance-preserving normalization extension, not editing raw files or
manually updating canonical rows. Alternatively, select a provider sample with
explicit supported classification metadata after reviewing a new bounded scope.
Until then, this canary verifies lossless evidence and exclusion behavior, not
successful environmental biodiversity analysis or the six model-answer cases.

## Local evidence retained

Private local workspace: `/private/tmp/ocean-anemone-pilot.DxUnef`.
It contains immutable raw/normalized/retrieval/analysis objects, operation
reports, the explicit recipe, `verify_canary.py`, `local-verification.json`, and
the verified backup
`backups/20260903T074926Z-anemone-pilot-ocean_pilot.dump`.
Archive SHA-256: `18d93c59f7df74a0948ecb86546d4b9324d6d3d39d88d2d3e943e7e274ea3287`.
The disposable `ocean-anemone-pilot-check` container was stopped and removed
after successful backup/restore verification. Its database can be reconstructed
from the retained archive; the source and artifact directories were not removed.
No downloaded source file, secret, database archive or signed token is committed.
Temporary-directory evidence is not durable cloud retention; preserve it before
host cleanup if the pilot is to be resumed.

Remaining: classification review/normalization support, current spend and
component guardrails, secure cloud credential delivery, real object-store/job
checks, reviewed model answers, live authorization/browser checks, production
backup/rollback rehearsal, merge, deployment and release.
