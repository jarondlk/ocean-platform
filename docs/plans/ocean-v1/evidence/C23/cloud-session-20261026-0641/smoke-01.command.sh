set -euo pipefail
umask 077
printf '%s  %s\n' 27f41c40a760e89e5268864922ffede098d4cf9e6d10cbc42ddcabb77ea9a78e /tmp/c23-operator-source-20261026-01.tar | sha256sum --check --strict
python3 - <<'REMOTE'
from pathlib import Path
import tarfile
root=Path('/var/lib/ocean-c23/operator-source-20261026-01');root.mkdir(mode=0o700)
with tarfile.open('/tmp/c23-operator-source-20261026-01.tar') as source:
 entries=source.getmembers();assert len(entries)==86
 for entry in entries:
  path=Path(entry.name)
  assert not path.is_absolute() and '..' not in path.parts and entry.isfile() and entry.size<=4*1024**2
 source.extractall(root,filter='data')
for path in root.rglob('*'):
 path.chmod(0o700 if path.is_dir() else 0o444)
REMOTE
env LD_LIBRARY_PATH=/opt/ocean-c23-sqlite/lib PYTHONPATH=/var/lib/ocean-c23/operator-source-20261026-01 /var/lib/ocean-c23/operator-venv/bin/python -B -m sandbox.experiment.gcp.run_operator_acceptance run --case smoke --attempt-dir /var/lib/ocean-c23/operator-acceptance/smoke-20261026-01 --blueprint /var/lib/ocean-c23/operator-source-20261026-01/docs/plans/ocean-v1/evidence/C23/operator-acceptance-preparation/blueprint.json --blueprint-sha256 6d63c5b5a091330af6bcfbfcd9ec978cad860248500e0923d685859310bd6f5d --host-controls /var/lib/ocean-c23/evidence/host-positive-controls-20261026-01.json --host-controls-sha256 867fbda9409cc4298a53720fd570f5717dbdefb71a9cd3aa150a1cba4444dc91 --network-isolation /var/lib/ocean-c23/evidence/network-isolation-20261026-01.json --network-isolation-sha256 53a8cf1f54a129f1d5abcce7aaba21f92f8734f9c3a168ded670d1265cbfcf2a --normalization-receipt /var/lib/ocean-c23/evidence/rootfs-normalization-quota-v3.json --normalization-sha256 d75b965714e6335774af59eb6ab7616325b45ac3add38a5f2abf9a474a329824
