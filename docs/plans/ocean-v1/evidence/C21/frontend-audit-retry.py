"""Create-only network retry of the authorized audit; no test/build repeat."""
import importlib.util,json,os,subprocess,time
from datetime import datetime,timezone
from pathlib import Path
HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('c21_verify',HERE/'verify_local.py')
verify=importlib.util.module_from_spec(spec);spec.loader.exec_module(verify)
output=HERE/'frontend-audit-acceptance-02';output.mkdir(exist_ok=False)
before=verify.source_pins();verify.save(output,'source-before.json',before)
env=dict(os.environ,PATH='/Users/jaronchai/.nvm/versions/node/v22.14.0/bin'+os.pathsep+os.environ.get('PATH',''))
command=['npm','audit','--omit=dev','--audit-level=moderate','--json','--cache=/private/tmp/c21-npm-audit-cache']
started=time.monotonic()
with (output/'audit.json').open('x') as log: result=subprocess.run(command,cwd=verify.ROOT/'frontend-v1',env=env,stdout=log,stderr=subprocess.STDOUT,timeout=120)
after=verify.source_pins();verify.save(output,'source-after.json',after)
changed=sorted(name for name in set(before)|set(after) if before.get(name)!=after.get(name))
initial=json.loads((HERE/'frontend-acceptance-01/result.json').read_text())
previous=json.loads((HERE/'frontend-acceptance-01/source-before.json').read_text())
try: audit=json.loads((output/'audit.json').read_text())
except ValueError: audit={}
row={'component':'C21','group':'frontend-audit-retry','created_at':datetime.now(timezone.utc).isoformat(),'command':command,'exit_code':result.returncode,'seconds':round(time.monotonic()-started,2),'log':'audit.json','log_sha256':verify.sha(output/'audit.json'),'source_changed_during_run':changed,'same_source_as_original_full_verification':before==previous,'preservation':verify.preservation(),'production_dependency_vulnerabilities':audit.get('metadata',{}).get('vulnerabilities'),'original_full_run':{'path':'docs/plans/ocean-v1/evidence/C21/frontend-acceptance-01/result.json','sha256':verify.sha(HERE/'frontend-acceptance-01/result.json'),'test_typecheck_build_passed':all(item['exit_code']==0 for item in initial['commands'] if item['name']!='audit'),'audit_failure':'sandbox DNS resolution unavailable; original attempt preserved'},'success':result.returncode==0 and not changed and before==previous and audit.get('metadata',{}).get('vulnerabilities',{}).get('total')==0}
verify.save(output,'result.json',row);print(json.dumps(row,indent=2));raise SystemExit(0 if row['success'] else 1)
