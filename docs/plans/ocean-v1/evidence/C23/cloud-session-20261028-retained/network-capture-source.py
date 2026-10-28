from pathlib import Path
from datetime import datetime,timezone
import subprocess,json,hashlib
out=Path('/Users/jaronchai/Documents/GitHub/provenance-eco-rag/docs/plans/ocean-v1/evidence/C23/cloud-session-20261028-retained/network01');out.mkdir(mode=0o700,exist_ok=False)
gcloud='/opt/homebrew/bin/gcloud'
commands={'instance':[gcloud,'compute','instances','describe','c23-containment-01','--zone=asia-northeast1-a'], 'routers':[gcloud,'compute','routers','list'], 'network':[gcloud,'compute','networks','describe','c23-private'], 'subnet':[gcloud,'compute','networks','subnets','describe','c23-tokyo','--region=asia-northeast1']}
receipts=[]
for name,cmd in commands.items():
 cmd+=['--project=ocean-v1-c23-20261024','--format=json']
 started=datetime.now(timezone.utc).isoformat()
 with (out/(name+'.json')).open('xb') as stdout,(out/(name+'.stderr.txt')).open('xb') as stderr:
  result=subprocess.run(cmd,stdout=stdout,stderr=stderr,timeout=90,check=False)
 receipts.append({'resource':name,'command':cmd,'started_at':started,'finished_at':datetime.now(timezone.utc).isoformat(),'exit_code':result.returncode,'sha256':hashlib.sha256((out/(name+'.json')).read_bytes()).hexdigest()})
 assert result.returncode==0
x=json.loads((out/'instance.json').read_text());assert x['status']=='RUNNING' and x['id']=='7275994259687337942'
assert not x.get('serviceAccounts') and not any(n.get('accessConfigs') for n in x['networkInterfaces'])
assert not json.loads((out/'routers.json').read_text())
assert not json.loads((out/'network.json').read_text()).get('peerings')
with (out/'api-provenance.json').open('x') as f:json.dump({'version':'c23-complete-network-api-provenance-v1','reads':receipts,'complete_router_inventory':True,'no_external_IP':True,'no_service_accounts':True,'no_routers_or_NAT':True,'no_peerings':True,'source_commit':'501c80b7e5ee07f0990539baea3d8243f71d184a'},f,indent=2,sort_keys=True);f.write('\n')
print(json.dumps({'four_complete_reads':True,'no_external_IP':True,'no_routers_or_NAT':True,'actual_stop_deadline':x['resourceStatus']['scheduling']['terminationTimestamp']}))
