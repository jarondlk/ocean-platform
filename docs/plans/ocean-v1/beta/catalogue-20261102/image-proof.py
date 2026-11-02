
import os,json,stat,hashlib,uuid
from pathlib import Path
from pydantic import SecretStr
assert os.getuid()==10001 and os.getgid()==10001
for name in ('beta-host-config.json','beta-empty-catalogue.json','source-manifest.json'):
 p=Path('/opt/ocean')/name;s=p.stat()
 assert p.is_file() and not p.is_symlink() and s.st_uid==0 and stat.S_IMODE(s.st_mode)==0o444 and s.st_nlink==1
assert not any(os.environ.get(k) for k in ('DATABASE_URL','OCEAN_V1_DATABASE_URL','OCEAN_V1_INTERNAL_AUTH_SECRET','V1_AUTH_SECRET','V1_GOOGLE_CLIENT_SECRET'))
manifest=json.loads(Path('/opt/ocean/source-manifest.json').read_text())
assert manifest['revision']=='abcdff79d8695be2e493efa29dc92c454d5b6dfe'
for name in ('api/v1_host.py','api/v1_catalogue_host.py'):
 assert hashlib.sha256((Path('/opt/ocean')/name).read_bytes()).hexdigest()==manifest['sources'][name]
import beta_entry
beta_entry.validate_serving_source(os.environ)
from api.v1_host import V1HostSettings,catalogue_services_from_environment
from api.auth import CurrentUser,ROLE_PERMISSIONS
cfg=json.loads(Path('/opt/ocean/beta-host-config.json').read_text())
for name in ('backend_hosts','allowed_providers'):cfg[name]=tuple(cfg[name])
services=catalogue_services_from_environment(V1HostSettings.model_validate(cfg),SecretStr('offline-image-check-public-test-key-'*2),os.environ)
assert services.investigation_service is None and services.research_run_service is None
actor=CurrentUser(uuid.UUID(int=1),'offline-image@example.invalid',None,'admin','internal','active',ROLE_PERMISSIONS['admin'],'google')
scope={'version':1,'sources':{family:{'enabled':family=='ctd','filters':{}} for family in ('ctd','metagenome','remote_sensing','edna_metabarcoding')}}
result=services.catalogue_browser.discover({'scope':scope},actor)
assert result['total']==0 and result['snapshots']==[] and result['latest_snapshot_id'] is None
print(json.dumps({'state':'catalogue_image_verified','revision':manifest['revision'],'uid':os.getuid(),'configuration_root_owned_0444':True,'actual_empty_discovery':True,'research_enabled':False,'database_or_credentials_used':False,'network':'none'}))
