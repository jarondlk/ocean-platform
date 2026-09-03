import type {
  ChatResponse,
  CitationAuditRecord,
  ContextDocument,
  SourceDocument,
} from "@/types";

export type CitationTargetKind = "source" | "context" | "invalid";

export type CitationTarget = {
  citationId: string;
  kind: CitationTargetKind;
  valid: boolean;
  cited: boolean;
  evidenceRole: string;
  sourceType?: string | null;
  contextType?: string | null;
  title: string;
  detail: string;
  source?: SourceDocument;
  context?: ContextDocument;
  audit?: CitationAuditRecord;
};

export type EvidenceDeepLinkKind = "provenance" | "sample" | "data" | "context";

export type EvidenceDeepLink = {
  kind: EvidenceDeepLinkKind;
  label: string;
  href: string;
};

export type AnalysisWorkspaceView = "trends" | "correlations" | "diversity" | "cooccurrence" | "bay_comparison" | "reliability";
export type ReliabilityWorkspaceView = "sst_ctd" | "gap" | "diversity_prediction" | "corroboration";

export type ContextWorkspaceTarget = {
  scope: "analysis" | "reliability";
  view: AnalysisWorkspaceView;
  reliabilityView?: ReliabilityWorkspaceView;
  diversitySource?: string;
};

const MAX_QUERY_VALUE_LENGTH = 200;
const evidenceIdentifierPattern = /^[A-Za-z0-9_:.-]+$/;
const isoDatePattern = /^\d{4}-\d{2}-\d{2}$/;

export function citationIdsFromBracketToken(token: string): string[] {
  const match = /^\[([A-Za-z0-9_:.-]+(?:\s*[,;]\s*[A-Za-z0-9_:.-]+)*)\]$/.exec(token);
  return match ? match[1].split(/\s*[,;]\s*/) : [];
}

export function safeEvidenceIdentifier(value: string | null | undefined): string | null {
  if (
    !value ||
    value.length > MAX_QUERY_VALUE_LENGTH ||
    value.includes("..") ||
    !evidenceIdentifierPattern.test(value)
  ) {
    return null;
  }
  return value;
}

export function safeIsoDate(value: string | null | undefined): string | null {
  if (!value || !isoDatePattern.test(value)) return null;
  const parsed = new Date(`${value}T00:00:00Z`);
  return Number.isNaN(parsed.getTime()) || parsed.toISOString().slice(0, 10) !== value
    ? null
    : value;
}

export function resolveContextWorkspace(contextId: string | null | undefined): ContextWorkspaceTarget | null {
  const safeId = safeEvidenceIdentifier(contextId);
  if (!safeId) return null;

  if (safeId === "analysis_ctd_trends_O") {
    return { scope: "analysis", view: "trends" };
  }
  if (safeId === "analysis_bay_comparison") {
    return { scope: "analysis", view: "bay_comparison" };
  }
  if (safeId === "analysis_taxa_env_correlations") {
    return { scope: "analysis", view: "correlations" };
  }
  if (safeId === "analysis_diversity_kraken") {
    return { scope: "analysis", view: "diversity", diversitySource: "kraken" };
  }
  if (safeId === "analysis_diversity_metaeuk") {
    return { scope: "analysis", view: "diversity", diversitySource: "metaeuk" };
  }
  if (safeId === "reliability_sst_ctd_validation") {
    return { scope: "reliability", view: "reliability", reliabilityView: "sst_ctd" };
  }
  if (safeId === "reliability_gap_interpolation") {
    return { scope: "reliability", view: "reliability", reliabilityView: "gap" };
  }
  if (safeId === "reliability_diversity_prediction") {
    return { scope: "reliability", view: "reliability", reliabilityView: "diversity_prediction" };
  }
  if (safeId === "reliability_corroboration_summary") {
    return { scope: "reliability", view: "reliability", reliabilityView: "corroboration" };
  }
  return null;
}

export function evidenceDeepLinks(target: CitationTarget): EvidenceDeepLink[] {
  if (!target.valid || target.kind === "invalid") return [];

  if (target.source) {
    const docId = safeEvidenceIdentifier(target.source.doc_id);
    if (!docId) return [];

    const links: EvidenceDeepLink[] = [
      {
        kind: "provenance",
        label: "Provenance",
        href: buildHref("/provenance", { view: "trace", doc_id: docId }),
      },
    ];
    const sampleId = safeEvidenceIdentifier(target.source.sample_id);
    if (sampleId && target.source.source_type !== "edna_metabarcoding") {
      links.push({
        kind: "sample",
        label: "Sample",
        href: buildHref("/explore", { view: "tables", sample_id: sampleId, doc_id: docId }),
      });
    }

    if (target.source.source_type === "ctd" && sampleId) {
      links.push({
        kind: "data",
        label: "CTD profile",
        href: buildHref("/data", { view: "ctd", sample_id: sampleId, doc_id: docId }),
      });
    } else if (target.source.source_type === "metagenome" && sampleId) {
      links.push({
        kind: "data",
        label: "Taxa profile",
        href: buildHref("/data", { view: "taxa", sample_id: sampleId, doc_id: docId }),
      });
    } else if (target.source.source_type === "remote_sensing") {
      const date = safeIsoDate(target.source.time?.slice(0, 10));
      if (date) {
        links.push({
          kind: "data",
          label: "SST record",
          href: buildHref("/data", { view: "sst", time_from: date, time_to: date, doc_id: docId }),
        });
      }
    } else if (target.source.source_type === "edna_metabarcoding" && sampleId) {
      const assayId = safeEvidenceIdentifier(target.source.assay_id);
      const assignmentMethod = safeEvidenceIdentifier(target.source.assignment_method);
      links.push({
        kind: "data",
        label: "eDNA sample",
        href: buildHref("/data", {
          view: "edna",
          sample_id: sampleId,
          assay_id: assayId,
          assignment_method: assignmentMethod,
          doc_id: docId,
        }),
      });
    }
    return links;
  }

  if (target.context) {
    const analysisId = target.context.analysis_id;
    const table = target.context.table;
    if (target.context.source_family === "edna_metabarcoding" && analysisId && /^[a-f0-9]{64}$/.test(analysisId)
        && table && target.context.doc_id === `analysis_edna_${analysisId}_${table}` && ["diversity", "method_summary", "controls", "associations", "environment_links"].includes(table)) {
      return [{ kind: "provenance", label: "Provenance", href: buildHref("/provenance", { view: "trace", doc_id: target.context.doc_id }) }, { kind: "context", label: "eDNA analysis", href: buildHref("/data", {
        view: "edna_analysis", analysis_id: analysisId, table,
      }) }];
    }
    const contextId = safeEvidenceIdentifier(target.context.doc_id);
    const workspace = resolveContextWorkspace(contextId);
    if (!contextId || !workspace || target.context.context_type !== workspace.scope) return [];
    return [{
      kind: "context",
      label: workspace.scope === "reliability" ? "Reliability" : "Analysis",
      href: buildHref("/data", { view: workspace.scope, context_id: contextId }),
    }];
  }

  return [];
}

export function buildHref(path: string, values: Record<string, string | null | undefined>): string {
  const params = new URLSearchParams();
  Object.entries(values).forEach(([key, value]) => {
    if (value) params.set(key, value);
  });
  const query = params.toString();
  return query ? `${path}?${query}` : path;
}

export function buildCitationTargetIndex(
  response: ChatResponse | null | undefined,
): ReadonlyMap<string, CitationTarget> {
  const targets = new Map<string, CitationTarget>();
  if (!response) return targets;

  const auditById = new Map<string, CitationAuditRecord>();
  (response.answer_audit?.citations || []).forEach((audit) => {
    if (!auditById.has(audit.citation_id)) {
      auditById.set(audit.citation_id, audit);
    }
  });

  [...(response.sources || []), ...(response.linked_sources || [])].forEach((source) => {
    const audit = auditById.get(source.doc_id);
    targets.set(source.doc_id, sourceTarget(source, audit, Boolean(audit)));
  });

  [...(response.analysis_context || []), ...(response.reliability_context || [])].forEach((context) => {
    const audit = auditById.get(context.doc_id);
    targets.set(context.doc_id, contextTarget(context, audit, Boolean(audit)));
  });

  auditById.forEach((audit, citationId) => {
    if (targets.has(citationId)) return;
    targets.set(citationId, invalidTarget(audit));
  });

  return targets;
}

export function sourceTarget(
  source: SourceDocument,
  audit?: CitationAuditRecord,
  cited = false,
): CitationTarget {
  const valid = audit ? audit.valid : true;
  return {
    citationId: source.doc_id,
    kind: valid ? "source" : "invalid",
    valid,
    cited,
    evidenceRole: audit?.evidence_role || source.retrieval_role || "primary",
    sourceType: audit?.source_type || source.source_type,
    contextType: audit?.context_type,
    title: audit?.title || source.title || source.doc_id,
    detail: audit?.detail || "Retrieved evidence supplied to the model.",
    source,
    audit,
  };
}

export function contextTarget(
  context: ContextDocument,
  audit?: CitationAuditRecord,
  cited = false,
): CitationTarget {
  const valid = audit ? audit.valid : true;
  return {
    citationId: context.doc_id,
    kind: valid ? "context" : "invalid",
    valid,
    cited,
    evidenceRole: audit?.evidence_role || "context",
    sourceType: audit?.source_type,
    contextType: audit?.context_type || context.context_type,
    title: audit?.title || context.title || context.doc_id,
    detail: audit?.detail || "Supplementary context supplied to the model.",
    context,
    audit,
  };
}

function invalidTarget(audit: CitationAuditRecord): CitationTarget {
  return {
    citationId: audit.citation_id,
    kind: "invalid",
    valid: false,
    cited: true,
    evidenceRole: audit.evidence_role || "unresolved",
    sourceType: audit.source_type,
    contextType: audit.context_type,
    title: audit.title || audit.citation_id,
    detail: audit.detail || "Citation was not present in supplied evidence.",
    audit,
  };
}
