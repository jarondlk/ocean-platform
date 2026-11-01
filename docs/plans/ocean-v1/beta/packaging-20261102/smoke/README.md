# Actual image smoke harness — prepared 2026-11-02 JST

State: **prepared and statically checked; actual image execution not run here**.
The Mac has no Docker daemon. No pass is inferred from successful image builds.
The root operator may run the harness in a separately bounded Linux Cloud Build
after pulling the two explicit image digests. The script is Python standard
library only and needs a Docker CLI connected to that disposable build daemon.
It performs no SDK call, image pull, provisioning, secret access or deployment.

```sh
python3 deploy/gcp/beta/smoke/container_smoke.py \
  --frontend-image "$BETA_FRONTEND_DIGEST_URL" \
  --api-image "$BETA_API_DIGEST_URL" \
  --revision "$BETA_SOURCE_COMMIT" \
  --frontend-manifest-sha256 "$BETA_FRONTEND_MANIFEST_SHA256" \
  --api-manifest-sha256 "$BETA_API_MANIFEST_SHA256" \
  --output /workspace/container-smoke-result.json
```

All inputs are explicit: only the new beta registry's `frontend` and `api`
digest URLs are accepted. Mutable tags are refused. The source commit is a
full 40-character hash; each expected manifest SHA256 is the **file hash** of
that context's exact `source-manifest.json`, not its inner inventory identity.
The output must not exist. A nonzero exit or `status: failed` keeps acceptance
closed. Preserve the output and source-bound build receipt, including failures.

The harness checks actual image metadata for Linux amd64 and a non-root default
user. It runs the API image with its packaged Python to assert a non-root UID,
read and verify the embedded manifest, import `api.v1_host`, and confirm
`api.main` was not imported. It separately runs the image's default entry with
no credentials or target configuration and requires its guarded exit2 before
database configuration. No migration is selected or database is supplied.

It then starts the actual built frontend image with fixed synthetic settings
and exercises HTTP to `127.0.0.1:8080` **inside that container** using packaged
Node. It requires the beta Host `/login` page and linked generated CSS to return
200, a wrong Host to return403, and unauthenticated `/v1/runtime` to return401.
It does not submit the sign-in form or call Google. Both image manifests must
match their context-file hashes and the selected source commit.

Every container uses `--network=none`, no published port, a read-only root,
no capabilities, no new privileges, bounded CPU/memory/PIDs and an owned tmpfs.
No real credential is inherited from the host environment. Actual login
credentials are deliberately absent; synthetic settings only permit the
unprivileged login page to render. The probe is limited to120seconds, each HTTP
request to3seconds, with a bounded cleanup phase afterward. `finally` removes
only the three UUID-named containers created by this invocation and records
whether each was removed or already absent. A cleanup failure makes the receipt
fail and identifies the owned container for inspection.

Local preparation checked Python syntax, embedded API/Node probe syntax, Ruff
and fixed registry/digest input rejection. None of those checks is a runtime
image smoke pass. Even a later successful smoke proves packaging and these
unauthenticated boundaries only: real OAuth, Cloud Run ingress, Cloud SQL,
scientific services, queue/worker and the20 operational release gates remain
separate acceptance work.
