import {scopeErrors, settingsErrors, type ChatSettings} from './chat-settings.ts';
import type {EvidenceScope} from './generated/chat-scope.ts';
import type {ResearchIntent} from '../types.ts';

export type AutoPlan = {
  status: string; explanation: string; scope?: EvidenceScope; researchIntent?: ResearchIntent;
  route?: string; preset?: string;
};
export function readAutoPlan(options: Record<string, unknown> | undefined): AutoPlan | null {
  const raw = options?.planning;
  if (!raw || typeof raw !== 'object' || Array.isArray(raw)) return null;
  const plan = raw as Record<string, unknown>;
  if (typeof plan.status !== 'string') return null;
  const scope = options?.evidence_scope;
  const intent = plan.research_intent as ResearchIntent | undefined;
  return {status: plan.status,
    explanation: typeof plan.explanation === 'string' ? plan.explanation : typeof plan.message === 'string' ? plan.message : '',
    scope: plan.status === 'applied' && !scopeErrors(scope).length ? scope as EvidenceScope : undefined,
    researchIntent: intent && typeof intent.kind === 'string' ? intent : undefined,
    route: typeof plan.route === 'string' ? plan.route : undefined,
    preset: typeof plan.preset === 'string' ? plan.preset : undefined};
}

export function effectiveChatSettings(manual: ChatSettings, options: Record<string, unknown> | undefined): ChatSettings {
  if (!readAutoPlan(options)?.scope) return manual;
  const effective = {...manual};
  for (const [section, keys] of Object.entries({
    retrieval: {k: 'k', vector_weight: 'vectorWeight', fts_weight: 'ftsWeight', rrf_k: 'rrfK', expand_evidence: 'expandEvidence', max_linked_sources: 'maxLinkedSources'},
    context: {inject_analysis: 'injectAnalysis', inject_reliability: 'injectReliability', run_answer_audit: 'runAnswerAudit'},
  })) {
    const values = options?.[section];
    if (!values || typeof values !== 'object' || Array.isArray(values)) continue;
    for (const [from, to] of Object.entries(keys)) {
      const value = (values as Record<string, unknown>)[from];
      if (typeof value === typeof manual[to as keyof ChatSettings]) Object.assign(effective, {[to]: value});
    }
  }
  return settingsErrors(effective).length ? manual : effective;
}
