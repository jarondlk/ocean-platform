# C15 browser verification — 2026-10-17 JST

Observed through the Codex in-app browser against the current static v1 build
and the actual C15 runtime route/auth middleware. `serve_shell_qa.py` supplies an
explicit server-side TEST identity, unused loopback database configuration and
no providers. This proves local shell behavior; it does not prove real OIDC,
scientific publication approval, a deployed target or production capacity.

## Responsive and keyboard observations

- Settings: English/Japanese × light/dark × 1440×900, 900×1024 and 390×844.
  All twelve measured document widths equal their viewport widths. Language,
  theme and essential controls remained readable. Research desktop, Japanese
  narrow/tablet Workspace and catalogue desktop/narrow panels were also inspected.
- The desktop keyboard separator changes the right panel width from 390 to370.
  Narrow panels expose tabs and focusable tabpanels; ArrowRight selects the
  adjacent Workspace/Inspector tab. The catalogue tablist announces its actual
  destination after the final polish.
- Navigation drawer and account dialog trap Shift-Tab/Tab, dismiss with Escape
  and restore their opener's focus. Account fields are read-only. Settings expose
  language/theme only. Back/Forward preserves requested routes and preferences.
- No console errors or warnings were observed. Screenshots were inspected in
  the browser tool output; no saved screenshot files are claimed by this receipt.

## Identity, failures and preview isolation

- Researcher: catalogue/tools visible, Administration absent; direct `/admin`
  retains the URL and shows access restricted. Administrator: Administration
  visible and opens an honest unavailable destination, without simulated admin
  records or mutations.
- Explicit synthetic preview preserves the already-saved P00 Administrator /
  Internal-account state, its sample badge and eleven synthetic datasets.
  Switching the same browser origin to a server-supplied Viewer produces Viewer
  / Research-account identity, hides catalogue/tools/admin links and denies the
  direct catalogue route. No saved preview state was edited or reset.
- Refresh access after a server-side401 removes the prior identity and navigation
  and asks for v1 sign-in. Missing configuration, a failing configuration callback
  and a malformed bootstrap show unavailable with Retry, never synthetic data.
- A13-second runtime delay first shows loading without identity, then the10-second
  deadline shows connection failure. The late response does not restore identity.
  Replacing the harness with a ready service and Retry recovers normally.
- Invalid runtime-mode configuration shows a bilingual configuration error with
  Retry; the service shell and synthetic preview are both absent. Retry after a
  valid mode recovers to the configured service. The inherited P00 metadata title
  was corrected to the neutral OCEAN Platform title and the final build passed.
- P00 state compiles into a distinct lazy chunk. Inspected service document script
  elements exclude that chunk. This observation is not a full network trace.

All owned disposable servers were stopped, the viewport override reset, and the
temporary browser tab closed. No real authentication, database, legacy API,
data transfer, provider call or cloud deployment was used.
