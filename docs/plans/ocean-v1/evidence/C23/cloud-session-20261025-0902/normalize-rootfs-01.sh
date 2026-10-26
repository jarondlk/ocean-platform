set -euo pipefail
umask 077
printf '%s  %s\n' e6831ca992b4869b7447bd736b60d7bfc51f8b399624b5e3de6c2dc3448af6eb /tmp/c23-operator-source-20261025-03.tar | sha256sum --check --strict
python3 - <<'REMOTE'
from pathlib import Path
import tarfile
root=Path('/var/lib/ocean-c23/operator-source-20261025-03');root.mkdir(mode=0o700)
with tarfile.open('/tmp/c23-operator-source-20261025-03.tar') as source:
 entries=source.getmembers();assert len(entries)==86
 for entry in entries:
  path=Path(entry.name)
  assert not path.is_absolute() and '..' not in path.parts and entry.isfile() and entry.size<=4*1024**2
 source.extractall(root,filter='data')
for path in root.rglob('*'):
 path.chmod(0o700 if path.is_dir() else 0o444)
REMOTE
env LD_LIBRARY_PATH=/opt/ocean-c23-sqlite/lib PYTHONPATH=/var/lib/ocean-c23/operator-source-20261025-03 /var/lib/ocean-c23/operator-venv/bin/python -B -m sandbox.experiment.gcp.normalize_rootfs --label quota-v3
