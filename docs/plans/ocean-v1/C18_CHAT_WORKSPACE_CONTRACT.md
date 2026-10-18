# C18 Chat and Workspace contract

The separate v1 Research destination uses the actual C17 private API and C16
catalogue browser. P00 fixtures remain confined to explicit prototype mode.
Default-off runtime readiness requires the shell/catalogue/browser/investigation
flags, actual services sharing the same catalogue instance and site, and current
`chat:use` plus `data:read`. This enables context management, not execution.

`src/investigation-service.ts` implements all fourteen bounded POST operations,
strict wire DTOs, current access failures, cancellation and exact mutation replay.
A lost acknowledgement retains the original idempotency key/body; another write
in that slot waits for recovery. Mutation replay may return an original revision,
so the host re-reads the current head before displaying it. Requests and selected
views have bounded deadlines and stale selection responses cannot repopulate UI.

`src/research-state.ts` restores investigation/conversation, Workspace tab and
mobile pane from canonical URLs. Private draft/pending-operation memory binds to
verified account and permission revision. It survives ordinary navigation and
same-account access refresh; identity changes or denial clear it. Browser reload
restores C17 metadata and context but intentionally loses volatile draft/activity.
C20/C21 will supply durable history. Chats share context, not narrative evidence.

Opening, browsing or staging a catalogue object never mutates C17. Attach adds
context; Pin restricts it. Explicit removal creates another immutable revision.
Source scope edits cover all four accepted source families and filters. Cross-chat
changes are visible. Submit re-reads C17 metadata/context and conversation and
requires review if the five-field binding changed. C20 must still provide
server-authoritative admission; the UI check is not that guarantee.

Refresh requires an explicit eligible new snapshot and name. C17 creates a new
investigation with predecessor IDs and unresolved selections. The original stays
available, no conversation narrative is copied, and unavailable context disables
submission. The UI offers an explicit route to the original investigation.

`src/research-run-contract.ts` defines submit/status/events/cancel/clarify/continue.
Every result retains investigation ID, conversation ID, immutable revision ID,
snapshot ID and payload SHA256, plus the frozen scope/attachments/pins. Catalogue
references bind to the current snapshot; trusted artifact references may retain a
different original snapshot. Cursor-monotonic public activity excludes private
model reasoning. Running, clarification, completed, partial, failed and cancelled
states, active elapsed time and linked continuation are distinct. Submitted
context never changes when the current investigation head changes.

RuntimeApp accepts an explicitly injected trusted transport, but the production
entry supplies none and never imports a development fixture. C20 owns production
execution/activation and C21 owns final answers and retained evidence. Synthetic
citation examples show their original binding, authority and unavailable artifact
status. Experiments remain unavailable until their owning components integrate.

Desktop has investigation navigation, Chat and keyboard-resizable Workspace;
narrow screens use accessible Chat/Workspace tabs and a collapsible private
navigation. Workspace sections use arrow/Home/End keyboard navigation. Essential
scope and pending recovery remain accessible in EN/JA and light/dark themes.
Spoken screen-reader use has not been claimed.

For isolated development acceptance, build `frontend-v1`, create a fresh JSON
control file under `/private/tmp` with `actor: owner`, an explicit revision and
empty `blocked_by_snapshot`, then launch the evidence/C18/serve_research_qa.py
helper with `--state-file` and a NEW `--observations` path. Explicit environment:
`DEPLOYMENT_ENV=test AUTH_MODE=disabled ENABLE_MOCK_LOGIN=false
PERSIST_LOCAL_CHAT=false ENABLE_V1_SHELL=true ENABLE_V1_CATALOGUE=true
ENABLE_V1_CATALOGUE_BROWSER=true ENABLE_V1_INVESTIGATIONS=true
DATABASE_URL=postgresql://unused:unused@127.0.0.1:1/ocean_c18_unused
MODEL_PROVIDER=ollama OLLAMA_BASE_URL=http://127.0.0.1:1`.
It creates and removes only its own temporary SQLite database and sealed synthetic
sources. Run `node frontend-v1/node_modules/next/dist/bin/next dev
frontend-v1/development/c18 --hostname 127.0.0.1 --port 3102` separately. Its banner
and outcome controls identify synthetic execution; API rewrites target only3101.
Stop both processes, preserve observations and remove no unrelated resources.
This is no real identity, scientific approval, provider, cloud or deployment gate.
