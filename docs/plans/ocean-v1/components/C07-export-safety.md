# C07 — Export safety

**Status:** Not started. **Prerequisites:** None. **Contract:** typed spreadsheet-safe CSV serialization.

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

**Planning-only**
> Review C07 without implementing. Read docs/plans/ocean-v1/{README.md,MASTER_PLAN.md,DECISIONS.md,STATUS.md}, components/C07-export-safety.md and relevant handoffs; C07 has no prerequisites. Inspect current serializers and checkout, then report refinements only. Do not edit application code or begin implementation without an explicit implementation request.

**Implementation**
> Implement only C07. Read the planning README, MASTER_PLAN, DECISIONS, STATUS, this C07 specification and relevant handoffs under docs/plans/ocean-v1; no prerequisites apply. Verify the checkout and preserve unrelated work. Complete checkpoints, update STATUS.md and handoffs/C07.md after each, and run required tests before completion. Do not start another component, modify canonical data, publish, make cloud writes, provision, deploy or run paid model evaluation.

**Resume**
> Resume C07 only after reading docs/plans/ocean-v1/{README.md,MASTER_PLAN.md,DECISIONS.md,STATUS.md}, components/C07-export-safety.md and handoffs/C07.md; no prerequisites apply. Reconcile current checkout and test evidence, then continue the next unfinished checkpoint. Preserve unrelated work, test changes and update status/handoff. Do not start another component, modify canonical data, publish, make cloud writes, provision, deploy or run paid model evaluation.
