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
const temp = fs.mkdtempSync(path.join(os.tmpdir(), 'ocean-coverage-ui-'));
after(() => fs.rmSync(temp, {recursive:true, force:true}));
function compile(source, output) {
  let code = ts.transpileModule(fs.readFileSync(path.join(root, source), 'utf8'), {
    compilerOptions:{module:ts.ModuleKind.CommonJS, jsx:ts.JsxEmit.ReactJSX, target:ts.ScriptTarget.ES2022},
  }).outputText;
  for (const [from,to] of Object.entries({'@/lib/source-coverage':'coverage.cjs','@/lib/preferences':'preferences.cjs'})) {
    code = code.replaceAll(`require("${from}")`, `require(${JSON.stringify(path.join(temp,to))})`);
  }
  for (const external of ['react','react/jsx-runtime']) code = code.replaceAll(`require("${external}")`, `require(${JSON.stringify(require.resolve(external))})`);
  fs.writeFileSync(path.join(temp,output),code);
}
fs.writeFileSync(path.join(temp,'preferences.cjs'), 'exports.useAppPreferences = () => ({ui: text => text});');
compile('lib/source-coverage.ts','coverage.cjs');
compile('components/SourceCoverage.tsx','component.cjs');
const {SourceCoverage} = require(path.join(temp,'component.cjs'));
function text(node) {return typeof node === 'string' ? node : (node?.children || []).map(text).join('');}

test('mounted coverage announces unverified overlap and retains both source counts', async () => {
  let renderer;
  try {
    await act(() => {renderer = create(React.createElement(SourceCoverage,{diagnostics:{comparison_status:'overlap_unverified',per_source:{
      remote_sensing:{enabled:true,state:'retrieved',prompt_count:4},
      edna_metabarcoding:{enabled:true,state:'retrieved',prompt_count:4},
      ctd:{enabled:false,state:'disabled',prompt_count:0},
    }}}));});
    assert.equal(renderer.root.findByType('section').props['aria-label'],'Source evidence coverage');
    assert.match(text(renderer.root.findByProps({role:'status'})),/does not establish a match/);
    assert.equal(renderer.root.findAllByType('li').length,2);
    assert.match(text(renderer.toJSON()),/ANEMONE eDNA: 4 evidence documents supplied/);
  } finally {await act(() => renderer?.unmount());}
});

test('legacy history renders no invented warning and a later partial response announces the failure', async () => {
  let renderer;
  try {
    await act(() => {renderer = create(React.createElement(SourceCoverage,{diagnostics:{backend:'postgres'}}));});
    assert.equal(renderer.toJSON(),null);
    await act(() => renderer.update(React.createElement(SourceCoverage,{diagnostics:{coverage_status:'partial',per_source:{edna_metabarcoding:{enabled:true,state:'backend_failed',prompt_count:0}}}})));
    assert.match(text(renderer.toJSON()),/Source search failed/);
    assert.equal(renderer.root.findAllByProps({role:'status'}).length,1);
    assert.match(text(renderer.toJSON()),/does not establish absent source data/);
  } finally {await act(() => renderer?.unmount());}
});
