import os,sys,json,time,hashlib,cProfile,pstats,functools,gc
from pathlib import Path
sys.path.insert(0,'/Users/jaronchai/Documents/GitHub/provenance-eco-rag')
os.environ['DEPLOYMENT_ENV']='test'
os.environ['ENABLE_V1_CATALOGUE']='true'
os.environ['ENABLE_V1_CATALOGUE_BROWSER']='true'
from ingestion.artifact_store import BoundedLocalStore
from ingestion.edna_catalogue_inputs import dataset_metadata
import ingestion.edna_catalogue_inputs as ei
from ingestion.gcs_catalogue_snapshot import GcsCatalogueSnapshotStore
from api.v1_catalogue_host import load_snapshot_catalogue,_canonical
from tests.catalogue_service_support import fixture_user
from retrieval.source_scope import EvidenceScope,FAMILIES
root=Path('/private/tmp/ocean-beta-multi-catalogue-prepared-20261103')
activation=(root/'activation.json').read_bytes();identity=hashlib.sha256(activation).hexdigest();doc=json.loads(activation)
binding={'version':'ocean-v1-gcs-catalogue-host-v1','project_id':'ocean-v1-beta-20261101','site_id':'v1:ocean-v1-beta-20261101','bucket':'ocean-v1-beta-20261101-snapshots','prefix':'v1/catalogue','activation_object':'v1/catalogue/activations/'+identity+'.json','activation_sha256':identity}
source=Path('/private/tmp/ocean-beta-edna-latency-source-20261103.json');source.write_bytes(_canonical(binding));source.chmod(0o444)
transport=BoundedLocalStore(root/'store')
reader=GcsCatalogueSnapshotStore(access_gate=lambda _:True,_test_store=transport)
candidates=[]
for entry in doc['snapshots']:
 for child in entry['registration']['child_snapshot_ids']:
  manifest,contents=reader.read(child)
  for obj in manifest.objects:
   if obj.schema_version=='catalogue-edna-dataset-v1':
    meta=dataset_metadata(contents[obj.object_id]);rows=next(s.row_count for s in meta.tables if s.name=='detections')
    candidates.append((rows,manifest,contents,obj))
rows,manifest,contents,obj=max(candidates,key=lambda x:x[0])
profile=cProfile.Profile();start=time.perf_counter();profile.enable();loaded=ei.load_dataset(manifest,contents,obj);profile.disable();wall=time.perf_counter()-start
profile.dump_stats('/private/tmp/ocean-beta-edna-largest-dataset-20261103.pstats')
stat=pstats.Stats(profile)
top=[]
for (file,line,name),(cc,nc,tt,ct,callers) in sorted(stat.stats.items(),key=lambda x:x[1][3],reverse=True)[:35]:
 top.append({'function':file+':'+str(line)+':'+name,'primitive_calls':cc,'calls':nc,'self_seconds':round(tt,5),'cumulative_seconds':round(ct,5)})
del loaded,candidates,manifest,contents;gc.collect()
timers={}
def timed(label,original):
 @functools.wraps(original)
 def wrapper(*a,**kw):
  start=time.perf_counter()
  try:return original(*a,**kw)
  finally:
   count,seconds=timers.get(label,(0,0));timers[label]=(count+1,seconds+time.perf_counter()-start)
 return wrapper
for name in ['parse_table','validate_rows','_frame_records','_validate_primitives','_json_object']:
 setattr(ei,name,timed('edna.'+name,getattr(ei,name)))
import orchestration.frozen_edna_catalogue as fe
fe.load_dataset=timed('edna.load_dataset',fe.load_dataset)
GcsCatalogueSnapshotStore.read=timed('store.read',GcsCatalogueSnapshotStore.read)
GcsCatalogueSnapshotStore.lifecycle=timed('store.lifecycle',GcsCatalogueSnapshotStore.lifecycle)
start=time.perf_counter();service,browser=load_snapshot_catalogue(source,project_id=binding['project_id'],site_id=binding['site_id'],cursor_key=b'audit-private-synthetic-cursor'*2,_allow_test_owner=True,_test_store=transport);startup=time.perf_counter()-start
a=fixture_user('beta-latency-local-synthetic',role='admin')
scope=EvidenceScope.model_validate({'version':1,'sources':{f:{'enabled':f=='edna_metabarcoding','filters':{}} for f in FAMILIES}}).model_dump(mode='json')
entry=next(e for e in doc['snapshots'] if any(d['source_family']=='edna_metabarcoding' for d in e['datasets']))
timers.clear();start=time.perf_counter();result=service.overview({'snapshot_id':entry['descriptor']['snapshot_id'],'scope':scope},a);overview=time.perf_counter()-start
report={'state':'local_transport_profile_only','source_activation_sha256':identity,'largest_dataset_detection_rows':rows,'largest_profiled_load_wall_seconds':round(wall,5),'largest_profile_functions':top,'startup_seconds':round(startup,5),'edna_overview_seconds':round(overview,5),'overview_root_items':len(result['items']),'aggregate_timers':{k:{'calls':v[0],'seconds':round(v[1],5)} for k,v in timers.items()},'scientific_rows_emitted':False,'cloud_calls':False,'actual_authenticated_production_acceptance':False}
Path('/private/tmp/ocean-beta-edna-latency-audit-20261103.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report,indent=2))
