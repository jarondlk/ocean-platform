set -euo pipefail
[[ "$(id -u)" == 0 && "$(hostname -s)" == c23-containment-01 ]]
umask 077
export LD_LIBRARY_PATH=/opt/ocean-c23-sqlite/lib
export PYTHONDONTWRITEBYTECODE=1
export PYTHONPATH=/var/lib/ocean-c23/operator-source-20261027-08
/var/lib/ocean-c23/operator-venv/bin/python -B -m sandbox.experiment.gcp.run_operator_acceptance seal-network-isolation --instance-resource=/tmp/c23-network-20261028/instance.json --routers=/tmp/c23-network-20261028/routers.json --network-resource=/tmp/c23-network-20261028/network.json --subnetwork-resource=/tmp/c23-network-20261028/subnet.json --complete-router-inventory --output=/var/lib/ocean-c23/evidence/network-isolation-retained-20261028.json
python3 -I -S -B - <<'PY'
from pathlib import Path
import json,hashlib,subprocess
raw=subprocess.run(['ss','-H','-lntp'],check=True,capture_output=True,text=True).stdout
rows=[line for line in raw.splitlines() if any(line.split()[3].endswith(':'+str(p)) for p in (55423,55424))]
assert len(rows)==2 and {line.split()[3] for line in rows}=={'127.0.0.1:55423','127.0.0.1:55424'}
receipt={'version':'c23-retained-loopback-control-listeners-v1','boot_id':Path('/proc/sys/kernel/random/boot_id').read_text().strip(),'listeners':rows,'loopback_only':True,'source':'ss -H -lntp, root observation','guest_credentials_provided':False}
p=Path('/var/lib/ocean-c23/evidence/retained-loopback-listeners-20261028.json')
with p.open('x') as f:json.dump(receipt,f,sort_keys=True,separators=(',',':'));f.write('\n')
p.chmod(0o400)
print(json.dumps(receipt))
PY
