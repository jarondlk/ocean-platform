# Cloud Run transport adapter preparation

The actual beta edge diagnostic found the canonical Host and all three trusted
X-Forwarded fields correct, while Cloud Run added RFC Forwarded after the load
balancer removed it. The accepted host middleware refuses that redundant field.
This package changes deployment transport only: it derives from the exact
accepted frontend image and preloads a finite Node HTTP request adapter before
the unchanged Next server. It has no credentials, network client, request logger,
HTTP response, authentication decision or application source patch.

Normalization requires the exact serving service, production/required-auth beta
environment and exactly one raw canonical Host, X-Forwarded-Host,
X-Forwarded-Proto=https and X-Forwarded-Port=443. It removes only RFC Forwarded
from Node's parsed, distinct and raw header views. Every other raw field, cookie,
Origin, authorization value, method, path and body remains unchanged. Missing,
duplicate, ambiguous, wrong or oversized transport inventories are unchanged and
remain subject to the existing application guards. Other deployments fail before
application startup with a fixed error.

The focused actual Node HTTP fixture passed 14/14 checks on the final source.
It uses only a child-owned ephemeral loopback listener and synthetic values; no
Google, GCP, database or actual image was contacted. The first two attempts are
retained: the initial adapter shortened rawHeaders before Node materialized its
lazy headersDistinct cache, causing a getter exception. The second attempt only
added the missing child diagnostic to the harness. The final adapter materializes
that public view before rewriting rawHeaders, then deletes only its Forwarded
entry. The failed adapter is retained as source-before-header-view.cjs with its
original reviewed hash. No accepted application checks were repeated.

After this package is committed, prepare a source-only context with:

```sh
.venv/bin/python deploy/gcp/beta/serving-frontend/prepare_context.py --revision FULL_COMMIT_SHA --output /tmp/NEW_CONTEXT_DIRECTORY
```

The packager requires the three package files to equal that explicit commit. It
emits the Dockerfile, adapter and a source manifest; no application rebuild is
needed. The Dockerfile copies root-owned read-only adapter/manifest files, then
restores the accepted base USER node and inherits its workdir/entrypoint.

Deployment acceptance remains external to this local preparation: build the
derived image, verify its digest, nonroot user, root-owned 0444 files and manifest,
then inspect the actual effective Cloud Run image and argv. **Clear the temporary
diagnostic command and args**, so the image CMD starts `node --require
/opt/ocean/serving-frontend-adapter.cjs hosting/server.js`. Preserve required app
auth, canonical edge header actions, internal-LB ingress, disabled default URI
and all existing secret bindings. Verify real edge `/login` 200 and unauthenticated
runtime refusal before publishing DNS. A login-page milestone does not accept a
real Google callback, enrolled account, backend integration or system release.

`verify.py` is byte-only and does not repeat HTTP, application suites or cloud work.
