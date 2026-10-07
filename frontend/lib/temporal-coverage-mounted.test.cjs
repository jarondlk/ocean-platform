const assert = require('node:assert/strict');
const {test, after} = require('node:test');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const ts = require('typescript');
const React = require('react');
const {create, act} = require('react-test-renderer');
global.IS_REACT_ACT_ENVIRONMENT = true;
const root = path.resolve(__dirname, '..');
const temp = fs.mkdtempSync(path.join(os.tmpdir(), 'ocean-temporal-ui-'));
after(() => fs.rmSync(temp, {recursive:true, force:true}));
function compile(source, output) {
  let code = ts.transpileModule(fs.readFileSync(path.join(root, source), 'utf8'), {
    compilerOptions:{module:ts.ModuleKind.CommonJS, jsx:ts.JsxEmit.ReactJSX, target:ts.ScriptTarget.ES2022},
  }).outputText;
  for (const [from,to] of Object.entries({'@/lib/temporal-coverage':'coverage.cjs','@/lib/preferences':'preferences.cjs','@/lib/api':'api.cjs'})) {
    code = code.replaceAll(`require("${from}")`, `require(${JSON.stringify(path.join(temp,to))})`);
  }
  for (const external of ['react','react/jsx-runtime']) code = code.replaceAll(`require("${external}")`, `require(${JSON.stringify(require.resolve(external))})`);
  fs.writeFileSync(path.join(temp,output),code);
}
fs.writeFileSync(path.join(temp,'preferences.cjs'), 'exports.useAppPreferences = () => ({ui: text => text});');
fs.writeFileSync(path.join(temp,'api.cjs'), 'exports.getOverviewCoverage = () => global.__coverageRequest();');
compile('lib/temporal-coverage.ts','coverage.cjs');
compile('components/TemporalCoverageTimeline.tsx','component.cjs');
const {TemporalCoverageTimeline, OverviewTemporalCoverage} = require(path.join(temp,'component.cjs'));
function text(node) {return typeof node === 'string' ? node : (node?.children || []).map(text).join('');}
function source(id, months, status='available') {
  return {id,label:id,count_unit:'samples',temporal_precision:'month',date_basis:'month',scope:'fixture',status,reason:null,
    observed_start:months[0] || null,observed_end:months.at(-1) || null,total_count:status==='unavailable'?null:months.length,
    bins:months.map(month=>({month,count:1,observed_days:null})),undated_count:0,excluded_count:0,categories:{},source_binding:{},
    missing_dates_within_extent:[],missing_day_count:null,missing_dates_truncated:false};
}
function payload(rows) {return {calendar:'Asia/Tokyo',resolution:'month',generated_at:'2026-10-07T01:00:00+00:00',sources:rows};}

test('mounted selection preserves unavailable sources, then computes populated-month intersection', async () => {
  let renderer;
  try {
    await act(() => {renderer = create(React.createElement(TemporalCoverageTimeline,{coverage:payload([
      source('ctd',['2026-01','2026-02']),source('metagenome',['2026-02']),source('edna_metabarcoding',[],'unavailable'),source('remote_sensing',['2026-02'])
    ]),onRefresh:()=>{}}));});
    assert.match(text(renderer.toJSON()),/Shared months are unknown/);
    const edna = renderer.root.findAllByType('input')[2];
    assert.equal(edna.props.checked,true);
    await act(() => edna.props.onChange({target:{checked:false}}));
    assert.match(text(renderer.toJSON()),/Months with records in all selected sources: 1/);
    const month = renderer.root.findAllByType('button').find(node=>node.props['aria-label']==='metagenome · 2026-02: 1 samples');
    await act(() => month.props.onFocus());
    assert.match(text(renderer.root.findByProps({'aria-live':'polite'})),/Date precision: month/);
    assert.equal(month.props.tabIndex,0);
  } finally {await act(() => renderer?.unmount());}
});

test('refresh loads replacement coverage and failed refresh clears stale claims', async () => {
  let renderer;
  let response = payload([source('ctd',['2026-01']),source('metagenome',['2026-01'])]);
  global.__coverageRequest = async () => response;
  try {
    await act(async () => {renderer = create(React.createElement(OverviewTemporalCoverage));});
    // Select only the available fixture sources.
    assert.match(text(renderer.toJSON()),/ctd/);
    response = payload([source('ctd',['2026-02']),source('metagenome',['2026-02'])]);
    await act(async () => renderer.root.findAllByType('button')[0].props.onClick());
    assert.match(text(renderer.toJSON()),/2026-02/);
    assert.doesNotMatch(text(renderer.toJSON()),/2026-01/);
    global.__coverageRequest = async () => {throw new Error('private/path');};
    await act(async () => renderer.root.findAllByType('button')[0].props.onClick());
    assert.match(text(renderer.root.findByProps({role:'alert'})),/Unable to load source coverage/);
    assert.equal(renderer.root.findAllByType('table').length,0);
    assert.doesNotMatch(text(renderer.toJSON()),/private\/path/);
  } finally {await act(() => renderer?.unmount()); delete global.__coverageRequest;}
});
