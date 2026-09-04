import assert from "node:assert/strict";
import test from "node:test";
import {
  buildHref,
  buildCitationTargetIndex,
  citationIdsFromBracketToken,
  evidenceDeepLinks,
  contextTarget,
  resolveContextWorkspace,
  safeEvidenceIdentifier,
  safeIsoDate,
  sourceTarget,
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

test("builds deterministic raw-source evidence links", () => {
  const source = buildCitationTargetIndex(responseFixture()).get("ctd_sample-1");
  assert.ok(source);
  assert.deepEqual(evidenceDeepLinks(source), [
    {
      kind: "provenance",
      label: "Provenance",
      href: "/provenance?view=trace&doc_id=ctd_sample-1",
    },
    {
      kind: "sample",
      label: "Sample",
      href: "/explore?view=tables&sample_id=sample-1&doc_id=ctd_sample-1",
    },
    {
      kind: "data",
      label: "CTD profile",
      href: "/data?view=ctd&sample_id=sample-1&doc_id=ctd_sample-1",
    },
  ]);
});

test("maps exact analysis and reliability context documents", () => {
  assert.deepEqual(resolveContextWorkspace("analysis_ctd_trends_O"), {
    scope: "analysis",
    view: "trends",
  });
  assert.deepEqual(resolveContextWorkspace("analysis_diversity_metaeuk"), {
    scope: "analysis",
    view: "diversity",
    diversitySource: "metaeuk",
  });
  assert.deepEqual(resolveContextWorkspace("analysis_bay_comparison"), {
    scope: "analysis",
    view: "bay_comparison",
  });
  assert.deepEqual(resolveContextWorkspace("reliability_gap_interpolation"), {
    scope: "reliability",
    view: "reliability",
    reliabilityView: "gap",
  });
  assert.equal(resolveContextWorkspace("analysis_unknown"), null);
  assert.equal(resolveContextWorkspace("analysis_ctd_trends_unknown"), null);
});

test("builds source-specific SST and metagenome destinations", () => {
  const sst = sourceTarget({
    doc_id: "sst_2026-01-03",
    title: "SST 2026-01-03",
    source_type: "remote_sensing",
    time: "2026-01-03T12:00:00Z",
    text: "SST evidence",
  });
  assert.deepEqual(evidenceDeepLinks(sst).map((link) => link.href), [
    "/provenance?view=trace&doc_id=sst_2026-01-03",
    "/data?view=sst&time_from=2026-01-03&time_to=2026-01-03&doc_id=sst_2026-01-03",
  ]);

  const metagenome = sourceTarget({
    doc_id: "meta_2024-04-O-s1",
    title: "Metagenome sample",
    source_type: "metagenome",
    sample_id: "2024-04-O-s1",
    text: "Taxa evidence",
  });
  assert.deepEqual(evidenceDeepLinks(metagenome).map((link) => link.href), [
    "/provenance?view=trace&doc_id=meta_2024-04-O-s1",
    "/explore?view=tables&sample_id=2024-04-O-s1&doc_id=meta_2024-04-O-s1",
    "/data?view=taxa&sample_id=2024-04-O-s1&doc_id=meta_2024-04-O-s1",
  ]);
});

test("routes eDNA evidence to the exact eDNA data view", () => {
  const edna = sourceTarget({
    doc_id: `edna_${"a".repeat(64)}_qcauto_target`,
    title: "ANEMONE MiFish sample",
    source_type: "edna_metabarcoding",
    sample_id: "s".repeat(64),
    assay_id: "a".repeat(64),
    assignment_method: "qcauto_target",
    text: "Detection records",
  });
  assert.deepEqual(evidenceDeepLinks(edna).map((link) => link.href), [
    `/provenance?view=trace&doc_id=edna_${"a".repeat(64)}_qcauto_target`,
    `/data?view=edna&sample_id=${"s".repeat(64)}&assay_id=${"a".repeat(64)}&assignment_method=qcauto_target&doc_id=edna_${"a".repeat(64)}_qcauto_target`,
  ]);
  assert.equal(evidenceDeepLinks(edna).some((link) => link.href.includes("view=taxa")), false);
});

test("only publishes full-page links for known context artifacts", () => {
  const known = contextTarget({
    doc_id: "reliability_corroboration_summary",
    title: "Corroboration",
    context_type: "reliability",
    analysis_type: "corroboration",
    text: "Reliability evidence",
  });
  assert.deepEqual(evidenceDeepLinks(known), [{
    kind: "context",
    label: "Reliability",
    href: "/data?view=reliability&context_id=reliability_corroboration_summary",
  }]);

  const unpublished = contextTarget({
    doc_id: "analysis_future_artifact",
    title: "Future artifact",
    context_type: "analysis",
    text: "Unpublished view",
  });
  assert.deepEqual(evidenceDeepLinks(unpublished), []);
});

test("rejects unsafe or malformed deep-link values", () => {
  assert.equal(safeEvidenceIdentifier("ctd_2024-01-O-s1"), "ctd_2024-01-O-s1");
  assert.equal(safeEvidenceIdentifier("../../admin"), null);
  assert.equal(safeEvidenceIdentifier(".."), null);
  assert.equal(safeEvidenceIdentifier("with spaces"), null);
  assert.equal(safeIsoDate("2026-02-28"), "2026-02-28");
  assert.equal(safeIsoDate("2026-02-31"), null);
  assert.equal(buildHref("/data", { view: "sst", time_from: "2026-01-01" }), "/data?view=sst&time_from=2026-01-01");

  const invalid = buildCitationTargetIndex(responseFixture()).get("missing_doc");
  assert.ok(invalid);
  assert.deepEqual(evidenceDeepLinks(invalid), []);
});
