"""Source-bound explicit gofer traversal harness integration checks; no analysis or cloud effects."""
from datetime import datetime,timezone
import hashlib,json
from pathlib import Path
import subprocess,time
ROOT=Path(__file__).resolve().parents[7]
BASE=Path(__file__).resolve().parent
SOURCES=('sandbox/experiment/gcp/prepare_image_receipts.py',
 'sandbox/experiment/gcp/run_operator_acceptance.py',
 'tests/test_experiment_sandbox_operator_acceptance.py',
 'tests/test_experiment_sandbox_image_materialization.py',
 'sandbox/experiment/gcp/normalize_rootfs.py',
 'orchestration/experiment_sandbox/profile.py',
 'orchestration/experiment_sandbox/profile_execution.py',
 'orchestration/experiment_sandbox/linux_runtime.py',
 'orchestration/experiment_sandbox/traversal.py',
 'orchestration/experiment_sandbox/files.py')
def pins():
 return {name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in SOURCES}
def write(name,value):
 with (BASE/name).open('x') as out:
  json.dump(value,out,indent=2,sort_keys=True);out.write('\n')
before=pins()
write('verification-start.json',{'recorded_at':datetime.now(timezone.utc).isoformat(),'sources':before})
results=[]
for name,argv in (
 ('pytest',[str(ROOT/'.venv/bin/python'),'-m','pytest','tests/test_experiment_sandbox_operator_acceptance.py','tests/test_experiment_sandbox_image_materialization.py','-q','--tb=short']),
 ('ruff',[str(ROOT/'.venv/bin/ruff'),'check',*SOURCES[:4]])):
 started=time.monotonic()
 with (BASE/(name+'.stdout.txt')).open('x') as out,(BASE/(name+'.stderr.txt')).open('x') as err:
  code=subprocess.run(argv,cwd=ROOT,stdout=out,stderr=err).returncode
 results.append({'check':name,'command':argv,'exit_code':code,'seconds':round(time.monotonic()-started,3)})
after=pins()
record={'recorded_at':datetime.now(timezone.utc).isoformat(),'source_files_before':before,'source_files_after':after,
 'source_steady':before==after,'results':results,'passed':before==after and all(r['exit_code']==0 for r in results),
 'scope':'Host-safe Path API wiring, exact selected-ancestor/readback mocks, strict staging-order and immutable-files boundary plus prior contracts; no actual POSIX ACL, guest code or cloud effect',
 'generated_analysis_execution_performed':False,'cloud_operations_performed':False,
 'actual_runtime_acceptance_performed':False,'retained_C22_real_approval':False,'C23_complete':False}
write('verification.json',record)
print(json.dumps(record),flush=True)
raise SystemExit(0 if record['passed'] else 1)
