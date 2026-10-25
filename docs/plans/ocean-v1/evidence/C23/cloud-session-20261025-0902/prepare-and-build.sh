set -euo pipefail
umask 077
printf '%s  %s\n' f9c78b5001fa13f8ea878e00253bfc5a7cd42b7fe403076f90c2e9efd25200f9 /tmp/c23-operator-source-20261025-02.tar | sha256sum --check --strict
python3 - <<'REMOTE'
from pathlib import Path
import tarfile
root=Path('/var/lib/ocean-c23/operator-source-20261025-02');root.mkdir(mode=0o700)
with tarfile.open('/tmp/c23-operator-source-20261025-02.tar') as source:
 entries=source.getmembers();assert len(entries)==85
 for entry in entries:
  path=Path(entry.name)
  assert not path.is_absolute() and '..' not in path.parts and entry.isfile()
  assert entry.size<=4*1024**2
 source.extractall(root,filter='data')
for path in root.rglob('*'):
 path.chmod(0o700 if path.is_dir() else 0o444)
REMOTE
bash /tmp/resume_worker.sh > /var/lib/ocean-c23/evidence/resume-20261025.json
mount --version > /var/lib/ocean-c23/evidence/mount-version-20261025.txt
umount --version > /var/lib/ocean-c23/evidence/umount-version-20261025.txt
mount --help > /var/lib/ocean-c23/evidence/mount-help-20261025.txt
umount --help > /var/lib/ocean-c23/evidence/umount-help-20261025.txt
python3 - <<'REMOTE'
from pathlib import Path
for name in ('mount','umount'):
 assert '--internal-only' in Path('/var/lib/ocean-c23/evidence/'+name+'-help-20261025.txt').read_text()
print('Pinned source staged; trusted mount/umount internal-only support verified.')
REMOTE
bash /tmp/build_quota_amendment.sh
