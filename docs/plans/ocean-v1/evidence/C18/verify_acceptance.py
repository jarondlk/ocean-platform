"""Freeze C18 local source/evidence once; later invocations verify without rewriting."""
from pathlib import Path
import hashlib
import json

ROOT = Path(__file__).resolve().parents[5]
OUT = Path(__file__).resolve().parent

def sha(path):
    return hashlib.sha256((ROOT / path).read_bytes()).hexdigest()

def aggregate(files):
    return hashlib.sha256(''.join(f'{p}:{h}\n' for p, h in sorted(files.items())).encode()).hexdigest()

def read(path):
    return json.loads((ROOT / path).read_text())

def save(name, value):
    with (OUT / name).open('x') as stream:
        stream.write(json.dumps(value, indent=2) + '\n')

def verify(files):
    changed = [p for p, h in files.items() if sha(p) != h]
    if changed:
        raise SystemExit('Changed pinned files: ' + repr(changed))

start = read('docs/plans/ocean-v1/evidence/C18/start-snapshot.json')
for files in start['preservation'].values():
    verify(files)
verify(start['prior_evidence_files'])
verify(start['readiness_receipts'])
backend = read('docs/plans/ocean-v1/evidence/C18/backend-tested-source.json')
assert backend['before_sha256'] == backend['after_sha256']
verify(backend['after_sha256'])
frontend = read('docs/plans/ocean-v1/evidence/C18/frontend-final-result.json')
assert frontend['before'] == frontend['after'] and not frontend['changed_during_run']
assert len(frontend['results']) == 4 and all(r['exit_code'] == 0 for r in frontend['results'])
verify(frontend['after'])
verify(read('docs/plans/ocean-v1/evidence/C17/accepted-source.json')['files'])
paths = [
 'api/v1_runtime_routes.py', 'tests/test_v1_runtime.py',
 'frontend-v1/src/runtime.ts', 'frontend-v1/tests/runtime.test.ts',
 'frontend-v1/src/investigation-service.ts', 'frontend-v1/src/research-state.ts',
 'frontend-v1/tests/investigation-service.test.ts', 'frontend-v1/tests/research-state.test.ts',
 'frontend-v1/src/research-run-contract.ts', 'frontend-v1/src/research-activity.tsx',
 'frontend-v1/src/research-activity.css', 'frontend-v1/development/c18/run-fixture.ts',
 'frontend-v1/tests/research-run-contract.test.ts', 'frontend-v1/src/research-workspace.tsx',
 'frontend-v1/src/research-workspace.css', 'frontend-v1/src/runtime-app.tsx',
 'frontend-v1/development/c18/app/page.tsx', 'frontend-v1/development/c18/app/layout.tsx',
 'frontend-v1/development/c18/next.config.mjs', 'frontend-v1/development/c18/package.json',
 'frontend-v1/development/c18/tsconfig.json', 'frontend-v1/development/c18/.gitignore',
 'frontend-v1/README.md',
]
files = {p: sha(p) for p in sorted(paths)}
formal = {}
for component, entries in start['formal_source_entries'].items():
    for path, entry in entries.items():
        before = entry['current_sha256']
        if sha(path) != before:
            assert path in files
            formal[f'{component}:{path}'] = {'before_sha256': before, 'C18_sha256': sha(path), 'reason': 'C18 actual Research UI/runtime integration and documentation; original receipt remains immutable'}
review_supersessions = {}
for name in ('ui-review-initial.json','ui-review-followup.json','ui-review-final.json'):
    receipt = json.loads((OUT/name).read_text())
    for key, values in receipt.items():
        if isinstance(values,dict):
            for p,h in values.items():
                if p in files and isinstance(h,str) and len(h)==64 and sha(p)!=h:
                    review_supersessions.setdefault(name,{})[p]={'reviewed_sha256':h,'accepted_sha256':sha(p),'reason':'Subsequent recorded R1-R12 fixes, final current review and final frontend checks'}
if (OUT/'verification.json').exists():
    accepted = read('docs/plans/ocean-v1/evidence/C18/accepted-source.json')
    verify(accepted['files'])
    receipt = read('docs/plans/ocean-v1/evidence/C18/verification.json')
    verify(receipt['evidence_files'])
    print(json.dumps({'state':'read-only verification pass','source_sha256':accepted['source_sha256'],'source_paths':len(files),'prior_evidence_unchanged':len(start['prior_evidence_files'])}))
else:
    save('accepted-source.json',{'files':files,'source_sha256':aggregate(files),'aggregate_algorithm':'SHA256 of sorted UTF-8 path:SHA256 lines with LF endings'})
    save('preservation.json',{'prerequisite_entries':sum(len(v) for v in start['formal_source_entries'].values()),'formal_intentional_supersessions':formal,'review_source_supersessions':review_supersessions,'C17_all19_sources_unchanged':True,'backend21_sources_unchanged':True,'frontend_all_tested_sources_unchanged':True,'prior_evidence_files_unchanged':len(start['prior_evidence_files']),'protected_counts':{k:len(v) for k,v in start['preservation'].items()},'original_run_semantics_supersession':'run-artifact-semantics-verification.json'})
    evidence={str(p.relative_to(ROOT)):sha(p.relative_to(ROOT)) for p in sorted(OUT.iterdir()) if p.is_file() and p.name!='verification.json'}
    save('verification.json',{'component':'C18','state':'All3 local checkpoints complete; source checkpoint and exact-source hosted delivery pending','branch':'overhaul','base_commit':start['implementation_base'],'files':files,'source_sha256':aggregate(files),'evidence_files':evidence,'checks':{'backend':{'passed':4214,'postgres_gated_skips':187,'coverage_percent':85.08,'warnings':2597,'seconds':340.29,'unchanged_sources':21,'unrelated_local_benchmark_cases_excluded_from_commit':9},'frontend':{'passed':673,'production_typecheck':'pass','production_build':'pass','development_strict_typecheck':'pass','source_unchanged':True},'actual_client_ASGI':{'requests':28,'operations':14},'focused_client_tests':128,'focused_run_tests':33,'runtime_backend':59,'runtime_frontend':69,'active_python_ruff':'pass','browser':'browser-qa.md','independent_current_review':'ui-review-browser-fixes.json','owned_server_cleanup':'browser-cleanup.json','hosted_ci':'pending exact-source run'},'preservation':{'prior_evidence_unchanged':736,'unrelated':30,'scientific':7,'serving':2,'legacy_frontend':106,'all19_C17_sources_unchanged':True},'qualifications':['Separate v1 actual C17/C16 UI with sealed synthetic fixtures and TEST principals only.','Production execution remains unavailable until C20; final answers/evidence remain C21.','No real OIDC/model/scientific approval/data acquisition or transfer/cloud deployment acceptance.','Original snapshot-discovery harness mistake and initial integration failures retained; corrected cases separately qualified.','Corrected9725 requests include passive polling during usage interruptions, not9725 independent cases or capacity evidence.','Drafts/run fixture memory intentionally volatile across browser reload; durable history deferred.','No spoken screen-reader claim; read-only review does not replace real browser checks.']})
    print(json.dumps({'state':'local acceptance frozen','source_sha256':aggregate(files),'source_paths':len(files),'verification_sha256':sha((OUT/'verification.json').relative_to(ROOT)),'formal_supersessions':len(formal),'evidence_files':len(evidence)}))
