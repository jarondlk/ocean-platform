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
const temp = fs.mkdtempSync(path.join(os.tmpdir(), 'ocean-research-ui-'));
after(() => fs.rmSync(temp, {recursive:true, force:true}));
const aliases = {
  '@/components/ResearchFrequencyPlot':'plots.cjs', '@/components/DataTable':'table.cjs',
  '@/lib/preferences':'preferences.cjs', '@/lib/api':'api.cjs',
  '@/components/ChatFilterSelect':'filter.cjs', '@/lib/chat-settings':'settings.cjs',
  '@/lib/generated/chat-scope':'scope.cjs', './generated/chat-scope.ts':'scope.cjs',
};
function compile(source, output) {
  let code = ts.transpileModule(fs.readFileSync(path.join(root, source), 'utf8'), {
    compilerOptions:{module:ts.ModuleKind.CommonJS, jsx:ts.JsxEmit.ReactJSX, target:ts.ScriptTarget.ES2022},
  }).outputText;
  for (const [from,to] of Object.entries(aliases)) code = code.replaceAll(`require("${from}")`, `require(${JSON.stringify(path.join(temp,to))})`);
  for (const external of ['react','react/jsx-runtime']) code = code.replaceAll(`require("${external}")`, `require(${JSON.stringify(require.resolve(external))})`);
  fs.writeFileSync(path.join(temp,output),code);
}
fs.writeFileSync(path.join(temp,'preferences.cjs'), 'exports.useAppPreferences = () => ({ui: text => text});');
fs.writeFileSync(path.join(temp,'api.cjs'), 'exports.request = (...args) => global.researchRequest(...args); exports.getChatFilterOptions = async () => ({sources:{}});');
fs.writeFileSync(path.join(temp,'filter.cjs'), 'exports.ChatFilterSelect = () => null;');
compile('components/ResearchFrequencyPlot.tsx','plots.cjs');
compile('components/DataTable.tsx','table.cjs');
compile('components/ResearchResultCards.tsx','cards.cjs');
compile('components/ResearchRegistryView.tsx','registry.cjs');
compile('lib/generated/chat-scope.ts','scope.cjs');
compile('lib/chat-settings.ts','settings.cjs');
compile('components/ChatSourceSettings.tsx','source-settings.cjs');
const {ResearchAreaPlot,ResearchSeriesPlot,periodOrder} = require(path.join(temp,'plots.cjs'));
const {ResearchResultCards} = require(path.join(temp,'cards.cjs'));
const {ResearchRegistryView} = require(path.join(temp,'registry.cjs'));
const {ChatSourceSettings} = require(path.join(temp,'source-settings.cjs'));
const {defaultScope} = require(path.join(temp,'settings.cjs'));
const areas = ['A','B','C'].map((id,index) => ({area_id:id,label:id,west:140+index,east:141+index,south:38,north:39,coordinate_uncertainty_km:1}));

test('regional demo rectangles show unknown coordinate uncertainty without inventing zero precision', async () => {
  let renderer;
  try {
    await act(() => {renderer = create(React.createElement(ResearchAreaPlot,{areas:[{...areas[0],coordinate_uncertainty_km:null}],rows:[{area_id:'A',result_id:'unloaded',frequency:null,eligible:0}]}));});
    const label = renderer.root.findByType('rect').props['aria-label'];
    assert(label.includes('coordinate uncertainty not established'));
    assert(!label.includes('null km'));
    assert(!label.includes('0 km'));
  } finally {await act(() => renderer?.unmount());}
});

test('reviewed maps distinguish sampled zero, unsampled null and unloaded cells; keyboard selects exact row', async () => {
  let renderer, selected;
  try {
    await act(() => {renderer = create(React.createElement(ResearchAreaPlot,{areas,rows:[
      {area_id:'A',result_id:'zero',frequency:0,detected:0,eligible:3,sampling_status:'sampled_negative'},
      {area_id:'B',result_id:'unsampled',frequency:null,eligible:0,sampling_status:'unsampled'},
    ],onSelect:id => selected=id}));});
    const cells = renderer.root.findAllByType('rect');
    assert.equal(cells[0].props.fill,'#2563eb');
    assert(cells[1].props.fill.startsWith('url(#'));
    assert.equal(cells[2].props.strokeDasharray,'3 3');
    assert(cells[0].props['aria-label'].includes('eligible 3, value 0'));
    await act(() => cells[0].props.onKeyDown({key:'Enter',preventDefault(){}}));
    assert.equal(selected,'zero');
  } finally {await act(() => renderer?.unmount());}
});

test('series retain chronological seasons and break across missing values; axes and matched denominators are separate', async () => {
  assert.deepEqual(['2020-SON','2020-JJA','2020-DJF','2020-MAM'].sort((a,b) => periodOrder({period:a}).localeCompare(periodOrder({period:b}))), ['2020-DJF','2020-MAM','2020-JJA','2020-SON']);
  let renderer, selected;
  const rows = [0.5,null,0,1].map((frequency,index) => ({result_id:`r${index}`,period:`202${index}`,period_kind:'year',taxon_key:'fish',protocol_id:'p',frequency,eligible:frequency === null ? 0 : 3,detected:frequency === null ? 0 : 3*frequency,sst_matched:2,sample_time_sst_mean_celsius:frequency === null ? null : 10+index}));
  try {
    await act(() => {renderer = create(React.createElement(ResearchSeriesPlot,{rows:[...rows].reverse(),taxa:[{taxon_key:'fish',species:'Test fish'}],onSelect:id => selected=id}));});
    const frequency = renderer.root.findAllByType('svg')[0];
    assert.equal(frequency.findAllByType('polyline').length,1);
    assert.equal(frequency.findByType('polyline').props.points.split(' ').length,2);
    assert.equal(frequency.findAllByType('circle').length,3);
    assert(renderer.root.findAllByType('svg')[1].props['aria-label'].includes('°C'));
    assert(frequency.findAllByType('circle')[1].props['aria-label'].includes('SST matched 2'));
    await act(() => frequency.findAllByType('circle')[1].props.onClick());
    assert.equal(selected,'r2');
  } finally {await act(() => renderer?.unmount());}
});

test('chat chart selection opens the exact row on its table page without privileged Data links', async () => {
  let renderer;
  const rows = Array.from({length:25},(_,i) => ({result_id:`row${i}`,period:`${2000+i}`,period_kind:'year',taxon_key:'fish',frequency:i/25,eligible:25,detected:i}));
  try {
    await act(() => {renderer = create(React.createElement(ResearchResultCards,{documents:[{doc_id:'published',title:'Series',context_type:'analysis',analysis_type:'detection_frequency',table:'series',result_rows:rows,total_rows:25,plot_taxa:[{taxon_key:'fish',species:'Test fish'}]}]}));});
    await act(() => renderer.root.findAllByType('circle')[24].props.onClick());
    const selected = renderer.root.findAllByType('tr').find(r => r.props['aria-selected']);
    assert(selected); assert(selected.props.onClick);
    assert(renderer.root.findByType('pre').children.join('').includes('row24'));
    assert.equal(renderer.root.findAllByType('a').length,0);
    const buttons = renderer.root.findAllByType('button');
    assert.equal(buttons.find(b => b.children.join('') === 'Previous').props.disabled,false);
    assert.equal(buttons.find(b => b.children.join('') === 'Next').props.disabled,true);
  } finally {await act(() => renderer?.unmount());}
});

test('researcher decisions and administrator application are distinct UI actions', async () => {
  for (const [role,state] of [['researcher','draft'],['admin','approved'],['admin','draft'],['viewer','approved']]) {
    let renderer;
    const review = {review_id:'review',registry_key:'sampling:test',kind:'sampling',state,version:1,content_sha256:'a'.repeat(64),definition:{},events:[]};
    global.researchRequest = async url => url === '/me' ? {role,permissions:['classification:decide','classification:apply']} : url === '/research-registry-reviews/review' ? review : {items:[review],total:1};
    try {
      await act(async () => {renderer = create(React.createElement(ResearchRegistryView));});
      await act(async () => renderer.root.findAllByType('select')[0].props.onChange({target:{value:'review'}}));
      const labels = renderer.root.findAllByType('button').map(b => b.children.join(''));
      assert.equal(labels.includes('Approve scientific definition'),role === 'researcher' && state === 'draft');
      assert.equal(labels.includes('Apply approved registry'),role === 'admin' && state === 'approved');
      if (labels.includes('Apply approved registry')) assert(renderer.root.findAllByType('button').find(b => b.children.join('') === 'Apply approved registry').props.disabled);
    } finally {await act(() => renderer?.unmount());}
  }
});

test('analysis/workflow/protocol selections preserve disabled sources and existing filters', async () => {
  let renderer;
  const identity = 'a'.repeat(64), changes = [], workflows = [];
  const scope = defaultScope();
  scope.sources.remote_sensing.enabled = false;
  scope.sources.edna_metabarcoding.filters.provider_project_id = 'retained';
  const original = JSON.stringify(scope);
  global.researchRequest = async () => ({options:[{analysis_id:identity,status:'current',analysis_kind:'detection_frequency',label:'Test cohort',protocol_ids:['p','q'],workflows:[{kind:'temperature_comparison',question:'Compare temperatures'}]}]});
  try {
    await act(async () => {renderer = create(React.createElement(ChatSourceSettings,{scope,analysisId:identity,researchIntent:{kind:'temperature_comparison'},onChange:v => changes.push(v),onAnalysisChange:() => {},onResearchChange:(...args) => workflows.push(args)}));});
    const selects = renderer.root.findAllByType('select');
    await act(() => selects.find(s => s.props.id === 'chat-analysis-id').props.onChange({target:{value:identity}}));
    await act(() => selects.find(s => s.props.value === 'temperature_comparison').props.onChange({target:{value:'temperature_comparison'}}));
    await act(() => selects.find(s => s.children.some(c => c.props?.value === 'p')).props.onChange({target:{value:'p'}}));
    assert.equal(changes.length,0); assert.equal(JSON.stringify(scope),original);
    assert.equal(workflows.at(-1)[0].protocol_id,'p');
    assert.equal(renderer.root.findAllByType('input').filter(i => i.props.type === 'checkbox')[2].props.checked,false);
  } finally {await act(() => renderer?.unmount()); delete global.researchRequest;}
});
