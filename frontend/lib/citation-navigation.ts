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

export function citationIdsFromBracketToken(token: string): string[] {
  const match = /^\[([A-Za-z0-9_:.-]+(?:\s*[,;]\s*[A-Za-z0-9_:.-]+)*)\]$/.exec(token);
  return match ? match[1].split(/\s*[,;]\s*/) : [];
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
