# C07 — Export safety

**Status:** Complete; delivered as `1195796` with passing hosted CI (2026-10-15 JST). **Prerequisites:** P00. **Contract:** typed spreadsheet-safe CSV serialization.

## Revised delivery boundary

Work on overhaul for the separate v1 system described in
[SITE_SEPARATION.md](../SITE_SEPARATION.md). The legacy site and its resources
remain unchanged. Existing entry points are reuse/regression references, not
permission to connect to production. P00 precedes backend implementation; its
prototype is not acceptance evidence for this component.

## Objective and boundaries

Repair audit F09 and establish consistent browser/server CSV handling before new Workspace exports reuse it. Strings containing spreadsheet formulas must remain text, while genuinely numeric scientific values retain their type and sign.

Included: shared serialization rules, browser exports, equivalent backend helpers, existing CSV consumers and cross-language fixtures. Excluded: changing scientific values, regenerating immutable publication bundles, altering export permissions or adding new export features. Apply presentation escaping only at the user-facing CSV boundary; never rewrite canonical input records.

## Existing entry points

Verified sources: [browser serializer](../../../../frontend/lib/csv.ts), [download component](../../../../frontend/components/CsvExportButton.tsx), and [analysis export](../../../../api/edna_analysis_routes.py). Additional server consumers are `api/main.py` and `api/admin_feedback_routes.py`; these already have partial protection and must retain their export metadata and truncation indicators. Existing tests include `tests/test_api_edna_analysis.py`, `tests/test_admin_feedback.py` and `tests/test_api_edna.py`.

## Interface decisions

Preserve `rowsToCsv`, column order and filename behavior. For string values and headers, prefix an apostrophe when the first non-whitespace character is `=`, `+`, `-` or `@`, or when the original string starts with tab, carriage return or newline. Then apply normal CSV quoting and quote escaping. Numeric negative values remain numeric; a textual `-1` remains text. Null/undefined serialize as empty cells. Object serialization remains documented JSON. Use one Python helper and one TypeScript helper implementing the same fixture contract; do not add separate ad hoc endpoint rules. Preserve original unescaped values in retained structured results.

## Resumable checkpoints and acceptance

1. **Shared examples:** define ordinary text, quoted/multiline text, Japanese text, formulas, leading whitespace/control characters, negative numbers, textual negatives and empty cells. Acceptance: expected bytes are explicit and require no spreadsheet execution.
2. **Browser boundary:** implement formula-safe serialization and register focused tests in the frontend test command. Acceptance: every dangerous string remains textual and numeric negatives are unchanged.
3. **Server parity:** consolidate existing helpers and check affected exports. Acceptance: Python/TypeScript fixtures agree, provenance columns and truncation headers survive, and original canonical values remain unchanged.

During implementation add proposed `frontend/lib/csv.test.ts` and run `cd frontend && node --test --experimental-strip-types --disable-warning=ExperimentalWarning --disable-warning=MODULE_TYPELESS_PACKAGE_JSON lib/csv.test.ts`; also run `npm run typecheck` there. Backend command: `python -m pytest tests/test_api_edna_analysis.py tests/test_admin_feedback.py tests/test_api_edna.py`. Extend those suites and proposed `tests/test_csv_serialization.py`. This planning setup has not run them.

## Compatibility, rollback and handoff

No data migration is required. Document apostrophe escaping as a CSV display/export behavior; structured evidence preserves original values. Preserve existing filenames and response shapes. If serialization must be disabled, disable affected downloads instead of restoring formula execution. Record fixtures, consumers, tests and limitations in `handoffs/C07.md`, updating `STATUS.md` after checkpoints. Complete only after frontend and backend acceptance.

## Exact prompts

Use the independent planning, implementation or resume prompt in
[PROMPTS.md](../PROMPTS.md#c07). Read the current site-separation
plan, UX brief and listed prerequisite handoffs as well as this specification.

## Local acceptance — 2026-10-15 JST

The shared fixture has 47 cases and an explicit Python/ECMAScript whitespace union.
One TypeScript policy now serves legacy tables, v1 tables and v1 administration;
one Python module serves all three API exports, including dynamic headers.
196 focused server tests, 132 legacy and 76 v1 frontend tests, both typechecks/builds
and the full 2,121-test backend (63 opt-in PostgreSQL skips, 81.85% coverage) pass.
Independent review finds no blockers and 835 extra cross-runtime values agree.
A stale local legacy Next installation was refreshed to the unchanged 15.5.27 lock
and its checks repeated. Intended presentation changes include lowercase booleans
and compact JSON feedback reason arrays; native JSON/number spelling outside the
fixture is not a new canonical scientific format. See [handoff](../handoffs/C07.md)
and [receipt](../evidence/C07/verification.json). No data migration/regeneration.

Hosted acceptance: 2,112 backend tests, 82.67% coverage, 132 legacy/76 v1
frontend tests, both typechecks/builds and production dependency audits, 63 actual
PostgreSQL cases plus idempotent upsert and isolated backup/restore. See
[delivery receipt](../evidence/C07/delivery.json) and [CI](https://github.com/jarondlk/ocean-platform/actions/runs/38670737411).
