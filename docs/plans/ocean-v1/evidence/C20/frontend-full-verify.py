"""C20 authorized full frontend verification; preserves source/dependency files."""
import hashlib,json,subprocess
from datetime import datetime,timezone
from pathlib import Path
ROOT=Path(__file__).resolve().parents[5]
BASE=ROOT/'docs/plans/ocean-v1/evidence/C20'
def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def pins(prefix):
    paths=subprocess.check_output(['git','ls-files','--cached','--others','--exclude-standard','-z','--',prefix],cwd=ROOT).decode().split('\0')
    return {path:sha(ROOT/path) for path in sorted(set(paths)) if path and (ROOT/path).is_file()}
def snapshot(): return {'frontend_source_sha256':pins('frontend-v1'),'legacy_source_sha256':pins('frontend'),'wire_fixture_sha256':sha(BASE/'wire-fixtures.json')}
before=snapshot()
(BASE/'frontend-full-source-before.json').write_text(json.dumps(before,indent=2)+'\n')
versions={name:subprocess.check_output([name,'--version'],text=True).strip() for name in ['node','npm']}
results=[]
for name,command in [('test',['npm','test']),('typecheck',['npm','run','typecheck']),('build',['npm','run','build'])]:
    print('Starting frontend '+name,flush=True)
    started=datetime.now(timezone.utc).isoformat()
    log=BASE/('frontend-full-'+name+'.txt')
    with log.open('w') as stream: result=subprocess.run(command,cwd=ROOT/'frontend-v1',stdout=stream,stderr=subprocess.STDOUT)
    record={'name':name,'command':command,'cwd':str(ROOT/'frontend-v1'),'started_at':started,'finished_at':datetime.now(timezone.utc).isoformat(),'exit_code':result.returncode,'log':str(log.relative_to(ROOT)),'log_sha256':sha(log)}
    results.append(record)
    with (BASE/'frontend-full-command-results.jsonl').open('a') as stream: stream.write(json.dumps(record)+'\n')
    print('Finished frontend '+name+': '+str(result.returncode),flush=True)
after=snapshot()
(BASE/'frontend-full-source-after.json').write_text(json.dumps(after,indent=2)+'\n')
(BASE/'frontend-full-local-results.json').write_text(json.dumps({'versions':versions,'commands':results,'frontend_unchanged':before['frontend_source_sha256']==after['frontend_source_sha256'],'legacy_unchanged':before['legacy_source_sha256']==after['legacy_source_sha256'],'wire_fixture_unchanged':before['wire_fixture_sha256']==after['wire_fixture_sha256']},indent=2)+'\n')
print(json.dumps({'commands':{item['name']:item['exit_code'] for item in results},'frontend_unchanged':before['frontend_source_sha256']==after['frontend_source_sha256'],'legacy_unchanged':before['legacy_source_sha256']==after['legacy_source_sha256']}),flush=True)
