# Beta frontend container preparation

The additive `deploy/gcp/beta/frontend` package builds the independent Next host,
then runs its standalone output as the image's unprivileged `node` user. Port8080
is the sole ingress. The Node22 official Linux/amd64 base digest is recorded in
`base-image-readback.json`; runtime and builder use the same immutable image.
No OAuth value, session secret, database URL or generated local build is copied.

`prepare_context.py` requires a full committed source revision and a new output
directory. It resolves local imports from the actual host app/lib entry graph,
reads bytes from Git objects and exports only that source, both dependency locks,
the exact committed Dockerfile and its manifest. Synthetic preview entry/data,
tests, fixtures, legacy frontend entry/config, local `node_modules` and `.next`
are excluded. The one shared `frontend/lib/csv.ts` is an existing pure formula-safe
serialization helper; it is explicitly permitted and pinned, with no legacy host
or package included. The first attempted closure correctly stopped at that shared
dependency before creating an output; the explicit allowlist now accounts for it.

```sh
.venv/bin/python deploy/gcp/beta/frontend/prepare_context.py \
  --revision FULL_COMMITTED_REVISION --output /private/tmp/NEW_OWNED_CONTEXT
```

This is container preparation, not a successful image build or deployment.
An actual bounded Cloud Build must compile this clean context on Linux, retain
the immutable image digest and test the produced container before deployment.
The previously accepted local host checks apply to the source app, not this new
container. Runtime settings remain exactly those in the host README. Real OAuth,
secrets, enrolled beta accounts, private DB/API, load-balancer header behavior,
probes, direct-URL isolation, DNS/TLS and live release gates remain pending.
