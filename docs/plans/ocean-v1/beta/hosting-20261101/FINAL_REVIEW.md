# Final local checkpoint review — 2026-11-02 JST

This review reads the retained output and unchanged 97-file snapshot. It does
not rerun the completed suites, build, HTTP lifecycle or cloud operations.

The frontend and backend contracts agree: the frontend supplies a fresh
60-second HS256 token with issuer `ocean-v1-frontend`, the exact single audience
`ocean-v1-api`, Google subject and verified email. The independent backend
resolves provider/subject against its own current active account record and
returns database-derived roles and permissions. Browser tokens and cookies are
not forwarded to the sidecar. The frontend rechecks `/me` during session use;
the backend authorizes each proxied operation again.

Host/session boundaries are explicit: the public beta origin is fixed, the API
origin is loopback-only, callback redirects stay on the beta site, Auth.js uses
PKCE/state/nonce and encrypted host-only secure cookies, mutations require the
same Origin, and proxy routes/body/response sizes and deadlines are bounded.
The earlier ambient redirect-proxy and production SQLite escape findings are
closed in the current source. Neither a legacy login nor a production mock
fallback is introduced.

The new `RuntimeApp` fetcher is opt-in and reaches the actual runtime,
catalogue, investigation, evidence, answer and experiment clients. Its absent
case keeps their previous defaults. The root static TypeScript check excludes
the separately checked `hosting` tree. The new CI job installs both locks,
checks host dependencies, units, types, production packaging and the actual
standalone HTTP lifecycle. Existing jobs remain present. The nested `.gitignore`
negates the repository's broad `lib/` rule; the release operator must still
confirm those helper files are staged in the source checkpoint.

No additional blocker was confirmed for committing this **local read-only
checkpoint**. This is not a deployment security or scientific acceptance verdict.
The retained HTTP test uses a synthetic Google discovery response and API;
its callback is not executed at Google. The API has separate native PostgreSQL
evidence. There is no actual combined browser/OAuth/Cloud SQL/Cloud Run journey
in this receipt. Production ingress header preservation/rewriting, direct URL
isolation, credentials, independent user enrollment, reviewed scientific
provider composition, DNS/TLS, live cookies and capacity remain unverified.
The bare API factory correctly reports scientific services unavailable.
Dispatch stays closed; D26-07 and the 20 existing operational gates remain open.
