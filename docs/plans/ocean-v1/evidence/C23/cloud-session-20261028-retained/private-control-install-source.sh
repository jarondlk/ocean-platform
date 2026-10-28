set -euo pipefail
[[ "$(id -u)" == 0 && "$(hostname -s)" == c23-containment-01 ]]
umask 077
python3 -I -S -B - <<'PY'
from pathlib import Path
import json,hashlib,os
source=Path('/tmp/c23-retained-upload-20261028');target=Path('/var/lib/ocean-c23/retained-control-20261028')
assert source.is_dir() and not target.exists();target.mkdir(mode=0o700)
expected={'scientific':'7e74ab44e748d3b79e2837f306fed9f24dad79078c0edbde9b1101c8a26ca37b','publication-revoked':'942970477ee51d5f5e4a368749362068d6721cbb59cda29f1a89bb96c37f49bd'}
for case,digest in expected.items():
 raw=(source/(case+'.json')).read_bytes();assert hashlib.sha256(raw).hexdigest()==digest
 doc=json.loads(raw);assert doc['private_key_path']==str(target/(case+'.seed'))
 seed=(source/(case+'.seed')).read_bytes();assert len(seed)==32
 for suffix,data in [('.json',raw),('.seed',seed)]:
  path=target/(case+suffix)
  with path.open('xb') as f:f.write(data)
  path.chmod(0o400)
  assert path.stat().st_uid==0 and path.stat().st_gid==0
for case in expected:
 for suffix in ('.json','.seed'):(source/(case+suffix)).unlink()
source.rmdir()
print(json.dumps({'version':'c23-retained-private-control-install-v1','two_private_configs_verified':True,'root_parent_mode':'0700','root_files_mode':'0400','upload_copies_removed':True,'guest_or_export_tree_credentials':False,'admin_or_GCP_credentials_transferred':False}))
PY
