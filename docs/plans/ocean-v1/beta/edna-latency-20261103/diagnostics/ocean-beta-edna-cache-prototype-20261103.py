"""Private measurement prototype only; not production cache implementation."""
import os,sys,json,time,hashlib,copy,resource
from pathlib import Path
sys.path.insert(0,'/Users/jaronchai/Documents/GitHub/provenance-eco-rag')
os.environ['DEPLOYMENT_ENV']='test';os.environ['ENABLE_V1_CATALOGUE']='true';os.environ['ENABLE_V1_CATALOGUE_BROWSER']='true'
from ingestion.artifact_store import BoundedLocalStore
from ingestion.edna_catalogue_inputs import DatasetInputs,_verified_bytes
from ingestion.immutable_bundle import canonical_bytes
from ingestion.gcs_catalogue_snapshot import GcsCatalogueSnapshotStore
from schema.catalogue_snapshot import manifest_id
from api.v1_catalogue_host import load_snapshot_catalogue
from tests.catalogue_service_support import fixture_user
from retrieval.source_scope import EvidenceScope,FAMILIES
import orchestration.frozen_edna_catalogue as fe
project=Path('/Users/jaronchai/Documents/GitHub/provenance-eco-rag')
paths=['ingestion/edna_catalogue_inputs.py','orchestration/frozen_edna_catalogue.py','orchestration/frozen_scientific_catalogue.py','orchestration/catalogue_service.py','ingestion/gcs_catalogue_snapshot.py','api/v1_catalogue_host.py']
pins={p:hashlib.sha256((project/p).read_bytes()).hexdigest() for p in paths}
root=Path('/private/tmp/ocean-beta-multi-catalogue-prepared-20261103');doc=json.loads((root/'activation.json').read_bytes());activation=hashlib.sha256((root/'activation.json').read_bytes()).hexdigest()
source=Path('/private/tmp/ocean-beta-edna-latency-source-20261103.json');transport=BoundedLocalStore(root/'store')
cache={};budget=1024*1024*1024;retained=0;hits=misses=0;original=fe.load_dataset
sizes={};taxonomy_rows=taxonomy_distinct=0

def clone(value):
 return DatasetInputs(value.metadata.model_copy(deep=True),{name:frame.copy(deep=True) for name,frame in value.tables.items()},tuple(copy.deepcopy(obj) for obj in value.objects))

def cached(manifest,contents,obj,*,decoded_budget=None):
 global retained,hits,misses,taxonomy_rows,taxonomy_distinct
 key=(manifest_id(manifest),obj.object_id)
 # Fresh snapshot reader has already verified every exact object and control.
 # Recheck each owned byte payload too; cache key cannot excuse changed bytes.
 for member in manifest.objects:
  if member.dataset_id==obj.dataset_id:_verified_bytes(member,contents)
 if key in cache:
  hits+=1;value=cache[key]
  decoded=sum(frame.attrs['decoded_bytes'] for frame in value.tables.values())
  if decoded_budget is not None and decoded>decoded_budget:raise ValueError('Current decoded budget exceeded')
  return clone(value)
 misses+=1;value=original(manifest,contents,obj,decoded_budget=decoded_budget)
 amount=sum(int(frame.memory_usage(index=True,deep=True).sum()) for frame in value.tables.values())
 if len(cache)>=64 or retained+amount>budget:
  Path('/private/tmp/ocean-beta-edna-cache-prototype-failure-20261103.json').write_text(json.dumps({'reason':'prototype_memory_budget','retained':retained,'next_entry_bytes':amount,'entries':len(cache),'budget':budget}));raise ValueError('Prototype bounded retained-memory gate exceeded')
 cache[key]=value;sizes[key]=amount;retained+=amount
 frame=value.tables.get('detections')
 if frame is not None:
  taxonomy_rows+=len(frame);taxonomy_distinct+=frame.taxonomy_json.nunique()
 return clone(value)
fe.load_dataset=cached
service,browser=load_snapshot_catalogue(source,project_id='ocean-v1-beta-20261101',site_id='v1:ocean-v1-beta-20261101',cursor_key=b'audit-private-synthetic-cursor'*2,_allow_test_owner=True,_test_store=transport)
actor=fixture_user('beta-latency-local-synthetic',role='admin')
scope=EvidenceScope.model_validate({'version':1,'sources':{f:{'enabled':f=='edna_metabarcoding','filters':{}} for f in FAMILIES}}).model_dump(mode='json')
entry=next(e for e in doc['snapshots'] if any(d['source_family']=='edna_metabarcoding' for d in e['datasets']))
payload={'snapshot_id':entry['descriptor']['snapshot_id'],'scope':scope}
start=time.perf_counter();first=service.overview(payload,actor);cold=time.perf_counter()-start
start=time.perf_counter();second=service.overview(payload,actor);warm=time.perf_counter()-start
assert first==second
selected=next(item['dataset_id'] for item in entry['datasets'] if item['source_family']=='edna_metabarcoding')
Path('/private/tmp/ocean-beta-edna-cache-prototype-overviews-20261103.json').write_text(json.dumps({'state':'private_overview_only_cache_prototype','fill_seconds':cold,'warm_seconds':warm,'retained_dataframe_bytes':retained,'entries':len(cache),'peak_rss_bytes':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,'source_pins':pins,'production_accepted':False}));
start=time.perf_counter();result=service.query({**payload,'input_ids':[selected],'operation_id':'c13.operation','operation_version':'c13-v1','parameters':{'operation_id':'c12.table','operation_version':'c12-v1','parameters':{'table':'detections','population':'raw'},'limit':5}},actor);query=time.perf_counter()-start
assert len(result['rows'])==5
assert pins=={p:hashlib.sha256((project/p).read_bytes()).hexdigest() for p in paths}
report={'state':'private_detached_input_cache_prototype_only','activation_sha256':activation,'source_pins':pins,'cache_fill_overview_seconds':round(cold,5),'cache_warm_overview_seconds':round(warm,5),'cache_warm_five_detection_query_seconds':round(query,5),'overview_exact_response_equal':first==second,'cache_entries':len(cache),'cache_hits':hits,'cache_misses':misses,'dataframe_deep_memory_bytes':retained,'memory_budget_bytes':budget,'peak_rss_bytes':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,'per_dataset_unique_taxonomy_rows_sum':taxonomy_distinct,'detection_taxonomy_rows':taxonomy_rows,'scientific_rows_emitted':False,'cloud_calls':False,'production_security_eviction_and_concurrency_tests_implemented':False,'actual_production_acceptance':False}
Path('/private/tmp/ocean-beta-edna-cache-prototype-20261103.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
