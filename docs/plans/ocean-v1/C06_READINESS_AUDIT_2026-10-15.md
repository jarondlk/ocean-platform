# C05 delivery and C06 readiness audit

Updated: 2026-10-15 JST. Branch: `overhaul`.

**C05 is committed/pushed and hosted CI passes. C06 is ready for explicit
selection and remains Not started.** The user requested delivery on overhaul
and verification before later C06 work; this audit does not select C06 implementation.

## Delivered checkpoint

Commit [fd8f520](https://github.com/jarondlk/ocean-platform/commit/fd8f5203cba4d57ade85018d639a54696616635a)
contains exactly the 63 paths in the reviewed C05 receipt. The 30 older unrelated
README/audit/benchmark files remain outside the checkpoint. The C05 local receipt
is historical evidence of the accepted pre-commit state; this audit records the
subsequent delivery. Its 19 source/test/workflow hashes still match.

[Hosted CI run 38602439380](https://github.com/jarondlk/ocean-platform/actions/runs/38602439380)
completed successfully for this exact source commit:

| Check | Result |
|---|---|
| Backend, lint and generated scope contract | 1,797 passed, 63 opt-in PostgreSQL skips; 82.60% coverage (minimum 70%) |
| Legacy frontend | 81 tests, typecheck, build and production dependency audit pass |
| V1 prototype | 27 tests, typecheck, build and production dependency audit pass |
| Existing PostgreSQL integration | 39 passed |
| C03 PostgreSQL retention ordering | 12 passed |
| C05 PostgreSQL identity/history | 12 passed, including two historical bug probes |
| Corpus upsert and backup/isolated restore | Pass |

The PostgreSQL job uses its own PostgreSQL 16.15/pgvector 0.8.7 service; C03 and
C05 use separate named databases and verify the exact job-owned server address.
Dependency review is skipped because this is a push, as configured. Broad backend
skips are separately covered by the three actual PostgreSQL suites. Local C05's
1,806-test run includes nine older uncommitted benchmark tests absent from the
hosted checkout, explaining the count difference.

[Delivery/readiness evidence](evidence/c06-readiness-2026-10-15/verification.json)
binds source hashes, CI job/step conclusions, extracted job summaries, prerequisite
verification, current runtime and offline baseline probes. The source checkpoint
is delivered to origin/overhaul; main and the legacy deployment are unchanged.

## C06 prerequisite and scope

The C06 specification and component manifest both list **P00 only** as their
formal prerequisite. P00 is accepted/Complete and all 36 accepted file hashes
match. C01–C05 are also Complete for their recorded local software acceptance;
C05's delivery gate is now fulfilled. The seven real scientific artifacts and
the two inspected serving files remain unchanged. The 82 legacy metagenome
documents awaiting a real rebuild are a deferred C05 operational action, not a
C06 dependency or authorization to execute that rebuild.

C06 will repair F07 and add provider-independent generation metadata for ordinary
and structured requests. It does not choose new models, change credentials,
redesign embeddings, add controller retries, benchmark providers or deploy.
All provider payloads can remain mocked; no external service is required for its
specified acceptance. Locked local dependencies and the hosted regression
environment are available.

## Baseline audit

The exact proposed C06 baseline command passes on the delivered source:

```sh
.venv/bin/python -m pytest tests/test_model_runtime.py tests/test_query_orchestrator.py tests/test_auto_settings.py -q --tb=short
```

Result: **99 passed, zero skips** with explicit test settings, unused loopback
database/model URLs and mocked providers. This baseline is regression/readiness
evidence, not acceptance of the future C06 result contract.

[Sixteen mocked payload probes](evidence/c06-readiness-2026-10-15/readiness-probes.json)
exercise both adapters and both methods with completion, output limit, missing
and unknown termination reasons. A seventeenth mocked call invokes the actual
API handler with the actual Ollama adapter and stubbed retrieval/persistence.
It reproduces F07: a nonempty `done_reason=length` result returns an `answered`
response and reaches the stubbed completed-receipt boundary. No provider or
database call is made and no application source is changed.

Observed current behavior:

| Method | Explicit normal finish | Output limit | Missing finish | Unknown finish |
|---|---|---|---|---|
| Ollama ordinary chat | Returns text | Returns partial text (F07) | Returns text | Returns text |
| Ollama structured chat | Returns JSON text | Raises ValueError | Returns JSON text | Returns JSON text |
| Vertex ordinary chat | Returns text | Raises ModelOutputLimitError | Returns text | Raises ValueError |
| Vertex structured chat | Returns JSON text | Raises ValueError | Returns JSON text | Raises ValueError |

The common typed result, normalized completed/output-limited/refused/failed/unknown
outcomes, measured generation duration and optional provider token usage are
not implemented yet. Current partial guards must be retained while C06 centralizes
the contract. Missing usage must remain unavailable rather than zero; valid JSON
must not override an incomplete provider termination.

## Consumer map and first checkpoint

The specification lists `orchestration/query_orchestrator.py` as a reference;
inspection confirms it retrieves evidence and builds prompts rather than calling
generation itself. The actual ordinary-generation/completed-answer boundary is
`api/main.py`. It currently recognizes the Vertex-specific `ModelOutputLimitError`,
returns a 502 and records failure instead of a completed answer. This path must
remain safe for both providers after normalization.

`orchestration/settings_planner.py` calls `structured_chat`, then validates its
bounded JSON. Runtime exceptions become an unavailable planning result; parseable
but incomplete JSON must fail before planner execution. Preserve existing
string-call signatures and completed legacy output while adding result methods.
The C05 identified-query embedding API and its actual ranking tests remain an
independent regression boundary.

When C06 is selected, start with the result-contract checkpoint: typed metadata
and mocked adapter fixtures covering normal, missing/unknown, refused, failed,
output-limit and malformed responses with optional usage. Then route both ordinary
and structured generation and compatibility wrappers through the same completion
decision. Finally test API/planner error handling, failure receipts and retained
signatures without introducing provider retries. Read the specification/prompt,
P00 handoff and this source receipt before modifying code.

## Remaining boundaries

C06 has no missing prerequisite or delivery blocker. C06 application work has
not begun and no C06 handoff or acceptance receipt is implied by this audit.
The existing C05 rebuild runbook remains deferred. Local and hosted software
success does not establish model quality, scientific publication, production
index acceptance, cloud isolation or release acceptance. C06–C27 remain unselected.
