// Verify captured API citation audits against the actual frontend renderer.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { createRequire } = require('node:module');
const root = path.resolve(__dirname, '../..');
const frontendRequire = createRequire(path.join(root, 'frontend/package.json'));
const ts = frontendRequire('typescript');
const React = frontendRequire('react');
const { renderToStaticMarkup } = frontendRequire('react-dom/server');
const temp = fs.mkdtempSync(path.join(os.tmpdir(), 'ocean-captured-markdown-'));
try {
  for (const [relative, name] of [['lib/citation-navigation.ts','citations.cjs'], ['components/MarkdownAnswer.tsx','answer.cjs']]) {
    let compiled = ts.transpileModule(fs.readFileSync(path.join(root,'frontend',relative),'utf8'), {
      compilerOptions: {module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.ReactJSX,target:ts.ScriptTarget.ES2022}
    }).outputText;
    compiled = compiled.replaceAll('require("@/lib/citation-navigation")',`require(${JSON.stringify(path.join(temp,'citations.cjs'))})`)
      .replaceAll('require("react/jsx-runtime")',`require(${JSON.stringify(frontendRequire.resolve('react/jsx-runtime'))})`);
    fs.writeFileSync(path.join(temp,name),compiled);
  }
  const { MarkdownAnswer } = require(path.join(temp,'answer.cjs'));
  const { buildCitationTargetIndex } = require(path.join(temp,'citations.cjs'));
  const data = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
  const checks = [];
  for (const result of data.results) {
    const response = result.response;
    if (response?.outcome !== 'answered') continue;
    const html = renderToStaticMarkup(React.createElement(MarkdownAnswer, {
      text: response.answer, citationTargets: buildCitationTargetIndex(response), onCitationSelect: () => {}
    }));
    const actual = [...html.matchAll(/aria-label="Inspect citation ([^"]+)"/g)].map(match => match[1]);
    const expected = response.answer_audit.citations.filter(row => row.valid).map(row => row.citation_id);
    assert.deepEqual(actual, expected, result.id);
    checks.push({id:result.id, clickable_citations:actual.length, passed:true});
  }
  console.log(JSON.stringify({checks},null,2));
} finally { fs.rmSync(temp,{recursive:true,force:true}); }
