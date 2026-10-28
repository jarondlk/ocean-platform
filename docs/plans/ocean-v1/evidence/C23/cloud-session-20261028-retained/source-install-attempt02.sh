set -euo pipefail
[[ "$(id -u)" == 0 && "$(hostname -s)" == c23-containment-01 ]]
umask 077
python3 -I -S -B - <<'PY'
from pathlib import Path
import json,hashlib,tarfile,os
archive=Path('/tmp/c23-operator-source-20261027-08.tar')
manifest_path=Path('/tmp/operator-source-20261027-08.json')
raw=manifest_path.read_bytes();manifest=json.loads(raw)
assert hashlib.sha256(archive.read_bytes()).hexdigest()==manifest['archive_sha256']=='e2213494733a96e278b3733204277db2d25941f2558128dd715719a3c08d7bbe'
root=Path(manifest['intended_remote_root']);assert root==Path('/var/lib/ocean-c23/operator-source-20261027-08') and not root.exists()
root.mkdir(mode=0o700)
with tarfile.open(archive,'r') as tar:
 members=tar.getmembers();assert len(members)==len(manifest['source_files'])==236
 assert {m.name for m in members}==set(manifest['source_files'])
 for member in members:
  assert member.isreg() and 0<member.size<=2*1024**2
  data=tar.extractfile(member).read();assert hashlib.sha256(data).hexdigest()==manifest['source_files'][member.name]
  path=root/member.name;assert path.is_relative_to(root) and '..' not in path.parts
  path.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
  with path.open('xb') as stream:stream.write(data)
  path.chmod(0o400)
for path in root.rglob('*'):
 if path.is_dir():path.chmod(0o700)
 assert path.stat().st_uid==0 and path.stat().st_gid==0
receipt=Path('/var/lib/ocean-c23/evidence/operator-source-20261027-08.json')
with receipt.open('xb') as stream:stream.write(raw)
receipt.chmod(0o400)
print(json.dumps({'source_root':str(root),'source_files':236,'archive_sha256':manifest['archive_sha256'],'protected_source_installed':True}))
PY
bash /var/lib/ocean-c23/operator-source-20261027-08/sandbox/experiment/gcp/resume_worker.sh
cd /var/lib/ocean-c23/operator-source-20261027-08
LD_LIBRARY_PATH=/opt/ocean-c23-sqlite/lib PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$PWD" /var/lib/ocean-c23/operator-venv/bin/python -B - <<'PY'
import importlib,json,hashlib,platform,sqlite3
from pathlib import Path
from orchestration.experiment_sandbox import physical_termination as p
for file in sorted(p.WORKER_FILES-{'sandbox/experiment/trusted_init.py'}):importlib.import_module(file[:-3].replace('/','.'))
importlib.import_module('tests.research_experiment_support')
importlib.import_module('sandbox.experiment.gcp.run_retained_acceptance')
manifest=json.loads(Path('/var/lib/ocean-c23/evidence/operator-source-20261027-08.json').read_text())
p._protected_sources(Path.cwd(),manifest['source_files']);p.require_loaded_source_provenance(Path.cwd(),manifest['source_files'],check=lambda:None)
files={name:hashlib.sha256(Path('/var/lib/ocean-c23/evidence',name).read_bytes()).hexdigest() for name in ('image-preparation-quota-v3.json','runtime-preparation-quota-v3.json','rootfs-normalization-quota-v3.json')}
print(json.dumps({'protected_imports_verified':True,'host_boot_id':Path('/proc/sys/kernel/random/boot_id').read_text().strip(),'worker_id':hashlib.sha256(('c23-linux-machine-id:'+Path('/etc/machine-id').read_text().strip()).encode()).hexdigest(),'python':platform.python_version(),'sqlite':sqlite3.sqlite_version,'known_material_receipt_sha256':files},sort_keys=True))
PY
