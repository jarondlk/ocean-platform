"""Source-bound pure harness checks; this never runs a guest analysis."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import time

ROOT=Path(__file__).resolve().parents[7]
BASE=Path(__file__).resolve().parent
SOURCES=('sandbox/experiment/gcp/run_operator_acceptance.py',
         'tests/test_experiment_sandbox_operator_acceptance.py')


def pins():
    return {name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in SOURCES}


def write(name,value):
    with (BASE/name).open('x') as stream:
        json.dump(value,stream,indent=2,sort_keys=True)
        stream.write('\n')


def main():
    before=pins()
    write('preparation-start.json',{'recorded_at':datetime.now(timezone.utc).isoformat(),
        'source_files':before,'blueprint_sha256':hashlib.sha256((BASE.parent/'blueprint.json').read_bytes()).hexdigest()})
    results=[]
    for name,command in (
        ('pytest',[str(ROOT/'.venv/bin/python'),'-m','pytest',
                   'tests/test_experiment_sandbox_operator_acceptance.py','-q','--tb=short']),
        ('ruff',[str(ROOT/'.venv/bin/ruff'),'check',*SOURCES]),
    ):
        started=time.monotonic()
        with (BASE/(name+'.stdout.txt')).open('x') as out:
            with (BASE/(name+'.stderr.txt')).open('x') as err:
                result=subprocess.run(command,cwd=ROOT,stdout=out,stderr=err)
        record={'check':name,'command':command,'exit_code':result.returncode,
                'seconds':round(time.monotonic()-started,3)}
        results.append(record)
        print(json.dumps(record),flush=True)
    after=pins()
    record={'recorded_at':datetime.now(timezone.utc).isoformat(),'source_files_before':before,
        'source_files_after':after,'source_steady':before==after,'results':results,
        'passed':before==after and all(result['exit_code']==0 for result in results),
        'scope':'Pure fixture, target guard, network evidence and observation-contract tests only',
        'generated_analysis_execution_performed':False,'cloud_operations_performed':False,
        'actual_runtime_acceptance_performed':False,'retained_C22_real_approval':False,'C23_complete':False}
    write('preparation.json',record)
    print(json.dumps(record),flush=True)
    raise SystemExit(0 if record['passed'] else 1)


if __name__=='__main__':
    main()
