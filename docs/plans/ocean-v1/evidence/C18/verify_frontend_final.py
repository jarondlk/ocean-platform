import hashlib,json,subprocess,time
from pathlib import Path
root=Path.cwd();out=root/'docs/plans/ocean-v1/evidence/C18'
paths=sorted(str(p.relative_to(root)) for p in (root/'frontend-v1/src').glob('*.ts*'))+sorted(str(p.relative_to(root)) for p in (root/'frontend-v1/src').glob('*.css'))+sorted(str(p.relative_to(root)) for p in (root/'frontend-v1/tests').glob('*.ts'))+sorted(str(p.relative_to(root)) for p in (root/'frontend-v1/development/c18').rglob('*') if p.is_file() and '.next' not in p.parts and p.name not in ('next-env.d.ts','tsconfig.tsbuildinfo'))
def hashes(): return {p:hashlib.sha256((root/p).read_bytes()).hexdigest() for p in paths}
before=hashes();results=[]
for name,cmd in [('frontend-tests-final',['npm','--prefix','frontend-v1','test']),('frontend-typecheck-final',['npm','--prefix','frontend-v1','run','typecheck']),('frontend-build-final',['npm','--prefix','frontend-v1','run','build']),('development-typecheck-final',['frontend-v1/node_modules/.bin/tsc','--noEmit','-p','frontend-v1/development/c18/tsconfig.json'])]:
 started=time.monotonic()
 with (out/(name+'.txt')).open('x') as f: result=subprocess.run(cmd,stdout=f,stderr=subprocess.STDOUT)
 results.append({'command':cmd,'exit_code':result.returncode,'seconds':round(time.monotonic()-started,2),'log':str((out/(name+'.txt')).relative_to(root))})
 if result.returncode: break
after=hashes();record={'results':results,'before':before,'after':after,'changed_during_run':[p for p in paths if before[p]!=after[p]]}
(out/'frontend-final-result.json').write_text(json.dumps(record,indent=2)+'\n');print(json.dumps({'results':results,'changed_during_run':record['changed_during_run']}));raise SystemExit(any(r['exit_code'] for r in results) or bool(record['changed_during_run']))
