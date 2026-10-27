"""Source-bound host-safe recovery driver preparation; no guest/cloud effects."""
from datetime import datetime,timezone
import hashlib,json
from pathlib import Path
import subprocess,time
ROOT=Path(__file__).resolve().parents[7]
BASE=Path(__file__).resolve().parent
SOURCES=('sandbox/experiment/gcp/run_recovery_acceptance.py','tests/test_experiment_sandbox_recovery_acceptance.py')
ACCEPTED=json.loads((BASE.parent/'accepted-source-unchanged.json').read_text())['source_files']
def pins(names):
 return {name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in names}
def write(name,value):
 with (BASE/name).open('x') as stream:
  json.dump(value,stream,indent=2,sort_keys=True);stream.write('\n')
before=pins((*SOURCES,*ACCEPTED))
write('verification-start.json',{'recorded_at':datetime.now(timezone.utc).isoformat(),'source_files':before})
results=[]
for name,argv in (
 ('pytest',[str(ROOT/'.venv/bin/python'),'-m','pytest',SOURCES[1],'-q','--tb=short']),
 ('ruff',[str(ROOT/'.venv/bin/ruff'),'check',*SOURCES])):
 start=time.monotonic()
 with (BASE/(name+'.stdout.txt')).open('x') as out,(BASE/(name+'.stderr.txt')).open('x') as err:
  code=subprocess.run(argv,cwd=ROOT,stdout=out,stderr=err).returncode
 results.append({'check':name,'command':argv,'exit_code':code,'seconds':round(time.monotonic()-start,3)})
after=pins((*SOURCES,*ACCEPTED))
record={'recorded_at':datetime.now(timezone.utc).isoformat(),'source_files_before':before,'source_files_after':after,
 'source_steady':before==after,'accepted_source_unchanged':all(after[name]==sha for name,sha in ACCEPTED.items()),
 'results':results,'passed':before==after and all(after[name]==sha for name,sha in ACCEPTED.items()) and all(r['exit_code']==0 for r in results),
 'scope':'Host-safe synthetic fixture AST, exact forwarding barriers, conservativeassessment andfreshinerthelperSIGKILL only; no generatedguestanalysis/runsc/cgroup/mount/ACL/cloud effect',
 'actual_runtime_acceptance_performed':False,'generated_analysis_execution_performed':False,'cloud_operations_performed':False,
 'retained_C22_real_approval':False,'reservation_released':False,'C23_complete':False}
write('verification.json',record)
print(json.dumps(record),flush=True)
raise SystemExit(0 if record['passed'] else 1)
