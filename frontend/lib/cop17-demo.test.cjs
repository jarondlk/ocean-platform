process.env.NEXT_PUBLIC_COP17_DEMO = "true";
// Exercise the real page and storage hook, including asynchronous account changes.
const assert = require('node:assert/strict');
const {test, after} = require('node:test');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const ts = require('typescript');
const React = require('react');
const {create, act} = require('react-test-renderer');
global.IS_REACT_ACT_ENVIRONMENT = true;
const temp = fs.mkdtempSync(path.join(os.tmpdir(), 'ocean-auto-chat-'));
after(() => fs.rmSync(temp, {recursive: true, force: true}));
const root = path.resolve(__dirname, '..');
const modules = {
  '@/components/ChatIdentityProvider': 'identity.cjs', '@/lib/use-chat-settings': 'hook.cjs',
  './chat-settings': 'settings.cjs', './chat-settings.ts': 'settings.cjs', '@/lib/chat-settings': 'settings.cjs',
  './generated/chat-scope.ts': 'scope.cjs', '@/lib/generated/chat-scope': 'scope.cjs',
  '@/lib/auto-settings': 'auto.cjs', '@/lib/api': 'api.cjs', '@/lib/preferences': 'preferences.cjs',
  '@/lib/chat-filter-options': 'options.cjs', '@/components/ChatFilterSelect': 'select.cjs',
  '@/components/ChatSourceSettings': 'sources.cjs', '@/lib/citation-navigation': 'citations.cjs',
  '@/lib/chat-presentation': 'presentation.cjs',
};
for (const name of ['CsvExportButton', 'ChatFeedback', 'DataTable', 'EvidenceNavigator', 'MarkdownAnswer',
  'SourceTable', 'ResearchResultCards', 'SourceCoverage']) modules[`@/components/${name}`] = 'components.cjs';
function compile(source, name) {
  let code = ts.transpileModule(fs.readFileSync(path.join(root, source), 'utf8'), {
    compilerOptions: {module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX, target: ts.ScriptTarget.ES2022},
  }).outputText;
  for (const [from, to] of Object.entries(modules)) code = code.replaceAll(`require("${from}")`, `require(${JSON.stringify(path.join(temp, to))})`);
  for (const external of ['react', 'react/jsx-runtime', 'lucide-react']) code = code.replaceAll(`require("${external}")`, `require(${JSON.stringify(require.resolve(external))})`);
  fs.writeFileSync(path.join(temp, name), code);
}
for (const [source, name] of Object.entries({
  'components/ChatIdentityProvider.tsx': 'identity.cjs', 'lib/generated/chat-scope.ts': 'scope.cjs',
  'lib/chat-settings.ts': 'settings.cjs', 'lib/use-chat-settings.ts': 'hook.cjs', 'lib/auto-settings.ts': 'auto.cjs',
  'lib/chat-filter-options.ts': 'options.cjs', 'components/ChatFilterSelect.tsx': 'select.cjs',
  'components/ChatSourceSettings.tsx': 'sources.cjs', 'app/chat/page.tsx': 'page.cjs',
})) compile(source, name);
fs.writeFileSync(path.join(temp, 'preferences.cjs'), 'exports.useAppPreferences = () => ({ui: text => text, preferences: {locale: "en"}, setPreference() {}});');
fs.writeFileSync(path.join(temp, 'api.cjs'), `
exports.ApiError = class ApiError extends Error {};
exports.getModels = async () => ({models: [{name: 'mock'}], default_model: 'mock', provider: 'ollama'});
exports.getChatCapabilities = async () => ({scope_version: 1, max_output_tokens: 8192, generation_fields: [], auto_settings: {enabled: true, plan_version: 1}});
exports.request = async () => ({options: global.autoAnalysisOptions || []});
exports.getChatFilterOptions = async () => ({sources: Object.fromEntries(['ctd', 'metagenome', 'remote_sensing', 'edna_metabarcoding'].map(f => [f, {available: true, fields: {}}]))});
exports.askQuestion = (...args) => global.autoChatRequest(...args);
`);
fs.writeFileSync(path.join(temp, 'citations.cjs'), 'exports.buildCitationTargetIndex = () => new Map(); exports.sourceTarget = () => null;');
fs.writeFileSync(path.join(temp, 'presentation.cjs'), 'exports.abstentionReasonLabel = s => s; exports.appliedFilterRows = () => [];');
fs.writeFileSync(path.join(temp, 'components.cjs'), `
const React = require(${JSON.stringify(require.resolve('react'))});
for (const name of ['CsvExportButton', 'ChatFeedback', 'DataTable', 'EvidenceNavigator', 'MarkdownAnswer', 'SourceTable', 'ResearchResultCards', 'SourceCoverage']) exports[name] = props => React.createElement('div', null, props.text || props.children);
exports.formatCell = value => String(value);
`);
const {ChatIdentityProvider} = require(path.join(temp, 'identity.cjs'));
const {defaultScope, defaultSettings, encodeSettings, settingsStorageKey, fixedDemoSetup, cop17AnalysisId, cop17ProtocolId} = require(path.join(temp, 'settings.cjs'));
const {ChatSourceSettings} = require(path.join(temp, 'sources.cjs'));
const ChatPage = require(path.join(temp, 'page.cjs')).default;
function storage() {
  const empty = defaultScope();
  for (const item of Object.values(empty.sources)) item.enabled = false;
  const values = new Map([[settingsStorageKey('A'), encodeSettings({...defaultSettings, autoSettings: true}, empty)]]);
  global.window = {location: {search: ''}, localStorage: {
    getItem: key => values.get(key) ?? null, setItem: (key, value) => values.set(key, value),
  }};
  return {values, empty};
}
const tree = accountId => React.createElement(ChatIdentityProvider, {accountId}, React.createElement(ChatPage));
function answer() {
  const chosen = defaultScope();
  for (const [family, item] of Object.entries(chosen.sources)) item.enabled = family === 'ctd';
  chosen.sources.ctd.filters = {station: 'A1'};
  return {query: 'CTD salinity', answer: 'Account A private result', n_sources: 0, sources: [],
    options: {planning: {status: 'applied', explanation: 'Use CTD salinity.'}, evidence_scope: chosen,
      retrieval: {k: 8}, context: {inject_analysis: false}}, outcome: 'answered'};
}
async function submit(renderer, query = 'CTD salinity') {
  await act(async () => renderer.root.findByType('textarea').props.onChange({target: {value: query}}));
  await act(async () => renderer.root.findByType('form').props.onSubmit({preventDefault() {}}));
}


function demoOptions() {
  const analysis = cop17AnalysisId, protocol = cop17ProtocolId;
  return [{analysis_id: analysis, status: 'current', analysis_kind: 'regional_frequency',
    label: 'MUR v4.1 · Miyagi · 2020–2023', publication_id: 'accepted',
    assignment_methods: ['qcauto_95pct_3nn_target'], protocol_ids: [protocol],
    protocols: {[protocol]: {target_gene: '12S rRNA', sequencing_method: 'MiSeq', library_layout: 'paired'}},
    sst_available: true, sst_dataset_id: 'mur-miyagi-2020-2023',
    workflows: [{kind: 'fish_frequency', question: 'Show the top 10 fish by detection frequency, with yearly and seasonal changes'},
      {kind: 'temperature_comparison', question: 'Compare fish detection frequency in high and low SST conditions and show a representative series'}]}];
}
function freshStorage() {
  const values = new Map();
  global.window = {location: {search: ''}, localStorage: {
    getItem: key => values.get(key) ?? null, setItem: (key, value) => values.set(key, value),
  }};
  return values;
}
function button(renderer, label) {return renderer.root.findAllByType('button').find(b => b.children.filter(c => typeof c === 'string').join('') === label);}

test('one click selects the fixed published setup; free-text clears pins and preserves a custom question', async () => {
  freshStorage(); global.autoAnalysisOptions = demoOptions();
  const requests = []; global.autoChatRequest = async request => {requests.push(request); return {answer: 'Verified', n_sources: 0, sources: []};};
  let renderer;
  try {
    await act(async () => {renderer = create(tree('demo'));});
    const labels = renderer.root.findAllByType('label').map(l => l.children.filter(c => typeof c === 'string').join('')).join(' ');
    assert(!labels.includes('CTD') && !labels.includes('Metagenome'));
    assert.equal(renderer.root.findAllByProps({className: 'chat-advanced'}).length, 0);
    await act(async () => button(renderer, 'Fish and sea surface temperature').props.onClick());
    await act(async () => renderer.root.findByType('form').props.onSubmit({preventDefault() {}}));
    assert.equal(requests.length, 1);
    assert.equal(requests[0].settings_mode, 'manual');
    assert.deepEqual(requests[0].research_intent, {kind: 'temperature_comparison', protocol_id: cop17ProtocolId});
    assert.equal(requests[0].evidence_scope.sources.edna_metabarcoding.analysis_id, cop17AnalysisId);
    assert.equal(requests[0].evidence_scope.sources.remote_sensing.filters.dataset_id, 'mur-miyagi-2020-2023');
    assert.equal(requests[0].evidence_scope.sources.ctd.enabled, false);
    await act(async () => renderer.root.findByType('textarea').props.onChange({target: {value: 'My own ANEMONE question'}}));
    await act(async () => button(renderer, 'Return to free-text search').props.onClick());
    await act(async () => renderer.root.findByType('form').props.onSubmit({preventDefault() {}}));
    assert.equal(requests[1].query, 'My own ANEMONE question');
    assert.equal(requests[1].research_intent, undefined);
    assert.equal(requests[1].evidence_scope.sources.edna_metabarcoding.analysis_id, undefined);
  } finally {await act(async () => renderer?.unmount()); delete global.autoAnalysisOptions; delete global.autoChatRequest;}
});

test('missing or incompatible fixed setup never substitutes another dataset or assay', async () => {
  const good = demoOptions();
  assert.equal(fixedDemoSetup(good).protocolId, cop17ProtocolId);
  for (const patch of [
    {analysis_id: 'c'.repeat(64)}, {status: 'stale'}, {assignment_methods: ['qcauto_target']},
    {assignment_methods: ['qcauto_95pct_3nn_target', 'qcauto_target']}, {protocol_ids: ['d'.repeat(64)]},
    {protocols: {[cop17ProtocolId]: {sequencing_method: 'NovaSeq', library_layout: 'paired'}}},
  ]) assert.equal(fixedDemoSetup([{...good[0], ...patch}]), undefined);
  assert.equal(fixedDemoSetup([...good, ...good]), undefined);
  freshStorage(); global.autoAnalysisOptions = [{...good[0], protocol_ids: ['d'.repeat(64)]}];
  const requests = []; global.autoChatRequest = async request => {requests.push(request); return {answer: 'Retrieved', n_sources: 0, sources: []};};
  let renderer;
  try {
    await act(async () => {renderer = create(tree('demo'));});
    assert(button(renderer, 'Fish detection frequency').props.disabled);
    assert(button(renderer, 'Fish and sea surface temperature').props.disabled);
    assert.equal(button(renderer, 'Free-text search').props['aria-pressed'], true);
    await submit(renderer, 'My own question');
    assert.equal(requests[0].research_intent, undefined);
    assert.equal(requests[0].evidence_scope.sources.edna_metabarcoding.analysis_id, undefined);
  } finally {await act(async () => renderer?.unmount()); delete global.autoAnalysisOptions; delete global.autoChatRequest;}
});

test('settings contains demo controls while the question leads the main column; free text has no published pins', async () => {
  freshStorage(); global.autoAnalysisOptions = demoOptions();
  const requests = []; global.autoChatRequest = async request => {requests.push(request); return {answer: 'Retrieved', n_sources: 0, sources: []};};
  let renderer;
  try {
    await act(async () => {renderer = create(tree('demo'));});
    const card = renderer.root.findAllByType('article')[0];
    const sidebar = renderer.root.findByType('aside');
    const modes = sidebar.findByProps({className: 'cop17-modes'});
    assert.equal(card.findAllByProps({className: 'cop17-modes'}).length, 0);
    assert.equal(card.findAllByProps({className: 'cop17-banner'}).length, 0);
    assert.equal(sidebar.findAllByProps({className: 'cop17-banner'}).length, 1);
    assert.equal(sidebar.findAllByProps({'aria-label': 'Language'}).length, 0);
    assert.equal(card.findByType('textarea').props.id, 'query-input');
    assert.equal(modes.findAllByType('button').length, 3);
    assert.equal(renderer.root.findAllByProps({id: 'chat-demo-setup'}).length, 0);
    assert.equal(modes.findAllByType('details').length, 0);
    assert.equal(button(renderer, 'Free-text search').props['aria-pressed'], true);
    assert.equal(button(renderer, 'Fish detection frequency').props['aria-pressed'], false);
    await submit(renderer, 'My own ANEMONE question');
    assert.equal(requests[0].research_intent, undefined);
    assert.equal(requests[0].evidence_scope.sources.edna_metabarcoding.analysis_id, undefined);
    assert.deepEqual(requests[0].evidence_scope.sources.remote_sensing.filters, {});
    await act(async () => button(renderer, 'Fish detection frequency').props.onClick());
    assert.equal(button(renderer, 'Fish detection frequency').props['aria-pressed'], true);
    assert.equal(button(renderer, 'Free-text search').props['aria-pressed'], false);
    await act(async () => renderer.root.findByType('form').props.onSubmit({preventDefault() {}}));
    assert.equal(requests[1].research_intent.protocol_id, cop17ProtocolId);
    assert.equal(requests[1].evidence_scope.sources.edna_metabarcoding.analysis_id, cop17AnalysisId);
    assert.equal(requests[1].evidence_scope.sources.remote_sensing.enabled, false);
  } finally {await act(async () => renderer?.unmount()); delete global.autoAnalysisOptions; delete global.autoChatRequest;}
});

test('returning from an untouched example restores the free-text draft and scope without preset pins', async () => {
  const values = freshStorage(); global.autoAnalysisOptions = demoOptions();
  const freeScope = defaultScope();
  freeScope.sources.remote_sensing.enabled = false;
  freeScope.sources.edna_metabarcoding.filters = {sample_id: 'chosen-sample'};
  values.set(settingsStorageKey('demo'), encodeSettings(defaultSettings, freeScope));
  const requests = []; global.autoChatRequest = async request => {requests.push(request); return {answer: 'Retrieved', n_sources: 0, sources: []};};
  let renderer;
  try {
    await act(async () => {renderer = create(tree('demo'));});
    await act(async () => renderer.root.findByType('textarea').props.onChange({target: {value: 'My original question'}}));
    await act(async () => button(renderer, 'Fish and sea surface temperature').props.onClick());
    await act(async () => renderer.root.findByType('form').props.onSubmit({preventDefault() {}}));
    assert.equal(requests[0].research_intent.kind, 'temperature_comparison');
    await act(async () => button(renderer, 'Return to free-text search').props.onClick());
    assert.equal(renderer.root.findByType('textarea').props.value, 'My original question');
    assert.equal(button(renderer, 'Free-text search').props['aria-pressed'], true);
    await act(async () => renderer.root.findByType('form').props.onSubmit({preventDefault() {}}));
    assert.deepEqual(requests[1].evidence_scope, freeScope);
    assert.equal(requests[1].research_intent, undefined);
    // A later account must not inherit this draft, even while an example is active.
    await act(async () => button(renderer, 'Fish detection frequency').props.onClick());
    await act(async () => renderer.update(tree('other-account')));
    assert.equal(renderer.root.findByType('textarea').props.value, '');
    await submit(renderer, 'New account question');
    assert.equal(requests[2].research_intent, undefined);
    assert.equal(requests[2].evidence_scope.sources.edna_metabarcoding.analysis_id, undefined);
    assert.deepEqual(requests[2].evidence_scope.sources.edna_metabarcoding.filters, {});
  } finally {await act(async () => renderer?.unmount()); delete global.autoAnalysisOptions; delete global.autoChatRequest;}
});

test('an explicit analysis link retains its context until the visitor returns to free text', async () => {
  freshStorage(); global.autoAnalysisOptions = demoOptions();
  global.window.location.search = '?analysis_id=' + cop17AnalysisId;
  const requests = []; global.autoChatRequest = async request => {requests.push(request); return {answer: 'Published', n_sources: 0, sources: []};};
  let renderer;
  try {
    await act(async () => {renderer = create(tree('demo'));});
    assert.equal(button(renderer, 'Free-text search').props['aria-pressed'], false);
    await submit(renderer, 'Question for the linked analysis');
    assert.equal(requests[0].evidence_scope.sources.edna_metabarcoding.analysis_id, cop17AnalysisId);
    await act(async () => button(renderer, 'Return to free-text search').props.onClick());
    await submit(renderer, 'My own question');
    assert.equal(requests[1].evidence_scope.sources.edna_metabarcoding.analysis_id, undefined);
    assert.equal(requests[1].research_intent, undefined);
  } finally {await act(async () => renderer?.unmount()); delete global.autoAnalysisOptions; delete global.autoChatRequest;}
});
