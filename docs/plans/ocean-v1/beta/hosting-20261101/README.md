# Independent v1 host: local checkpoint, 2026-11-01

The new `frontend-v1/hosting` entry builds an actual standalone Next server with
independent Google authentication, encrypted host-only sessions, current-account
checks and a bounded private API proxy. This receipt accepts the local host
checkpoint only. It does not establish a public beta or complete phase 1's full
integrated UI journeys, live authentication, service composition or deployment.

Run the read-only evidence check from the repository root:

```sh
.venv/bin/python docs/plans/ocean-v1/beta/hosting-20261101/verify.py
```

`accepted-commands.json` binds 97 source files by byte hash to
`sha256:7b90b4d172a8d845d01ad2fae58422100203b72680816d7b36b192b220b18772`.
The five host checks observed identical source before and after execution. The
recorded checkout is the parent commit; these new files were uncommitted when
checked. Their application identity is the explicit source hash, not an assertion
that a previous accepted Git commit contains this implementation. `receipt.json`
also pins the raw output artifacts. Original C26/C27 evidence stays immutable.
The final receipt was assembled on 2026-11-02 from these retained outputs after
the prior turn was interrupted. The source still matches all 97 recorded hashes;
no suite or stateful rehearsal was repeated. The five host exit codes are in
the original command record. Static-preview completion is evidenced by its TAP,
typecheck and build output and the previous owner's completion report; its
process exit codes were not separately captured in that record.

| Check | Observed result |
|---|---|
| Host unit/security/Auth.js/client bridge tests | 50 passed, zero failed/skipped |
| Actual standalone HTTP lifecycle | 1 passed, zero failed/skipped |
| Host typecheck and standalone production build | Passed |
| Host production dependency audit | Zero vulnerabilities |
| Existing static frontend tests | 1,051 passed, zero failed/skipped |
| Existing static typecheck and export build | Passed |

The exact host commands, in `frontend-v1/hosting`, are `npm test`,
`npm run typecheck`, `npm run build`, `npm run test:server`, and
`npm audit --omit=dev --audit-level=moderate`. Build includes
`node scripts/package-standalone.mjs`, which copies generated static assets to the
standalone package. The static-preview checks used `npm test`,
`npm run typecheck`, and `npm run build` in `frontend-v1`.

Both locked packages must be installed for hosted CI:

```sh
npm --prefix frontend-v1 ci --ignore-scripts
npm --prefix frontend-v1/hosting ci --ignore-scripts
```

The actual HTTP test starts its own loopback API fixture and the newly built
standalone Next server. It exercises multipart login through Auth.js to a Google
303 redirect with PKCE/state/nonce; encrypted session acceptance; a fresh signed
private API request; sibling Origin rejection; logout; and revoked-account
denial. Its test-only Google discovery transport blocks external network calls;
it does not follow the Google redirect or execute a real provider callback.
The current-account API is synthetic in this host test. Separate backend tests
must establish the actual independent database composition and role authority.
The owned child process and API listener close in the test's finalizer; no port
8000 listener remained after the captured run.

Unit tests invoke actual Auth.js core and real typed client serialization. The
RuntimeApp bridge test supplies isolated React scheduling/visual child doubles
to observe the dependency injection; it is not a full browser journey. Original
static preview behavior remains covered by the existing 1,051-test suite.

Two approved shared-source supersessions are recorded with previous/new hashes:
`src/runtime-app.tsx` gains an optional fetcher and propagates it to the actual
clients; absent opt-in retains original defaults. `tsconfig.json` excludes the
new independently checked hosting tree so static CI needs only its own lock.
No original receipt is retargeted to these later bytes. The remaining host
source is additive under `frontend-v1/hosting`.

The host is fixed to `https://beta.oceaninfobio.com` and an explicit private
loopback API sidecar. Production ingress must preserve exact Host, overwrite
untrusted forwarding headers, and use HTTPS/port 443. Independent OAuth client
enrollment, runtime secrets, operator-enrolled beta accounts, live callback and
cookie behavior, actual load-balancer/direct-URL isolation, whole UI/service
composition, queue/worker integration and release evidence remain required.
Saved reads/cancellation are the initial allowlist; new research, synthesis,
experiment dispatch and investigation writes stay closed. Missing snapshot and
services remain unavailable. This checkpoint neither clears D26-07 nor any of
the 20 existing release gates, and it authorizes no data acquisition or transfer.

See [host setup](../../../../../frontend-v1/hosting/README.md) and the
[production integration plan](../INTEGRATION_PLAN.md).
The [final read-only review](FINAL_REVIEW.md) qualifies this checkpoint's scope.
