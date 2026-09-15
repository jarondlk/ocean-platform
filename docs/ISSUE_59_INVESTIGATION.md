# Issue #59 investigation

Investigated on 2026-09-11–12 JST against deployed v0.4.4 and source commit
`730805bb63775c5e0a725fc0a218b31d08032f91`.
[Issue #59](https://github.com/jarondlk/ocean-platform/issues/59) reports that
`fetch me some edna metabarcoding samples` returns
`The language model could not complete the request`. The issue has no body or
comments supplying additional reproduction details.

## Confirmed failure

The model reaches its configured output-token limit. `VertexRuntime.chat`
rejects the unfinished response; the chat endpoint records a failed interaction
and returns HTTP 502 with the generic `llm_request_failed` message.

This remains present in v0.4.4. The taxonomy release did not change this model
response path or output budget.

| Evidence | Observation |
| --- | --- |
| Original exact-query interaction | Created 2026-09-10 04:43:52 UTC; failed after 10,185 ms |
| Original revision | `ocean-platform-00013-djj` |
| Correlated original exception | 04:44:02 UTC: `Vertex AI answer did not finish cleanly: MAX_TOKENS` |
| Latest exact-query interaction | Created 2026-09-11 11:26:24 UTC; failed after 11,247 ms |
| Latest revision | `ocean-platform-v044-d3aa6a9` |
| Correlated latest exception | 11:26:35 UTC: the same `MAX_TOKENS` exception |
| Model and deployment configuration | `gemini-3.6-flash`, 1,600 maximum output tokens, thinking budget 0 |
| Request generation options | Temperature 0, top-p 0.9, no requested output-limit override |
| Latest retrieval | PostgreSQL, publication ready, eight primary documents, no linked or supplementary context documents |
| Evidence mix | Two eDNA method documents for one sample, plus six shotgun-metagenome documents |
| Latest prompt size | 8,867 characters, including 5,473 retrieved-text characters |

The timestamps connect the saved exact-query interactions to the production
exceptions. The error occurs after evidence retrieval and model invocation;
the evidence does not indicate a missing eDNA dataset, pending publication,
GCP authentication failure, or request timeout for these interactions.

Google defines `MAX_TOKENS` as reaching the configured generated-token limit:
[Vertex GenerateContentResponse documentation](https://cloud.google.com/vertex-ai/generative-ai/docs/reference/rest/v1/GenerateContentResponse#FinishReason).

## Code path and contributing conditions

1. `model_runtime.py`, `VertexRuntime.chat`: `max_output_tokens` is capped at
   `CHAT_MAX_OUTPUT_TOKENS`, currently 1,600 in production. A requested higher
   `num_predict` value is silently clamped. The adapter raises on a non-STOP
   finish reason before returning any answer text.
2. `api/main.py`, `chat`: all generation exceptions become the same public
   `llm_request_failed` response. The stored interaction retains the generic
   code, but not structured finish-reason or token-usage metadata.
3. `orchestration/unified.py`, `infer_expected_source_types`: the phrase is
   correctly recognized as eDNA intent. By design this inference drives
   diagnostics, not a retrieval filter. With `source_type=null` and `k=8`,
   six shotgun-metagenome results accompany the two eDNA method documents.
4. The prompt requests an answer under 500 words and a citation in every
   factual paragraph/bullet. It exposes full eDNA document identifiers,
   containing a 64-character hash and method suffix, as model-generated
   citation labels. A word limit does not enforce a token limit. Repeated
   identifiers create substantial output pressure. The controlled replay below
   reproduced failure with full IDs and completion with short labels; reducing
   the evidence to eDNA alone did not resolve it.
5. The request schema accepts `num_predict` up to 8,192 while the deployed
   adapter caps it at 1,600. Increasing the UI field beyond the server cap
   therefore cannot resolve this failure by itself.

The current rejection of an unfinished answer protects citation integrity.
Removing the finish-reason check would turn a visible failure into an
apparently complete but truncated scientific answer.

## Validation

The relevant runtime and persisted-chat tests passed: 14 tests across
`tests/test_model_runtime.py` and `tests/test_chat_feedback.py`. Existing tests
explicitly require rejection of MAX_TOKENS responses and failure persistence.
They verify the current contract; they do not demonstrate that the user query
will complete within the deployed generation budget.

A bounded diagnostic job, `ocean-anemone-process-7gtj8`, was submitted with
three generation cases, each limited to 1,600 output tokens and with SDK
retries disabled:

- reconstruct the latest saved request and require its exact prompt SHA-256;
- retain only its two eDNA evidence documents;
- use the same eDNA evidence with short, local citation labels.

The job completed successfully. Its baseline prompt exactly matched the saved
v0.4.4 prompt SHA-256, `facc34b26d5476de428418d31ace635763aef6795c71b9ad7323e81b8a6e4d4e`.
All cases used the saved temperature/top-p settings, the same model, thinking
budget 0, and the same 1,600-token output limit.

| Replay case | Prompt tokens | Returned answer tokens | Finish reason | Result |
| --- | --- | --- | --- | --- |
| Exact saved request, eight documents | 3,264 | 1,596 | MAX_TOKENS | Truncated midway through an eDNA citation |
| Two eDNA documents, full IDs | 2,060 | 1,596 | MAX_TOKENS | Truncated while listing detected taxa |
| Same two documents, short citation labels | 1,927 | 756 | STOP | Complete 281-word answer |

The baseline unfinished answer contained only 167 whitespace-separated words,
well below the 500-word instruction. Bracketed citations occupied 1,405 of its
2,655 characters. This illustrates why a word target does not prevent citation
identifiers from exhausting the token budget.

The short-label answer was expanded through its exact per-request mapping
back to canonical document IDs and passed the existing answer audit: 22 valid
citation references, zero invalid citations, no missing expected source types,
and no audit warnings. That validates identifier resolution, not independent
scientific verification of every generated claim.

These are one trial per case, not a reliability benchmark. They support short
citation labels as the first correction to implement and test. Filtering alone
is insufficient. The successful short-label trial did not increase the output
budget. See [machine-readable replay metrics](ISSUE_59_REPLAY_RESULTS.json).

The diagnostic job read saved evidence and made three bounded model calls. It
did not write chat interactions, change canonical data, or update service settings.

## Recommended correction

- Introduce short citation labels within the generation prompt, then resolve
  them through an explicit per-request mapping to canonical identifiers before
  auditing, persistence, and rendering. Cover primary, linked, analysis, and
  reliability sources; reject unknown labels and retain exact provenance.
- Add a deliberate eDNA-only inventory path for an unambiguous request like
  this one, while preserving explicit filters and mixed-source comparison
  intent. Display the pilot as one sample with two assignment methods. Its
  unknown classification still permits inventory inspection and must continue
  to exclude it from environmental-only ecological conclusions.
- Report output-limit failures distinctly and retain safe structured finish
  reason/usage metadata. Keep unfinished responses out of the completed-answer
  path. Align any user-visible output-limit controls with the effective server
  limit. Evaluate a bounded concise-answer fallback only after measuring the
  scoped/short-citation cases; avoid unconditional repeated generation.
- Add regressions for long eDNA identifiers, the exact reported query's source
  selection, canonical citation resolution, partial-answer rejection, and
  preservation of mixed-source requests. Validate with a small production-like
  canary before changing the deployed budget.

No application fix, production configuration change, issue comment, or issue
closure has been performed as part of this investigation.
