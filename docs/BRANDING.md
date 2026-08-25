# OCEAN Platform branding

This document is the canonical naming contract for the application and its
operational identifiers.

## Canonical identity

- Product name: **OCEAN Platform**
- Expanded name: **Ocean Coastal Ecosystem Archive Nexus (OCEAN)**
- Repository slug: `ocean-platform`
- Short operational prefix: `ocean`
- API title: `OCEAN Platform API`
- Frontend package: `ocean-platform-frontend`

OCEAN is a recursive acronym: the first letter expands to "Ocean" while the
complete acronym names the platform.

## Naming rules

Use **OCEAN Platform** in navigation, authentication screens, browser metadata,
documentation titles, release names, and user-facing descriptions. Use the
expanded name on the login screen, README introduction, and other places where
a reader first encounters the project.

Use the lowercase `ocean` prefix for new internal and infrastructure
identifiers. Prefer `ocean-platform` when an identifier represents the entire
application and a focused suffix such as `ocean-pipeline` for a component.

## Names that remain Onagawa

`Onagawa` remains correct when it describes scientific geography or source
data, including:

- Onagawa Bay and station code `O`;
- `ONAGAWA_LAT` and `ONAGAWA_LON`;
- `CTD_Onagawa.tsv`;
- `onagawa_sst_subset/` and `onagawa_sst_*.nc` source files;
- scientific prompts, evaluation questions, and reference answers about the
  Onagawa monitoring programme.

Historical release records also retain the exact names of the resources that
produced them. A runbook must not rewrite an old Cloud Run revision, Cloud Run
Job execution, image path, backup archive, or digest merely to match the new
brand.

## Compatibility policy

- Browser preferences migrate from `onagawa-app-preferences` to
  `ocean-platform-preferences` on first load.
- New chat records use `ocean-chat-v2`; existing `onagawa-chat-v1` records stay
  unchanged as provenance evidence.
- The legacy mock-login UUID namespace remains stable so local test identities
  are not duplicated by the rebrand.
- New default internal JWT values are `ocean-platform-frontend` and
  `ocean-platform-api`; environment variables remain the deployment control
  point during rollout.
- Release `v0.2.1` completed the GCP data-plane transition. Active application
  manifests and identities use the target names below. Legacy resources keep
  their historical IDs only as private, deletion-protected rollback assets.

## Target component names

| Component | Target identifier |
| --- | --- |
| GitHub repository | `jarondlk/ocean-platform` |
| Cloud Run service | `ocean-platform` |
| Artifact Registry repository | `ocean-platform` |
| Application service account | `ocean-platform` |
| Job service account | `ocean-jobs` |
| Cloud SQL instance | `ocean-postgres` |
| PostgreSQL database | `ocean_platform` |
| PostgreSQL application user | `ocean_app` |
| Migration job | `ocean-migrate` |
| Pipeline job | `ocean-pipeline` |
| Embedding job | `ocean-embedding` |
| Evaluation job | `ocean-evaluation` |
| Cloud Storage bucket | `data-infra-infobio-ocean-data` |

All target identifiers are active as of release `v0.2.1`. The former service
is private and the former Cloud SQL instance is stopped; do not reuse legacy
identifiers for new components.
