
import os,json,stat,hashlib,sys
from pathlib import Path
assert os.getuid()==10001 and os.getgid()==10001
for name in ('beta-host-config.json','beta-catalogue-source.json','source-manifest.json'):
 p=Path('/opt/ocean')/name;s=p.stat()
 assert p.is_file() and not p.is_symlink() and s.st_uid==0 and stat.S_IMODE(s.st_mode)==0o444 and s.st_nlink==1
assert not any(os.environ.get(k) for k in ('DATABASE_URL','OCEAN_V1_DATABASE_URL','OCEAN_V1_INTERNAL_AUTH_SECRET','V1_AUTH_SECRET','V1_GOOGLE_CLIENT_SECRET','GOOGLE_APPLICATION_CREDENTIALS'))
a=json.loads(Path('/opt/ocean/source-manifest.json').read_bytes())
assert a['revision']=='a4923c4e41fba694f77ebb60c1d3f768390e8b1b' and len(a['sources'])==173
for name in ('api/v1_host.py','api/v1_catalogue_host.py','ingestion/gcs_catalogue_snapshot.py'):
 assert hashlib.sha256((Path('/opt/ocean')/name).read_bytes()).hexdigest()==a['sources'][name]
import beta_entry
beta_entry.validate_serving_source(os.environ)
from api.v1_catalogue_host import _ConfigurationSource,_source_binding
source=_ConfigurationSource('/opt/ocean/beta-catalogue-source.json')
binding=_source_binding(source,'ocean-v1-beta-20261101','v1:ocean-v1-beta-20261101')
assert binding['activation_sha256']=='746743985d3d4eca37b41cb62c9e7f8ef55782ab977ff7f242ddbc45db6490ed'
assert set(binding)=={'version','project_id','site_id','bucket','prefix','activation_object','activation_sha256'}
from ingestion.gcs_catalogue_snapshot import GcsCatalogueSnapshotStore
try:GcsCatalogueSnapshotStore(access_gate=lambda m:True,_test_store=object())
except ValueError:pass
else:raise AssertionError('Production transport injection allowed')
assert 'api.main' not in sys.modules
print(json.dumps({'state':'sealed_snapshot_image_verified','revision':a['revision'],'uid':os.getuid(),'configuration_root_owned_0444':True,'source_bound_modules':3,'opaque_binding_only':True,'database_data_authority_or_credentials_accessed':False,'production_test_transport_injection_denied':True,'network':'none'}))
