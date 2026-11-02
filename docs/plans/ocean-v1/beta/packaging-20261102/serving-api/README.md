# Configuration-only beta API image — 2026-11-02 JST

The new `deploy/gcp/beta/serving-api` package addresses the missing regular API
configuration file. It derives only from accepted API digest
`sha256:f2e73ca98ba915e29a4dd7dc429e34a165475faa7f9000bc8cefaa10e5a6ee4f`,
whose embedded API source revision remains
`7924a28e919b1fb751890c694f7b1f9b26b104ff`.

Its Dockerfile copies the canonical non-secret host JSON to
`/opt/ocean/beta-host-config.json`, owned by root with mode0444, and sets only
`OCEAN_V1_HOST_CONFIG` to that path. A separate root-owned0444
`/opt/ocean/serving-manifest.json` records the new layer's committed source,
configuration hash and exact base identity. It does not replace the base API's
`source-manifest.json`; the JSON revision must match that preserved base manifest.

The base's UID/GID10001, ENTRYPOINT, CMD, application bytes, loopback8000
listener and execution fences are inherited. There is no RUN, USER, command,
health or security override, startup writer, fifth runtime secret or new IAM
grant. Config contains only fixed project/site/source/host/provider metadata;
no password, DSN, OAuth, token, session key or scientific data is included.
The earlier hosting proposal and its17inspected inputs remain unchanged.

## Committed context preparation

After root reviews and checkpoints these files, use the **new full commit**:

```sh
.venv/bin/python deploy/gcp/beta/serving-api/prepare_context.py \
  --revision NEW_FULL_COMMITTED_SOURCE_SHA \
  --api-revision 7924a28e919b1fb751890c694f7b1f9b26b104ff \
  --api-image asia-northeast1-docker.pkg.dev/ocean-v1-beta-20261101/ocean-v1-beta/api@sha256:f2e73ca98ba915e29a4dd7dc429e34a165475faa7f9000bc8cefaa10e5a6ee4f \
  --output /private/tmp/NEW_OWNED_SERVING_API_CONTEXT
```

The preparer requires that exact base image/source, a distinct committed
descendant revision, regular Git sources and matching working bytes. It rejects
alternate/legacy configuration, duplicate/extra/noncanonical JSON and any
Dockerfile instruction outside the four reviewed instructions. All validation
precedes output creation. The output is exactly `Dockerfile`,
`api-host-config.json` and `serving-manifest.json`; stdout reports their manifest
and configuration hashes. No checkout-wide or generated context is copied.

Pre-commit checks pass for the canonical files and negative guards, including
the refusal to export these uncommitted files from an older commit. Successful
committed export is deliberately pending root's checkpoint. The checks make no
Git commit, cloud call, database connection or image/native claim.

## Required actual image proof

Root must build this clean context on Linux with Docker COPY `--chmod` support,
retain its immutable image digest, and verify the produced image:

- Image/runtime user remains10001:10001; base ENTRYPOINT/CMD and listener behavior
  are unchanged.
- `lstat` observes a regular, non-symlink configuration file with UID/GID0:0 and
  mode0444; its byte hash and parsed content match the reviewed config.
- The unprivileged runtime can read the JSON but cannot open it for writing;
  the base source manifest still names7924a28 and the new layer manifest names
  the actual configuration-package commit.
- The inherited entry consumes this path and still fails closed without required
  independent runtime/SQL inputs. Real database/schema and whole-instance startup
  checks remain distinct from this file proof.

Do not submit the old hosting JSON unchanged: it explicitly overrides
`OCEAN_V1_HOST_CONFIG` with a `/tmp` path. A separate owning renderer amendment
must select the **new derived digest** and remove that old override or set the
new `/opt/ocean/beta-host-config.json` path. Preserve the original hosting
proposal/receipts; do not retarget them to new bytes.

This checkpoint performs no build, deployment, OAuth callback, account enrollment
or scientific/provider integration. Those actual gates remain open.

```sh
.venv/bin/python docs/plans/ocean-v1/beta/packaging-20261102/serving-api/verify.py
```

The verifier checks pinned source/artifact bytes and the recorded pure checks
without replaying them or accessing GCP. `checks.py` is the separate pure-check
harness if source changes justify another capture.
