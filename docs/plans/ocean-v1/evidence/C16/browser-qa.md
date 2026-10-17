# C16 rendered service browser observations

Observed2026-10-17 JST through the in-app browser using the production v1 build
and owned127.0.0.1:3100 harness. The harness used actual C14/C16 routes and auth
middleware with an explicit server-side TEST researcher, two sealed synthetic
C09/C10–C13 snapshots and51 canonical nodes. It supplied no real OIDC session,
provider, database, scientific approval or production target. Browser screenshots
were inspected in tool output; no screenshot file is claimed in this receipt.

- Keyboard tree expansion traversed Data → CTD source → nested collection →
  dataset. Arrow keys/Home/End moved roving focus; semantic tree rows exposed
  levels, selection and expansion. Dataset Browse contents exposed both native
  table children; the depth-table child opened its parent's actual query.
- CTD casts returned four data rows; depth observations returned eight with m,
  degC, PSU and the negative-1.5 value retained. Dataset authority remained
  descriptive, unpublished and not_reviewed. eDNA raw output returned eleven
  data rows with the explicit controls/unknown-not-eligible qualification.
  Retained counts and actual scoped query counts stayed distinguishable.
- Direct depth-table URL reload retained snapshot/object/section and rows.
  Back/Forward restored Overview/Tables. Reopening the current catalogue
  navigation preserved its URL. Snapshot changes cleared selected node/parent;
  Back restored the original newer snapshot and table section.
- Search across all51 nodes with page size25 yielded25/25/1 entries, disabled
  Next on the final page, restored Previous and retained cursor results on reload.
  Multi-root/source URL filters displayed every active filter chip and the two
  expected datasets. No client approximation replaced server totals.
- A workflow's unsupported Tables section showed unavailable; its child listing
  showed No child objects. An unmatched search showed No matching objects.
  These were distinct from access and request errors.
- A published synthetic analysis displayed12 data rows and actual publication
  scope. The final build explicitly stated that retained publication scope leaves
  browsing/investigation settings unchanged, labelled retained row counts, and
  labelled the separate provenance scope Catalogue browsing scope.
- EN/JA × light/dark ×1440×900,900×1024,390×844: all12 combinations had document
  width equal to viewport width. Catalogue widths were1216/734/390 respectively;
  heading/search/filter/mobile controls stayed within the available pane.
  Japanese mobile long IDs and filter labels were visually inspected.
- Mobile directory dialog occupied a310px-wide full-height panel with scrim.
  Accessibility output exposed only the modal. Escape restored Directories.
  Final-build Shift-Tab from close reached the roving selected tree item;
  Tab wrapped to close. A full forward cycle also wrapped to close and remained
  inside the dialog. This rechecked the fixed exclusion of tabIndex=-1 buttons.
- While the published analysis and rows were open, trusted test policy revision
  changed without changing identity/role and revoked that analysis. Opening
  Provenance cleared all protected panes: zero rows and zero protected-title
  occurrences remained; a changed-view notice appeared. Reset cleared invalid
  node/parent/cursor and recovered the current listing. A restored policy plus
  Refresh access restored the permitted analysis.
- A subsequent test401 on bootstrap removed catalogue, account identity and
  destination links and showed Sign in to continue. Restoring authorization and
  Retry recovered the actual service catalogue. No P00 fallback appeared.
- Final browser warning/error log was empty. The owned browser tab was closed,
  temporary viewport reset and owned small server52890 stopped with exit0.
  The earlier owned100000 server56312 was also stopped.

These observations include manual keyboard and accessibility-tree inspection.
They do not claim spoken VoiceOver/NVDA testing, independent assistive-user
validation, real identity enrollment or production performance. Those operational
qualifications remain explicit; all recorded scientific inputs are synthetic.
