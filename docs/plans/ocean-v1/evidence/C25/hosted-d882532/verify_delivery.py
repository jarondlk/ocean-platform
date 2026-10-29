"""Read-only C25 exact-source delivery/evidence verifier; no cloud or analyses."""
import gzip
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[6]
HERE = Path(__file__).resolve().parent
BASE = HERE.parent


def read(path):
    return json.loads(path.read_text())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    receipt = read(BASE / 'delivery.json')
    source = receipt['source_commit']
    run = read(HERE / 'run.json')
    assert run['id'] == receipt['hosted_run']['id'] and run['head_sha'] == source
    assert run['status'] == 'completed' and run['conclusion'] == 'success'
    jobs = read(HERE / 'jobs.json')['jobs']
    required = [j for j in jobs if j['name'] in receipt['required_job_results']]
    assert len(required) == 4
    for job in required:
        assert job['conclusion'] == 'success' and job['status'] == 'completed' and job['run_id'] == run['id']
        meta = read(HERE / f'job-{job["id"]}.json')
        path = HERE / f'job-{job["id"]}.log.gz'
        assert meta['source_commit'] == source and sha(path) == meta['gzip_sha256']
        assert hashlib.sha256(gzip.decompress(path.read_bytes())).hexdigest() == meta['raw_sha256']
    for name, expected in receipt['source_files'].items():
        assert sha(ROOT / name) == expected, name
        assert hashlib.sha256(subprocess.check_output(['git', 'show', source + ':' + name], cwd=ROOT)).hexdigest() == expected, name
    for field in ('local_receipt', 'original_local_receipt', 'source_checkpoint'):
        ref = receipt[field]
        assert sha(ROOT / ref['path']) == ref['sha256']
    for folder, name in [('implementation-20261028', 'local-receipt.json'), ('history-amendment-20261029', 'receipt.json')]:
        evidence = read(BASE / folder / name)
        for relative, expected in evidence['evidence_files'].items():
            assert sha(BASE / folder / relative) == expected, relative
    start = read(BASE / 'implementation-20261028/start.json')
    for name, expected in start['protected_sha256'].items():
        assert sha(ROOT / name) == expected, name
    manifest = read(HERE / 'manifest.json')
    assert sha(BASE / 'delivery.json') == manifest['delivery_sha256']
    for name, expected in manifest['files'].items():
        assert sha(HERE / name) == expected, name
    print(f'C25 Complete: {len(receipt["source_files"])} exact source pins, four successful hosted jobs, immutable evidence and protected paths verified')


if __name__ == '__main__':
    main()
