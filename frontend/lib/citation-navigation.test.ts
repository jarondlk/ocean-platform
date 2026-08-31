import assert from "node:assert/strict";
import test from "node:test";
import {
  buildCitationTargetIndex,
  citationIdsFromBracketToken,
} from "./citation-navigation.ts";
import type { ChatResponse } from "../types.ts";

function responseFixture(): ChatResponse {
  return {
    query: "Compare CTD and SST reliability.",
    answer: "Supported [ctd_sample-1] [reliability_sst_ctd_validation] [missing_doc].",
    sources: [
      {
        doc_id: "ctd_sample-1",
        title: "CTD sample 1",
        source_type: "ctd",
        sample_id: "sample-1",
        text: "CTD evidence",
        retrieval_role: "primary",
      },
      {
        doc_id: "ctd_unused",
        title: "Unused CTD sample",
        source_type: "ctd",
        text: "Additional evidence",
        retrieval_role: "primary",
      },
    ],
    linked_sources: [],
    analysis_context: [],
    reliability_context: [
      {
        doc_id: "reliability_sst_ctd_validation",
        title: "SST / CTD validation",
        context_type: "reliability",
        analysis_type: "cross_source_validation",
        text: "Reliability context",
      },
    ],
    model: "test-model",
    n_sources: 2,
    n_linked_sources: 0,
    n_context_documents: 1,
    prompt_diagnostics: {},
    retrieval_diagnostics: {},
    answer_audit: {
      trust_level: "caution",
      trust_score: 0.75,
      citation_count: 3,
      valid_citation_count: 2,
      invalid_citation_count: 1,
      cited_source_types: ["ctd"],
      expected_source_types: ["ctd", "remote_sensing"],
      retrieved_source_types: ["ctd"],
      missing_expected_citations: ["remote_sensing"],
      primary_sources_cited: 1,
      linked_sources_cited: 0,
      analysis_context_cited: 0,
      reliability_context_cited: 1,
      unused_linked_sources: [],
      citation_requirements: {},
      invalid_citations: [],
      warnings: [],
      citations: [
        {
          citation_id: "ctd_sample-1",
          raw: "[ctd_sample-1]",
          valid: true,
          evidence_role: "primary",
          source_type: "ctd",
          context_type: null,
          covered_source_types: ["ctd"],
          title: "CTD sample 1",
          detail: "Resolved against supplied evidence.",
        },
        {
          citation_id: "reliability_sst_ctd_validation",
          raw: "[reliability_sst_ctd_validation]",
          valid: true,
          evidence_role: "context",
          source_type: null,
          context_type: "reliability",
          covered_source_types: ["ctd", "remote_sensing"],
          title: "SST / CTD validation",
          detail: "Resolved against supplied evidence.",
        },
        {
          citation_id: "missing_doc",
          raw: "[missing_doc]",
          valid: false,
          evidence_role: null,
          source_type: null,
          context_type: null,
          covered_source_types: [],
          title: null,
          detail: "Citation was not present in supplied evidence.",
        },
      ],
    },
    options: {},
  };
}

test("resolves source, context, invalid, and uncited evidence targets", () => {
  const targets = buildCitationTargetIndex(responseFixture());

  const source = targets.get("ctd_sample-1");
  assert.equal(source?.kind, "source");
  assert.equal(source?.valid, true);
  assert.equal(source?.cited, true);
  assert.equal(source?.source?.sample_id, "sample-1");

  const context = targets.get("reliability_sst_ctd_validation");
  assert.equal(context?.kind, "context");
  assert.equal(context?.contextType, "reliability");
  assert.equal(context?.context?.analysis_type, "cross_source_validation");

  const invalid = targets.get("missing_doc");
  assert.equal(invalid?.kind, "invalid");
  assert.equal(invalid?.valid, false);
  assert.match(invalid?.detail || "", /not present/i);

  const uncited = targets.get("ctd_unused");
  assert.equal(uncited?.kind, "source");
  assert.equal(uncited?.valid, true);
  assert.equal(uncited?.cited, false);
});

test("returns an empty target index without a response", () => {
  assert.equal(buildCitationTargetIndex(null).size, 0);
});

test("parses single and grouped bracket citation tokens", () => {
  assert.deepEqual(citationIdsFromBracketToken("[ctd_sample-1]"), ["ctd_sample-1"]);
  assert.deepEqual(
    citationIdsFromBracketToken("[ctd_sample-1, sst_2026-01-03; reliability:summary]"),
    ["ctd_sample-1", "sst_2026-01-03", "reliability:summary"],
  );
  assert.deepEqual(citationIdsFromBracketToken("[not a citation]"), []);
});
