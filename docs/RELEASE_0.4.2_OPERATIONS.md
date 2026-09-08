# v0.4.2 deployment record

Verified 2026-09-08 JST. This records the immutable release and Cloud Run
rollout; it does not create or apply a scientific classification decision.

## Source and release

- GitHub PR [#56](https://github.com/jarondlk/ocean-platform/pull/56) was
  reviewed and merged into `main`.
- GitHub release [v0.4.2](https://github.com/jarondlk/ocean-platform/releases/tag/v0.4.2)
  was published from merged commit `2731d464ae11a2064359d2696db3f2eab523c2ac`.
- Cloud Build `fd2a5970-692f-424e-a721-0144e1e2e005` completed successfully in
  8m54s and produced immutable API and frontend images tagged with that build
  ID in Artifact Registry `asia-northeast1-docker.pkg.dev/data-infra-infobio/ocean-platform`.

## Migration and service rollout

- Cloud Run Job `ocean-migrate-w9z9s` completed successfully before rollout;
  schema head remains `20260905_0011`.
- Cloud Run service `ocean-platform` now serves revision
  `ocean-platform-00013-djj` at 100% traffic.
- The frontend uses `AUTH_URL=https://oceaninfobio.com`.
- The API uses `CORS_ORIGINS=https://oceaninfobio.com`.
- The fallback Cloud Run URL and Google OAuth callback remain documented for
  reviewed rollback.

## Live checks

- `https://oceaninfobio.com/` redirects unauthenticated users to `/login`.
- `/login`, `/api/auth/session`, and `/manifest.webmanifest` returned HTTP 200.
- No scientific review, approval, application, rollback, or ANEMONE download
  was run by this deployment. The retained pilot remains `unknown`.

## Remaining acceptance

Researcher-specific role acceptance, suspension, and uninvited-account denial
still require the corresponding test identities. This is a scientific and
authorization acceptance gap, not a Cloud Run rollout failure.

Billing controls were not changed. The user-confirmed project ceiling remains
JPY 20,000 per month.
