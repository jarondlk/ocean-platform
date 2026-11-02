"""Create-only first beta snapshot publication and one prefix-scoped reader."""
import base64,copy,hashlib,json,re,subprocess,urllib.request,urllib.error,urllib.parse
from pathlib import Path
import google_crc32c

PROJECT='ocean-v1-beta-20261101';BUCKET=PROJECT+'-snapshots'
SOURCE=Path('/private/tmp/ocean-beta-ctd-catalogue-a4923c4')
ROOT=Path('/Users/jaronchai/Documents/GitHub/provenance-eco-rag')
P=ROOT/'docs/plans/ocean-v1/beta/snapshot-activation-20261103'
REV='a4923c4e41fba694f77ebb60c1d3f768390e8b1b'
ACTIVATION='746743985d3d4eca37b41cb62c9e7f8ef55782ab977ff7f242ddbc45db6490ed'
MEMBER='serviceAccount:ocean-v1-beta-serving@'+PROJECT+'.iam.gserviceaccount.com'
EXPRESSION="resource.name.startsWith('projects/_/buckets/"+BUCKET+"/objects/v1/catalogue/')"
class NR(urllib.request.HTTPRedirectHandler):
 def redirect_request(self,*args,**kw):return None
def save(n,d):
 with (P/n).open('x') as f:json.dump(d,f,indent=2);f.write('\n')
def digest(data):return hashlib.sha256(data).hexdigest()
def signature(s):return (s.st_dev,s.st_ino,s.st_mode,s.st_uid,s.st_gid,s.st_nlink,s.st_size,s.st_mtime_ns,s.st_ctime_ns)
def main():
 manifest=json.loads((SOURCE/'publication-manifest.json').read_bytes())
 assert manifest['source_revision']==REV and manifest['project_id']==PROJECT and manifest['bucket']==BUCKET
 assert manifest['activation_sha256']==ACTIVATION and manifest['scientific_approval'] is False
 assert len(manifest['files'])==8 and sum(x['upload_last'] for x in manifest['files'])==1
 selected=sorted(manifest['files'],key=lambda x:(x['upload_last'],x['object_key']))
 assert selected[-1]['object_key']=='v1/catalogue/control.json'
 bodies={}
 for entry in selected:
  key=entry['object_key'];local=entry['local_path']
  assert re.fullmatch(r'v1/catalogue/(?:objects/[a-f0-9]{64}|manifests/[a-f0-9]{64}\.json|activations/[a-f0-9]{64}\.json|control\.json)',key)
  assert local==('activation.json' if key.startswith('v1/catalogue/activations/') else 'store/'+key)
  path=SOURCE/local;assert not path.is_symlink() and path.resolve().is_relative_to(SOURCE)
  before=signature(path.lstat());data=path.read_bytes();assert before==signature(path.lstat())
  assert len(data)==entry['bytes'] and digest(data)==entry['sha256'];bodies[key]=data
 assert not (P/'data-upload-selection.json').exists(),'Existing attempt; inspect instead of rerun'
 r=subprocess.run(['/opt/homebrew/bin/gcloud','auth','print-access-token','--project='+PROJECT,'--quiet'],capture_output=True,text=True,timeout=30,check=True)
 token=r.stdout.strip();opener=urllib.request.build_opener(NR());base='https://storage.googleapis.com/storage/v1/b/'+BUCKET
 def request(method,url,data=None,missing=False):
  assert url.startswith((base,'https://storage.googleapis.com/upload/storage/v1/b/'+BUCKET+'/o?'))
  req=urllib.request.Request(url,method=method,data=data,headers={'Authorization':'Bearer '+token,'Content-Type':'application/octet-stream','Accept-Encoding':'identity'})
  try:
   with opener.open(req,timeout=40) as h:return json.load(h)
  except urllib.error.HTTPError as e:
   if missing and e.code==404:return {'http_status':404}
   raise RuntimeError('Fixed beta snapshot request failed with HTTP '+str(e.code)) from None
 bucket=request('GET',base)
 assert bucket['name']==BUCKET and bucket['projectNumber']=='534831104543' and bucket['location']=='ASIA-NORTHEAST1'
 assert bucket['iamConfiguration']['uniformBucketLevelAccess']['enabled'] and bucket['iamConfiguration']['publicAccessPrevention']=='enforced'
 save('snapshot-bucket-before.json',bucket)
 policy=request('GET',base+'/iam?optionsRequestedPolicyVersion=3');save('snapshot-iam-before.json',policy)
 assert all(not {'allUsers','allAuthenticatedUsers'}.intersection(v['members']) for v in policy.get('bindings',[]))
 assert all(MEMBER not in b['members'] for b in policy.get('bindings',[])),'Existing serving authority needs separate reconciliation'
 for key in bodies:
  assert request('GET',base+'/o/'+urllib.parse.quote(key,safe=''),missing=True)=={'http_status':404},'Existing object; inspect before publication'
 save('data-upload-selection.json',{'state':'selected_once','source_revision':REV,'bucket':BUCKET,'activation_sha256':ACTIVATION,'objects':[{k:v for k,v in e.items() if k!='local_path'} for e in selected],'immutable_bytes_before_control':True,'if_generation_match':0,'scientific_approval':False,'research_enabled':False})
 results=[]
 for entry in selected:
  key=entry['object_key'];data=bodies[key]
  params=urllib.parse.urlencode({'uploadType':'media','name':key,'ifGenerationMatch':'0'})
  actual=request('POST','https://storage.googleapis.com/upload/storage/v1/b/'+BUCKET+'/o?'+params,data)
  crc=base64.b64encode(google_crc32c.value(data).to_bytes(4,'big')).decode()
  assert actual['name']==key and actual['bucket']==BUCKET and int(actual['size'])==len(data) and actual['crc32c']==crc
  url=base+'/o/'+urllib.parse.quote(key,safe='')+'?alt=media&generation='+actual['generation']
  req=urllib.request.Request(url,headers={'Authorization':'Bearer '+token,'Accept-Encoding':'identity'})
  with opener.open(req,timeout=30) as h:observed=h.read(len(data)+1)
  assert observed==data and digest(observed)==entry['sha256']
  result={'name':key,'generation':actual['generation'],'bytes':len(data),'sha256':entry['sha256'],'crc32c':crc,'download_sha256_verified':True,'control_published_last':entry['upload_last']}
  save('data-object-'+str(len(results))+'.json',result);results.append(result)
 save('data-upload-complete.json',{'state':'sealed_ctd_objects_and_activation_verified','bucket':BUCKET,'source_revision':REV,'objects':results,'casts':162,'depth_observations':10955,'scientific_approval':False,'research_enabled':False,'serving_activated':False})
 save('reader-grant-selection.json',{'state':'selected_once','bucket':BUCKET,'member':MEMBER,'role':'roles/storage.objectViewer','condition':{'title':'ocean-v1-beta-catalogue-only','expression':EXPRESSION},'direct_legacy_or_project_grant':False})
 cmd=['/opt/homebrew/bin/gcloud','storage','buckets','add-iam-policy-binding','gs://'+BUCKET,'--member='+MEMBER,'--role=roles/storage.objectViewer','--condition=expression='+EXPRESSION+',title=ocean-v1-beta-catalogue-only','--project='+PROJECT,'--quiet','--format=json']
 r=subprocess.run(cmd,capture_output=True,text=True,timeout=45)
 assert r.returncode==0,'Reader grant outcome needs inspection; no automatic retry'
 after=request('GET',base+'/iam?optionsRequestedPolicyVersion=3');save('snapshot-iam-after.json',after)
 matches=[b for b in after.get('bindings',[]) if b['role']=='roles/storage.objectViewer' and b.get('condition',{}).get('expression')==EXPRESSION and MEMBER in b['members']];assert len(matches)==1
 restored=copy.deepcopy(after);target=next(b for b in restored['bindings'] if b['role']=='roles/storage.objectViewer' and b.get('condition',{}).get('expression')==EXPRESSION and MEMBER in b['members']);target['members'].remove(MEMBER);restored['bindings']=[b for b in restored['bindings'] if b['members']]
 def canon(p):return sorted((b['role'],json.dumps(b.get('condition',{}),sort_keys=True),tuple(sorted(b['members']))) for b in p.get('bindings',[]))
 assert canon(restored)==canon(policy)
 save('reader-grant-verification.json',{'state':'one_prefix_scoped_beta_snapshot_reader_verified','member':MEMBER,'resource':'gs://'+BUCKET,'role':'roles/storage.objectViewer','expression':EXPRESSION,'all_other_bindings_preserved':True,'legacy_or_project_grant':False,'keys_or_secrets_read':False})
 print(json.dumps({'state':'ctd_snapshot_storage_and_reader_ready','objects':len(results),'casts':162,'depth_observations':10955,'reader_scope':'beta snapshot bucket v1/catalogue/ only','serving_activated':False}))
if __name__=='__main__':main()
