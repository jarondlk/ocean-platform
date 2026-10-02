// Mount the real hook/components: serialization tests cannot exercise effects.
const assert = require('node:assert/strict');
const {test, after} = require('node:test');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const ts = require('typescript');
const React = require('react');
const {create, act} = require('react-test-renderer');
global.IS_REACT_ACT_ENVIRONMENT = true;
const temp = fs.mkdtempSync(path.join(os.tmpdir(), 'ocean-settings-'));
after(() => fs.rmSync(temp, {recursive: true, force: true}));
const root = path.resolve(__dirname, '..');
const modules = {
  '@/components/ChatIdentityProvider': 'identity.cjs', './chat-settings': 'settings.cjs',
  './generated/chat-scope.ts': 'scope.cjs', '@/lib/api': 'api.cjs',
  '@/lib/preferences': 'preferences.cjs', '@/lib/chat-filter-options': 'options.cjs',
};
function compile(source, name) {
  let code = ts.transpileModule(fs.readFileSync(path.join(root, source), 'utf8'), {
    compilerOptions: {module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX, target: ts.ScriptTarget.ES2022},
  }).outputText;
  for (const [from, to] of Object.entries(modules)) code = code.replaceAll(`require("${from}")`, `require(${JSON.stringify(path.join(temp, to))})`);
  for (const external of ['react', 'react/jsx-runtime']) code = code.replaceAll(`require("${external}")`, `require(${JSON.stringify(require.resolve(external))})`);
  fs.writeFileSync(path.join(temp, name), code);
}
compile('components/ChatIdentityProvider.tsx', 'identity.cjs');
compile('lib/generated/chat-scope.ts', 'scope.cjs');
compile('lib/chat-settings.ts', 'settings.cjs');
compile('lib/use-chat-settings.ts', 'hook.cjs');
compile('lib/chat-filter-options.ts', 'options.cjs');
fs.writeFileSync(path.join(temp, 'preferences.cjs'), 'exports.useAppPreferences = () => ({ui: text => text});');
fs.writeFileSync(path.join(temp, 'api.cjs'), 'exports.getChatFilterOptions = (...args) => global.filterRequest(...args);');
compile('components/ChatFilterSelect.tsx', 'select.cjs');
const {ChatIdentityProvider} = require(path.join(temp, 'identity.cjs'));
const {useChatSettings} = require(path.join(temp, 'hook.cjs'));
const {defaultScope, defaultSettings, encodeSettings, settingsStorageKey} = require(path.join(temp, 'settings.cjs'));
const {ChatFilterSelect} = require(path.join(temp, 'select.cjs'));
function stored(enabled) {
  const scope = defaultScope();
  for (const source of Object.values(scope.sources)) source.enabled = enabled;
  return encodeSettings(defaultSettings, scope);
}
function storage(entries = {}) {
  const values = new Map(Object.entries(entries)), writes = [];
  global.window = {localStorage: {getItem: key => values.get(key) ?? null, setItem: (key, value) => {writes.push([key, value]); values.set(key, value);}}};
  return {values, writes};
}
test('account transitions never render or save the previous account scope; missing identity blocks submission', async () => {
  const a = settingsStorageKey('A'), b = settingsStorageKey('B');
  const {values, writes} = storage({[a]: stored(false), [b]: stored(true)});
  let current; const renders = [];
  function Probe({account}) {current = useChatSettings(''); renders.push({account, ready: current.ready, enabled: current.scope.sources.ctd.enabled}); return null;}
  const tree = account => React.createElement(ChatIdentityProvider, {accountId: account}, React.createElement(Probe, {account}));
  let renderer;
  try {
    await act(() => {renderer = create(tree('A'));});
    assert.equal(current.ready, true); assert.equal(current.scope.sources.ctd.enabled, false);
    await act(() => renderer.update(tree('B')));
    assert.equal(current.scope.sources.ctd.enabled, true);
    assert(renders.filter(r => r.account === 'B').every(r => !r.ready || r.enabled));
    assert(writes.filter(([key]) => key === b).every(([, raw]) => JSON.parse(raw).scope.sources.ctd.enabled));
    assert.equal(JSON.parse(values.get(a)).scope.sources.ctd.enabled, false);
    await act(() => renderer.update(tree(null)));
    assert.equal(current.ready, false);
    assert.equal(current.scope.sources.ctd.enabled, true);
  } finally {await act(() => renderer?.unmount());}
});
test('corrupt account settings block writes, reset is explicit and notices do not leak between accounts', async () => {
  const {values} = storage({[settingsStorageKey('broken')]: '{broken'});
  let current, renderer;
  function Probe() {current = useChatSettings(''); return null;}
  const tree = accountId => React.createElement(ChatIdentityProvider, {accountId}, React.createElement(Probe));
  try {
    await act(() => {renderer = create(tree('broken'));});
    assert(current.blocked); assert.equal(values.get(settingsStorageKey('broken')), '{broken');
    await act(() => current.reset('model'));
    assert.equal(current.blocked, ''); assert.equal(current.settings.model, 'model');
    window.localStorage.getItem = () => {throw new Error('denied');};
    window.localStorage.setItem = () => {throw new Error('denied');};
    await act(() => renderer.update(tree('denied')));
    assert.equal(current.ready, true); assert(current.storageNotice); assert.equal(current.blocked, '');
    await act(() => current.setScope(JSON.parse(stored(false)).scope));
    assert.equal(current.scope.sources.ctd.enabled, false);
    storage();
    await act(() => renderer.update(tree('clean')));
    assert.equal(current.storageNotice, ''); assert.equal(current.scope.sources.ctd.enabled, true);
  } finally {await act(() => renderer?.unmount());}
});
test('analysis-linked scope changes stay transient; reset also resets the retained defaults', async () => {
  const key = settingsStorageKey('A'); const {values} = storage({[key]: stored(false)});
  let current, renderer;
  function Probe({analysis}) {current = useChatSettings(analysis); return null;}
  const tree = analysis => React.createElement(ChatIdentityProvider, {accountId: 'A'}, React.createElement(Probe, {analysis}));
  try {
    await act(() => {renderer = create(tree(''));});
    await act(() => renderer.update(tree('a'.repeat(64))));
    await act(() => current.setScope(defaultScope()));
    assert.equal(JSON.parse(values.get(key)).scope.sources.ctd.enabled, false);
    await act(() => current.reset('model'));
    assert.equal(JSON.parse(values.get(key)).scope.sources.ctd.enabled, true);
  } finally {await act(() => renderer?.unmount());}
});
test('an aborted filter search cannot replace current choices, even if the transport resolves late', async () => {
  const calls = []; global.filterRequest = (request, signal) => new Promise(resolve => calls.push({request, signal, resolve}));
  const props = {id: 'taxon', family: 'edna_metabarcoding', field: 'taxon', label: 'Taxon', value: 'saved-taxon',
    choices: {values: ['base'], truncated: true}, scopeJson: '{}', loading: false, failed: false, invalidScope: false, onChange: () => {}};
  let renderer;
  const delay = () => new Promise(resolve => setTimeout(resolve, 280));
  try {
    await act(() => {renderer = create(React.createElement(ChatFilterSelect, props));});
    await act(() => renderer.root.findByType('input').props.onChange({target: {value: 'first'}}));
    await act(delay);
    await act(() => renderer.root.findByType('input').props.onChange({target: {value: 'second'}}));
    await act(delay);
    assert.equal(calls.length, 2); assert.equal(calls[0].signal.aborted, true);
    const response = value => ({sources: {edna_metabarcoding: {fields: {taxon: {values: [value], truncated: false}}}}});
    await act(async () => {calls[1].resolve(response('current'));});
    await act(async () => {calls[0].resolve(response('stale'));});
    const options = renderer.root.findAllByType('option').map(option => option.props.value);
    assert(options.includes('current') && options.includes('saved-taxon')); assert(!options.includes('stale'));
    assert.equal(renderer.root.findByType('select').props.disabled, false);
  } finally {await act(() => renderer?.unmount()); delete global.filterRequest;}
});
