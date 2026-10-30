/** Exact captured synthetic API bytes through the real C21 frontend parser/client. */
import { readFileSync, writeFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { parseEvidenceModel } from '../../../../../frontend-v1/src/research-evidence-contract.ts';
import { createAnswerClient, createEvidenceClient } from '../../../../../frontend-v1/src/research-evidence-service.ts';
import { loadAnswerHistory } from '../../../../../frontend-v1/src/research-answer-history.ts';

const [input, output] = process.argv.slice(2).map(value => resolve(value));
if (!input?.startsWith('/private/tmp/') || !output?.startsWith('/private/tmp/')) {
  throw new Error('Explicit private/tmp synthetic capture paths required');
}
const capture = JSON.parse(readFileSync(input, 'utf8'));
if (capture.live_calls_performed !== false || capture.classification !== 'synthetic-local-actual-services') {
  throw new Error('Explicit synthetic capture classification required');
}
const observations = [];
for (const item of capture.cases) {
  const observation = { id: item.id, api_status: item.status };
  const group = item.group ?? 'answers', action = item.action ?? 'list';
  const model = group === 'answers' ? ({ list: 'AnswerListResponse', events: 'AnswerEventsResponse',
    submit: 'AnswerResponse', status: 'AnswerResponse', cancel: 'AnswerResponse' })[action]
    : ({ list: 'EvidenceListResponse', open: 'EvidenceResponse', page: 'EvidencePageResponse' })[action];
  for (const mode of ['schema', 'client']) {
    try {
      const result = mode === 'schema'
        ? await parseEvidenceModel(model, JSON.parse(item.response_text))
        : await (group === 'answers' ? createAnswerClient : createEvidenceClient)({ fetcher: async () => new Response(item.response_text, {
          status: item.status, headers: { 'Content-Type': 'application/json' },
        }) })[action](item.request);
      observation[mode] = { status: 'passed', run_id: result.run_id,
        items: result.items?.length, receipt_id: result.receipt?.id };
    } catch (error) {
      observation[mode] = { status: 'failed', type: error.name, code: error.code,
        status_code: error.status_code, message: error.message };
    }
  }
  observations.push(observation);
}
const hydrations = {};
for (const phase of ['mixed-native-experimental-context', 'mixed-native-experimental-prepared-answer']) {
  const mixed = capture.cases.filter(item => item.id.startsWith(phase + ':'));
  if (!mixed.some(item => item.group === 'evidence' && item.action === 'list')) continue;
  const answer = mixed.find(item => item.group === 'answers' && item.action === 'list');
  const canonical = value => JSON.stringify(Object.fromEntries(Object.entries(value).sort(([a], [b]) => a.localeCompare(b))));
  const fetcher = async (path, init) => {
    const item = mixed.find(value => path === `/research/${value.group}/${value.action}`);
    if (!item || canonical(JSON.parse(init.body)) !== canonical(item.request)) {
      throw new Error('No exact captured request for actual client hydration');
    }
    return new Response(item.response_text, { status: item.status, headers: { 'Content-Type': 'application/json' } });
  };
  try {
    const { investigation_id, conversation_id, run_id } = answer.request;
    const result = await loadAnswerHistory({ answers: createAnswerClient({ fetcher }),
      evidence: createEvidenceClient({ fetcher }), address: { investigation_id, conversation_id, run_id },
      pages: 1, receiptLimit: 100, selectedJobId: null, cached: [], expectedAccessRevision: null,
      signal: new AbortController().signal, isCurrent: () => true });
    hydrations[phase] = { status: 'passed', views: result.views.length,
      receipts: result.receipts.map(item => item.id), run_id: result.listing.run_id };
  } catch (error) {
    hydrations[phase] = { status: 'failed', type: error.name, code: error.code, message: error.message };
  }
}
const hydration = hydrations['mixed-native-experimental-context'];
writeFileSync(output, JSON.stringify({ version: 'c26-mixed-answer-parser-diagnostic-v1',
  input, source_revision: capture.source_revision, observations, hydration, hydrations }, null, 2) + '\n', { flag: 'wx' });
console.log(JSON.stringify({ observations, hydration, hydrations }));
