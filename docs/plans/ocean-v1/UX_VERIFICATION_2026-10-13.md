# P00 usability and accessibility verification — 2026-10-13

Result: **pass for the reviewed prototype journeys after fixes**. P00 remains
Ready for review. This is an expert/heuristic and browser verification against
established industry guidance; it is not a full WCAG conformance certification,
a representative-user study, or acceptance of real backend/security/scientific services.

## Method and standards

Two independent source reviews supplemented direct browser walkthroughs. Reference
criteria came from [WCAG 2.2](https://www.w3.org/TR/WCAG22/) and
[Nielsen's ten usability heuristics](https://www.nngroup.com/articles/ten-usability-heuristics/).
Tests used the actual static localhost build, existing synthetic investigations,
English/Japanese, light/dark, desktop 1440×900 and narrow 320×800/390×844 viewports.
Temporary viewport overrides were reset afterward.

Read-only DOM measurements used computed foreground/background colors (sRGB
relative luminance and ancestor-background composition), control bounding boxes,
visibility/inert status and document width. They supplement manual semantics,
keyboard and visual review; they are not axe or a complete conformance scanner.
Disabled text and SVG text were excluded from this text scan. Chart text/meaning
and equivalent tables were inspected separately. [Raw measurements](mockups/p00/ux-verification-2026-10-13/measurements.json)
contain 17 final recorded checks: zero sampled text-contrast failures, zero
undersized control bounds, and no document-width overflow in those cases.

## Findings fixed and rechecked

| Area | Issue found | Resolution and evidence |
|---|---|---|
| Text contrast | Original light blue ink was 4.45:1 on white and 3.92:1 on selected backgrounds. | Darker functional blue is 5.41:1 / 4.77:1; sky/baby-blue accents remain. Muted text and placeholder opacity were corrected. Both-theme rendered scans pass. |
| Control visibility | Pale input boundaries and tiny text made controls harder to recognize. | Input boundary contrast is at least 3.18:1 on declared light surfaces, and 4.23:1 in dark mode. Metadata has an 11px design floor; this is a readability choice, not a WCAG font-size threshold. |
| Targets | Small text actions, diagnostic summaries and a 6px resize handle were awkward. | Minimum 24px control bounds; 24px resize hit area with a thin visible handle; larger labelled radio/checkbox targets. Measured cases pass. Primary research actions are larger. |
| Focus | Admin panel suppressed its outline; navigation could remove the focused trigger. | 2px visible panel focus, destination focus/scroll reset without moving focus during search or tab selection. Browser checked panel focus in the viewport. |
| Viewport focus | Off-screen map focus could scroll the document and clip the top navigation. | Screen-reader-only anchors and document overflow were corrected. Recheck: document height equals viewport, root scroll 0, navigation top 0 after map focus. |
| Dialogs | Changing Account→Preview controls could lose focus; inert background risked losing the original trigger. | Trigger captured before opening; content changes refocus inside the dialog; Escape and final focus return verified. |
| Mobile drawer | Covered main controls could remain in keyboard order. | Focus enters drawer; background is inert; Tab/Shift+Tab wrap; Escape returns focus to Menu. Direct keyboard check passed. |
| Status | Completion/clarification/cancellation/error could clear the live status region. | Stable atomic status announces the actual latest run state without elapsed-time spam. Completed sample run exposes “Complete within scope.” |
| Map names | Visible CTD/SST labels were omitted from accessible names. | Accessible names now start with visible short labels and add full titles/type. Equivalent record/link lists remain. |
| Recovery | Undo expired after nine seconds; long Japanese toasts could overflow. | Undo notices stay until dismissed; messages/actions can wrap and controls cannot shrink below minimum targets. |
| Admin jobs | Scheduling under an error/status filter hid the new job/log. | Successful scheduling clears filter, selects the new ID and announces it. Browser reproduced retry from Needs attention and verified the new queued job/log is visible. |
| Admin settings | Record demo check silently replaced an unsaved settings draft. | Reconciliation follows committed value changes, not cloned object references. Browser verified draft 60 survives the check and Discard restores saved 45; regression test passes. |
| Mobile headings | Japanese Feedback/catalogue headings and snapshot text were cramped. | Full-width support/catalogue headings and a readable snapshot selector; 320px Japanese views rechecked with no document overflow. |

Contrast, target and focus checks correspond to
[1.4.3](https://www.w3.org/WAI/WCAG22/Understanding/contrast-minimum.html),
[1.4.11](https://www.w3.org/WAI/WCAG22/Understanding/non-text-contrast.html),
[2.5.8](https://www.w3.org/WAI/WCAG22/Understanding/target-size-minimum.html),
[2.4.7](https://www.w3.org/WAI/WCAG22/Understanding/focus-visible.html) and
[2.4.11](https://www.w3.org/WAI/WCAG22/Understanding/focus-not-obscured-minimum.html).
Reflow, names, status and modal behavior were reviewed with
[1.4.10](https://www.w3.org/WAI/WCAG22/Understanding/reflow.html),
[2.5.3](https://www.w3.org/WAI/WCAG22/Understanding/label-in-name.html),
[4.1.3](https://www.w3.org/WAI/WCAG22/Understanding/status-messages.html) and
[WAI dialog guidance](https://www.w3.org/WAI/ARIA/apg/patterns/dialog-modal/).
Charts/tables keep bounded horizontal scrolling where their two-dimensional
meaning requires it. The document itself does not overflow in measured narrow views.

## Human usability review

| Heuristic | Observed behavior |
|---|---|
| System status | Run state, snapshot/revision, local preview and saved feedback are visible. |
| Familiar meaning | Research, Context Catalog, Conversations and Workspace expose the research task; scientific units/limitations remain explicit. |
| User control | Cancel/retry/continue, undo, scope review and snapshot branching retain the original evidence. |
| Consistency | Shared tabs, dialogs, controls, library icons and account labels work across the new pages. |
| Error prevention | Scope restriction and proposal approval ask for review; edits invalidate approval; demo admin cannot lock itself out. |
| Recognition | Catalogue roots/source counts, breadcrumbs, context cards and receipts reduce memory burden. |
| Efficiency | Search/paging, deep links, keyboard tabs, resizable workspace and narrow alternatives are available. |
| Minimal design | Restrained accents and short action labels keep data and research prominent. |
| Recovery | Empty/zero/unknown/unavailable/revoked/partial/error states are distinct and offer appropriate recovery. |
| Contextual help | Qualifications, code/resource limits and preview boundaries appear where relevant; About/Feedback are easy to find. |

Native labels, semantic tabs/tables, live status and accessible-name continuity were
inspected through DOM/AX and keyboard behavior. A formal VoiceOver/NVDA test,
200% browser text/zoom and custom text-spacing audit, forced-colors review and
representative researcher usability testing remain release validation work. Reduced-
motion CSS is present; OS preferences were not changed. These limits prevent an
unsupported claim of full accessibility certification or measured user-performance gains.

## Technical checks and artifacts

- Typecheck and static build pass; 27/27 focused tests pass, including the new
  unsaved-settings regression. No captured browser warnings/errors.
- Existing drafts survived reload/navigation. Prior P00 evidence records complete
  CSV/JSON/Markdown/SVG downloads and preservation of experimental authority.
- Legacy frontend/backend remain unchanged. Real roles, jobs, data and analysis
  are absent from this local synthetic prototype.
- Five current screenshots: [Research](mockups/p00/ux-verification-2026-10-13/01-research-workspace.jpg),
  [Catalogue overview](mockups/p00/ux-verification-2026-10-13/02-catalogue-overview.jpg),
  [Relationship map](mockups/p00/ux-verification-2026-10-13/03-relationship-map.jpg),
  [Administration](mockups/p00/ux-verification-2026-10-13/04-administration.jpg), and
  [Japanese mobile](mockups/p00/ux-verification-2026-10-13/05-mobile-japanese-dark.jpg).

## Architecture comparison and Gmail draft

The legacy general retrieval path caps k at 25 (api/schemas.py:311), but also
supports exact aggregates and published workflow routes (api/main.py:5661).
The draft explicitly preserves that distinction. New local interactions are
implemented; full authorized inventory, durable server execution, containment
and independent v1 infrastructure remain planned gates, and speed/accuracy/cost
improvements are not claimed as measured.

At the user's request, created an unsent Gmail draft titled **OCEAN v1.0.0
Architecture Overhaul** after verification, with five inline JPEG screenshots.
Gmail readback confirms subject, DRAFT label, matching attachment filenames/byte
sizes/Content-IDs and HTML image references, and no To/Cc/Bcc headers. Nothing was
sent. Private Gmail IDs are kept only in /private/tmp/ocean-v1-gmail-receipt.json.
The [draft body](OCEAN-v1-architecture-overhaul-draft.html) is retained locally for review.

## Subsequent acceptance — 2026-10-14 JST

The user accepted the direction and requested Pipeline & jobs be omitted. P00
is Complete after removing that page, overview entry points, queue settings and
demo-jobs database listing, then rerunning typecheck, 27 tests and static build.
The [final P00 receipt](mockups/p00/source-revision.json) and
[accepted admin capture](mockups/p00/accepted-2026-10-14/administration.jpg) record
the final UI. The industry review and Gmail draft above remain dated evidence
of the preceding iteration; real-service and full conformance gates remain open.
