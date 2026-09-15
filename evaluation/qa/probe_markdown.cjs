// Exercise the real answer renderer without a browser or production mutation.
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const {createRequire} = require('node:module');
const root = path.resolve(__dirname, '../..');
const frontendRequire = createRequire(path.join(root, 'frontend/package.json'));
const ts = frontendRequire('typescript');
const React = frontendRequire('react');
const {renderToStaticMarkup} = frontendRequire('react-dom/server');
const temp = fs.mkdtempSync(path.join(os.tmpdir(), 'ocean-markdown-qa-'));
function compile(relative, name) {
  const source = fs.readFileSync(path.join(root, 'frontend', relative), 'utf8');
  let compiled = ts.transpileModule(source, {compilerOptions:{module:ts.ModuleKind.CommonJS, jsx:ts.JsxEmit.ReactJSX, target:ts.ScriptTarget.ES2022}}).outputText;
  compiled = compiled.replaceAll('require("@/lib/citation-navigation")', `require(${JSON.stringify(path.join(temp,'citations.cjs'))})`)
    .replaceAll('require("react/jsx-runtime")',`require(${JSON.stringify(frontendRequire.resolve('react/jsx-runtime'))})`);
  fs.writeFileSync(path.join(temp,name), compiled);
}
compile('lib/citation-navigation.ts','citations.cjs');
compile('components/MarkdownAnswer.tsx','answer.cjs');
compile('lib/api.ts','api.cjs');
const {MarkdownAnswer} = require(path.join(temp,'answer.cjs'));
const target = {citationId:'ctd_qa',kind:'source',valid:true,title:'QA source',detail:'12 C',evidenceRole:'primary'};
const examples = [
  ['plain','12 C [ctd_qa].',true],
  ['bold','**12 C [ctd_qa].**',true],
  ['group','12 C [ctd_qa, ctd_qa].',true],
  ['markdown_link','12 C [ctd_qa](https://example.org/qa).',false],
  ['inline_code','12 C `[ctd_qa]`.',false],
  ['unsafe_link','[unsafe](javascript:alert(1))',false],
  ['raw_html','<script>alert(1)</script>',false],
];
const results = examples.map(([id,text,expectClickable])=>{
 const html=renderToStaticMarkup(React.createElement(MarkdownAnswer,{text,citationTargets:new Map([['ctd_qa',target]]),onCitationSelect:()=>{}}));
 const clickable=html.includes('aria-label="Inspect citation');
 return {id,expectClickable,clickable,passed:id==='unsafe_link'?!html.includes('href="javascript:'):id==='raw_html'?!html.includes('<script>'):clickable===expectClickable,html};
});
(async()=>{
 const {request}=require(path.join(temp,'api.cjs'));
 global.fetch=async()=>new Response(JSON.stringify({detail:[{type:'value_error',loc:['body','time_from'],msg:'Value error, time_from must not exceed time_to',input:'2099-12-31'}]}),{status:422});
 try{await request('/chat')}catch(e){results.push({id:'validation_message_is_human_readable',passed:!e.message.startsWith('{'),message:e.message})}
 global.fetch=async()=>new Response(JSON.stringify({detail:{code:'llm_output_limit',message:'The answer reached the output limit before it could finish.',interaction_id:'qa-reference'}}),{status:502});
 try{await request('/chat')}catch(e){results.push({id:'failure_reference_preserved',passed:e.message.includes('qa-reference')||Boolean(e.interaction_id),message:e.message,code:e.code??null,interaction_id:e.interaction_id??null})}
 console.log(JSON.stringify({date:'2026-09-14',scope:'Actual frontend component SSR and fetch error handling; synthetic responses',results},null,2));
 fs.rmSync(temp,{recursive:true,force:true});
})();
