// Run the actual renderer and API client against the shared citation fixtures.
const assert = require('node:assert/strict');
const { test, after } = require('node:test');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const ts = require('typescript');
const React = require('react');
const { renderToStaticMarkup } = require('react-dom/server');
const root = path.resolve(__dirname, '..');
const temp = fs.mkdtempSync(path.join(os.tmpdir(), 'ocean-contract-'));
after(() => fs.rmSync(temp, { recursive: true, force: true }));
function compile(relative, name) {
  const source = fs.readFileSync(path.join(root, relative), 'utf8');
  let compiled = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX, target: ts.ScriptTarget.ES2022 } }).outputText;
  compiled = compiled.replaceAll('require("@/lib/citation-navigation")', `require(${JSON.stringify(path.join(temp, 'citations.cjs'))})`)
    .replaceAll('require("react/jsx-runtime")', `require(${JSON.stringify(require.resolve('react/jsx-runtime'))})`);
  fs.writeFileSync(path.join(temp, name), compiled);
}
compile('lib/citation-navigation.ts', 'citations.cjs');
compile('components/MarkdownAnswer.tsx', 'answer.cjs');
compile('lib/api.ts', 'api.cjs');
const { MarkdownAnswer } = require(path.join(temp, 'answer.cjs'));
const { request, ApiError } = require(path.join(temp, 'api.cjs'));
const fixtures = JSON.parse(fs.readFileSync(path.join(root, '../tests/fixtures/citation_contract.json')));
for (const fixture of fixtures) {
  test(`citation contract: ${fixture.name}`, () => {
    const targets = new Map(['ctd_qa', 'ctd_other'].map(id => [id, { citationId: id, valid: true, title: id }]));
    const html = renderToStaticMarkup(React.createElement(MarkdownAnswer, { text: fixture.answer, citationTargets: targets, onCitationSelect: () => {} }));
    assert.deepEqual([...html.matchAll(/aria-label="Inspect citation ([^"]+)"/g)].map(match => match[1]), fixture.ids);
  });
}
test('structured errors retain diagnostics, and validation never echoes request input', async () => {
  const previous = global.fetch;
  try {
    global.fetch = async () => new Response(JSON.stringify({ detail: [{ loc: ['body', 'time_from'], msg: 'Value error, time_from must not exceed time_to', input: { secret: 'PRIVATE_REQUEST' } }] }), { status: 422 });
    await assert.rejects(request('/chat'), error => {
      assert(error instanceof ApiError);
      assert.equal(error.code, 'validation_error');
      assert.equal(error.status, 422);
      assert.equal(error.message, 'time_from: time_from must not exceed time_to');
      assert(!error.message.includes('PRIVATE_REQUEST'));
      return true;
    });
    global.fetch = async () => new Response(JSON.stringify({ detail: { code: 'llm_output_limit', message: 'Request a shorter answer.', interaction_id: 'qa-reference' } }), { status: 502 });
    await assert.rejects(request('/chat'), error => error.code === 'llm_output_limit' && error.interaction_id === 'qa-reference');
    global.fetch = async () => new Response('<html>proxy failure</html>', { status: 503 });
    await assert.rejects(request('/chat'), error => error.message === 'Request failed with 503');
  } finally { global.fetch = previous; }
});
