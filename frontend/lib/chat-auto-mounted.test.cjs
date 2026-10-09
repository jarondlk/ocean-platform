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
fs.writeFileSync(path.join(temp, 'preferences.cjs'), 'exports.useAppPreferences = () => ({ui: text => text});');
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
const {defaultScope, defaultSettings, encodeSettings, settingsStorageKey} = require(path.join(temp, 'settings.cjs'));
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

test('AUTO displays applied settings; toggling off restores manual, editing copies the result', async () => {
  const {values, empty} = storage();
  const requests = [];
  global.autoChatRequest = async request => {requests.push(request); return answer();};
  let renderer;
  try {
    await act(async () => {renderer = create(tree('A'));});
    await submit(renderer);
    assert.equal(requests.length, 1);
    assert.equal(requests[0].settings_mode, 'auto');
    assert.deepEqual(requests[0].evidence_scope, empty);
    assert.equal(renderer.root.findByType(ChatSourceSettings).props.scope.sources.ctd.enabled, true);
    assert.equal(JSON.parse(values.get(settingsStorageKey('A'))).scope.sources.ctd.enabled, false);
    await act(async () => renderer.root.findByType(ChatSourceSettings).props.onAutoChange(false));
    assert.equal(renderer.root.findByType(ChatSourceSettings).props.scope.sources.ctd.enabled, false);
    await act(async () => renderer.root.findByType(ChatSourceSettings).props.onAutoChange(true));
    const scope = structuredClone(renderer.root.findByType(ChatSourceSettings).props.scope);
    scope.sources.ctd.filters.station = 'A2';
    await act(async () => renderer.root.findByType(ChatSourceSettings).props.onChange(scope));
    const saved = JSON.parse(values.get(settingsStorageKey('A')));
    assert.equal(saved.settings.autoSettings, false);
    assert.equal(saved.settings.k, 8);
    assert.equal(saved.settings.injectAnalysis, false);
    assert.equal(saved.scope.sources.ctd.filters.station, 'A2');
    assert.equal(saved.scope.sources.metagenome.enabled, false);
    assert.equal(renderer.root.findByType(ChatSourceSettings).props.autoEnabled, false);
  } finally {await act(async () => renderer?.unmount()); delete global.autoChatRequest;}
});

test('a late AUTO response cannot appear or change settings after switching accounts', async () => {
  const {values} = storage();
  let resolve;
  global.autoChatRequest = () => new Promise(done => {resolve = done;});
  let renderer;
  try {
    await act(async () => {renderer = create(tree('A'));});
    await submit(renderer);
    assert.equal(typeof resolve, 'function');
    await act(async () => renderer.update(tree('B')));
    await act(async () => resolve(answer()));
    assert(!JSON.stringify(renderer.toJSON()).includes('Account A private result'));
    const settings = renderer.root.findByType(ChatSourceSettings).props;
    assert.equal(settings.autoEnabled, false);
    assert.equal(settings.scope.sources.ctd.filters.station, undefined);
    assert.equal(JSON.parse(values.get(settingsStorageKey('B'))).settings.autoSettings, false);
  } finally {await act(async () => renderer?.unmount()); delete global.autoChatRequest;}
});

test('fresh AUTO renders selected published analysis, workflow and default protocol without manual pins', async () => {
  const {empty, values} = storage();
  const analysis = 'a'.repeat(64), protocol = 'b'.repeat(64);
  global.autoAnalysisOptions = [{analysis_id: analysis, status: 'current', analysis_kind: 'regional_frequency',
    label: 'MUR v4.1 · Miyagi · 2020–2023', protocol_ids: [protocol, 'c'.repeat(64)],
    protocol_labels: {[protocol]: '12S · First protocol'},
    workflows: [{kind: 'fish_frequency', question: 'Show the top 10 fish'},
      {kind: 'temperature_comparison', question: 'Compare high and low SST'}]}];
  const requests = [];
  global.autoChatRequest = async request => {
    requests.push(request);
    const kind = requests.length === 1 ? 'fish_frequency' : 'temperature_comparison';
    const chosen = structuredClone(empty);
    chosen.sources.edna_metabarcoding = {enabled: true, filters: {}, analysis_id: analysis};
    chosen.sources.remote_sensing.enabled = kind === 'temperature_comparison';
    return {...answer(), options: {evidence_scope: chosen,
      planning: {status: 'applied', explanation: 'Using the first protocol by default.',
        research_intent: {kind, protocol_id: protocol}}}};
  };
  let renderer;
  try {
    await act(async () => {renderer = create(tree('A'));});
    for (const [query, kind] of [['Show the top 10 fish by detection frequency, with yearly and seasonal changes', 'fish_frequency'],
      ['Compare fish detection frequency in high and low SST conditions and show a representative series', 'temperature_comparison']]) {
      await submit(renderer, query);
      const controls = renderer.root.findByType(ChatSourceSettings).props;
      assert.equal(controls.analysisId, analysis);
      assert.deepEqual(controls.researchIntent, {kind, protocol_id: protocol});
      assert.equal(renderer.root.findByProps({id: 'chat-analysis-id'}).props.value, analysis);
      assert.equal(renderer.root.findAllByType('select').find(s => s.props.value === kind).props.value, kind);
      assert.equal(renderer.root.findAllByType('select').find(s => s.props.value === protocol).props.value, protocol);
      assert(controls.autoEnabled);
    }
    assert(requests.every(r => r.research_intent === undefined));
    assert(requests.every(r => JSON.stringify(r.evidence_scope) === JSON.stringify(empty)));
    assert.deepEqual(JSON.parse(values.get(settingsStorageKey('A'))).scope, empty);
  } finally {await act(async () => renderer?.unmount()); delete global.autoChatRequest; delete global.autoAnalysisOptions;}
});
